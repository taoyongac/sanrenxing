#!/usr/bin/env python3
"""三人行 (sanrenxing) web demo — stdlib HTTP + SSE, no web framework.

Serves a single-page UI and a live discussion stream:
  GET  /                       -> static/index.html
  GET  /api/ask?q=...&rounds=N -> SSE: 3 seats stream in parallel, then the
                                  curator's possibility map.

Config (env):
  SANRENXING_HOST   bind host           (default 127.0.0.1)
  SANRENXING_PORT   bind port           (default 8030)
  SANRENXING_ROUNDS seat rounds         (default 2)
  SANRENXING_USER / SANRENXING_PASS     optional HTTP Basic Auth (both required to enable)
Seats are configured via SEATn_* (see sanrenxing.config / .env.example).

A single global lock serializes discussions (concurrency = 1) so a shared demo
never piles up parallel runs and burns the owner's quota.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sanrenxing import llm  # noqa: E402
from sanrenxing.config import load_seats  # noqa: E402
from sanrenxing.discussion import (curate, seat_prompt)  # noqa: E402

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

HOST = os.environ.get("SANRENXING_HOST", "127.0.0.1")
PORT = int(os.environ.get("SANRENXING_PORT", "8030"))
ROUNDS = int(os.environ.get("SANRENXING_ROUNDS", "2"))
USER = os.environ.get("SANRENXING_USER", "")
PASS = os.environ.get("SANRENXING_PASS", "")

RUN_LOCK = threading.Lock()  # concurrency = 1


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quieter logs
        pass

    # -------------------------------------------------- auth
    def _authed(self) -> bool:
        if not (USER and PASS):
            return True
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                u, p = base64.b64decode(h[6:]).decode().split(":", 1)
                if u == USER and p == PASS:
                    return True
            except Exception:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="sanrenxing"')
        self.end_headers()
        return False

    # -------------------------------------------------- routing
    def do_GET(self):
        if not self._authed():
            return
        u = urlparse(self.path)
        if u.path == "/" or u.path == "/index.html":
            return self._send_file(STATIC / "index.html", "text/html; charset=utf-8")
        if u.path == "/api/ask":
            return self._stream_discussion(parse_qs(u.query))
        self.send_error(404)

    def _send_file(self, path: Path, ctype: str):
        try:
            body = path.read_bytes()
        except OSError:
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -------------------------------------------------- discussion stream
    def _stream_discussion(self, qs: dict):
        question = (qs.get("q", [""])[0]).strip()
        rounds = max(1, min(int(qs.get("rounds", [str(ROUNDS)])[0] or ROUNDS), 4))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def emit(event, data):
            try:
                self.wfile.write(_sse(event, data))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                raise

        if not question:
            emit("error", {"text": "empty question"})
            return
        if not RUN_LOCK.acquire(blocking=False):
            emit("busy", {"text": "另一场讨论进行中，请稍候再试。"})
            return
        try:
            self._run(question, rounds, emit)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            RUN_LOCK.release()

    def _run(self, question: str, rounds: int, emit):
        try:
            seats = load_seats()
        except Exception as e:
            return emit("error", {"text": f"seats not configured: {e}"})

        transcript: list[tuple[int, dict[str, str]]] = []
        peers: dict[str, str] = {}
        for r in range(1, rounds + 1):
            emit("round_start", {"round": r})
            outs: dict[str, str] = {}

            # Seat 1 streams token-by-token (snappy first paint); the rest block
            # in parallel. All are independent reasoning calls.
            head, rest = seats[0], seats[1:]
            with ThreadPoolExecutor(max_workers=max(1, len(rest))) as ex:
                fut = {ex.submit(self._seat_block, s, question, r, peers): s
                       for s in rest}
                # stream the head seat live
                emit("status", {"agent": head.name, "text": "构思中", "round": r})
                acc = []
                try:
                    for tok in llm.chat_stream(
                            head.model, seat_prompt(head, question, r, peers),
                            base_url=head.base_url, api_key=head.api_key):
                        acc.append(tok)
                        emit("delta", {"agent": head.name, "text": tok, "round": r})
                except Exception as e:
                    acc = [f"[{head.name} 未能作答: {e}]"]
                outs[head.name] = "".join(acc).strip()
                emit("done", {"agent": head.name, "text": outs[head.name], "round": r})
                for f in fut:
                    s = fut[f]
                    txt = f.result()
                    outs[s.name] = txt
                    emit("done", {"agent": s.name, "text": txt, "round": r})
            transcript.append((r, outs))
            peers = outs

        emit("map_start", {"text": "正将多轮讨论绘成可能性地图…"})
        pmap = curate(question, transcript, seats)
        if pmap.get("direct"):
            emit("direct", {"text": pmap["direct"]})
        if pmap.get("overview"):
            emit("overview", {"text": pmap["overview"]})
        letters = ["A", "B", "C", "D", "E"]
        for i, b in enumerate(pmap.get("branches", [])[:5]):
            emit("branch", {
                "n": letters[i] if i < len(letters) else str(i + 1),
                "title": b.get("title", f"分支{i+1}"),
                "bridge": b.get("bridge", ""),
                "insight": b.get("insight", "—"),
                "next": b.get("next", ""),
                "meta": f"前提 · {b.get('premise','—')}　｜　代价 · {b.get('cost','—')}",
            })
        if pmap.get("more"):
            emit("more", {"text": pmap["more"]})
        emit("map_done", {"text": ""})

    @staticmethod
    def _seat_block(seat, question, round_no, peers) -> str:
        try:
            return llm.chat(seat.model, seat_prompt(seat, question, round_no, peers),
                            base_url=seat.base_url, api_key=seat.api_key)
        except Exception as e:
            return f"[{seat.name} 未能作答: {e}]"


def main():
    try:
        seats = load_seats()
        print(f"[sanrenxing] {len(seats)} seats: "
              + ", ".join(f"{s.name}({s.model})" for s in seats))
    except Exception as e:
        print(f"[sanrenxing] WARNING: {e}")
    auth = "ON" if (USER and PASS) else "OFF"
    print(f"[sanrenxing] http://{HOST}:{PORT}  (basic-auth: {auth}, rounds: {ROUNDS})")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
