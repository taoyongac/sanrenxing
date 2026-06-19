#!/usr/bin/env python3
"""三人行 (sanrenxing) MCP server — divergent fan-out for any MCP host.

Two tools:
  trio_round — run ONE round of a 3-seat divergent discussion (all seats in
               parallel), return each seat's text + a reminder for the host to
               add its own voice and (optionally) call the next round.
  fanout     — dispatch N self-contained prompts across the configured seats in
               parallel; return structured per-task JSON. The host stays the
               ARBITER — this server never merges, ranks, or picks a winner.

Seats are configured purely through environment variables (see sanrenxing.config
/ .env.example). No provider is hard-coded; any OpenAI-compatible endpoint works.
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Allow running from a checkout without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from sanrenxing import llm  # noqa: E402
from sanrenxing.config import Seat, load_seats  # noqa: E402

mcp = FastMCP("sanrenxing")

MAX_PARALLEL_CAP = int(os.environ.get("SANRENXING_MAX_PARALLEL", "6"))

_TRIO_HEADER = (
    "[三人行 seat — pure reasoning]\n"
    "You are one seat in a 3-way DIVERGENT discussion. Answer from your own "
    "knowledge and the context embedded below. Open a distinct angle; do not "
    "converge to a single answer. If a fact is missing, say so — do not fabricate "
    "citations or accession numbers.\n\n=== TASK ===\n"
)


def _seats_by_id() -> dict[str, Seat]:
    return {s.sid: s for s in load_seats()}


def _invoke(seat: Seat, prompt: str, timeout: float) -> dict:
    t0 = time.time()
    try:
        out = llm.chat(seat.model, prompt, base_url=seat.base_url,
                       api_key=seat.api_key, timeout=timeout)
        return {"status": "ok", "duration_s": round(time.time() - t0, 1),
                "output": out}
    except Exception as e:
        return {"status": "err", "duration_s": round(time.time() - t0, 1),
                "output": f"ERR: {e}"}


@mcp.tool()
def trio_round(seat1_prompt: str, seat2_prompt: str, seat3_prompt: str,
               round_num: int = 1, timeout_s: int = 180) -> str:
    """Run ONE round of a 三人行 (trio) divergent discussion: all 3 seats in parallel.

    Structure (keep it divergent — that is the point):
      - 3 seats answer in parallel, each from a complementary lens.
      - The MCP HOST is effectively a 4th voice + the curator: after this returns,
        write your own analysis, then (for a real discussion) call trio_round again
        embedding the FULL prior-round transcript into each seat prompt so seats
        REACT to each other (yes-and / branch further — not debate-to-consensus).
      - Default cadence: 2-3 rounds, then lay out the possibility map. Do NOT pick
        a single winner unless the user explicitly asks you to decide.

    Args:
        seat1_prompt / seat2_prompt / seat3_prompt: self-contained prompt for each
            seat (rounds 2+: embed the prior transcript so seats can react).
        round_num: which round this is (informational).
        timeout_s: per-seat timeout in seconds.

    Returns:
        JSON: {"round", "seats": [{sid,name,status,duration_s,output}...],
               "host_reminder": "..."}.
    """
    seats = load_seats()
    prompts = [seat1_prompt, seat2_prompt, seat3_prompt][:len(seats)]
    with ThreadPoolExecutor(max_workers=len(seats)) as ex:
        futs = {ex.submit(_invoke, s, _TRIO_HEADER + p, float(timeout_s)): i
                for i, (s, p) in enumerate(zip(seats, prompts))}
        out: list[dict] = [None] * len(prompts)  # type: ignore
        for f in as_completed(futs):
            i = futs[f]
            r = f.result()
            r.update({"sid": seats[i].sid, "name": seats[i].name})
            out[i] = r

    if round_num >= 3:
        reminder = ("Final round done. Add your own voice, then curate the full "
                    "possibility map: list every branch with premise/cost/next-step. "
                    "Do NOT converge or pick a winner.")
    else:
        reminder = (f"R{round_num} done. Add your own voice, then call trio_round "
                    f"for R{round_num + 1}: embed the FULL R{round_num} transcript "
                    "(all seats + your voice) into each seat prompt; instruct seats "
                    "to react to the others (yes-and, branch further — not debate).")

    return json.dumps({"round": round_num, "seats": out,
                       "host_reminder": reminder}, ensure_ascii=False)


@mcp.tool()
def fanout(tasks: str, max_parallel: int = 6) -> str:
    """Dispatch a batch of self-contained prompts across the seats IN PARALLEL.

    Use for: N independent angles on one question, N approaches to compare, N
    parallel judgments. YOU remain the arbiter — this returns raw per-task output;
    merging / ranking / tallying is your job.

    Args:
        tasks: JSON array string. Each element:
            {"prompt": "<self-contained prompt>",   # required
             "seat": "1" | "2" | "3"}               # optional, default "1"
        max_parallel: concurrency cap (hard-capped at SANRENXING_MAX_PARALLEL, default 6).

    Returns:
        JSON array, input order: [{"idx","seat","status","duration_s","output"}...].
    """
    try:
        batch = json.loads(tasks)
        if not isinstance(batch, list):
            raise ValueError("tasks must be a JSON array")
    except Exception as e:
        return json.dumps([{"idx": 0, "status": "err_badjson",
                            "output": f"could not parse tasks: {e}"}])
    if not batch:
        return json.dumps([])
    by_id = _seats_by_id()
    default_sid = next(iter(by_id))
    n_par = max(1, min(int(max_parallel), MAX_PARALLEL_CAP))

    def _one(idx: int, task: dict) -> dict:
        sid = str(task.get("seat") or default_sid)
        seat = by_id.get(sid)
        prompt = task.get("prompt", "")
        if not seat:
            return {"idx": idx, "seat": sid, "status": "err_badseat",
                    "duration_s": 0, "output": f"unknown seat '{sid}'"}
        if not prompt:
            return {"idx": idx, "seat": sid, "status": "err_badspec",
                    "duration_s": 0, "output": "task missing prompt"}
        r = _invoke(seat, prompt, float(task.get("timeout_s", 180)))
        r.update({"idx": idx, "seat": sid})
        return r

    results: list[dict] = [None] * len(batch)  # type: ignore
    with ThreadPoolExecutor(max_workers=n_par) as ex:
        futs = {ex.submit(_one, i, t): i for i, t in enumerate(batch)}
        for f in as_completed(futs):
            i = futs[f]
            try:
                results[i] = f.result()
            except Exception as e:
                results[i] = {"idx": i, "status": "err_exc", "output": str(e)}
    return json.dumps(results, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
