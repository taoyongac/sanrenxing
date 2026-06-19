"""三人行 discussion engine — divergent, open-mind, mutual-evaluation.

Design intent (this is the whole point — keep it):
  The goal is to OPEN the possibility space, not converge to one winner. Three
  seats with complementary lenses inspire each other; each round a seat reacts
  to the others (spark / tension / gap) and GENERATES new angles — generative,
  never eliminative. A curator then lays out a POSSIBILITY MAP of distinct
  branches (premise + cost + next step). The human chooses.

Flow:
  Round 1     : each seat opens a distinct angle (parallel).
  Round 2..N  : each seat reads the others' prior round, reacts, branches further.
  Curator     : one model integrates all rounds into the possibility map.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Iterator

from . import llm
from .config import Seat, curator_endpoint, load_seats

# Shared style guide injected into every seat — substance over flourish.
_PROSE = ("用清晰、专业的中文作答。务实、严谨，聚焦科学与技术本身；抓住有洞见(insight)的关键点，"
          "以解决问题为目标，尽量输出有价值的实质内容。少用类比、不堆比喻、不卖弄、不轻浮。")


def seats() -> list[Seat]:
    return load_seats()


# ----------------------------------------------------------------- seat prompts
def _peer_ctx(peers: dict[str, str], me: str) -> str:
    """Format the previous round so a seat can react to itself + the others."""
    peers = peers or {}
    lines = []
    if peers.get(me):
        lines.append(f"【你上一轮说】{peers[me]}")
    for k, v in peers.items():
        if k != me and v:
            lines.append(f"【{k} 上一轮说】{v}")
    return "\n".join(lines)


def seat_prompt(seat: Seat, question: str, round_no: int,
                peers: dict[str, str] | None) -> str:
    base = f"{seat.persona}{_PROSE}\n用户的问题：{question}\n\n"
    if round_no == 1:
        return base + (
            "这是多角度探讨的第 1 轮。从你的角度提出一个有洞见、可深入的科学/技术观点或切入点，"
            "给出关键依据或机制。≤160 字，实质、扎实，只提角度不下最终结论。")
    return base + (
        f"这是第 {round_no} 轮。先回顾你自己上一轮、再读另两位同伴的观点：\n"
        f"{_peer_ctx(peers or {}, seat.name)}\n\n"
        "任务：(1) 简短回应同伴——哪点最有价值 / 哪里有漏洞或张力（对事不对人，聚焦科学论点）；"
        "(2) 在你自己上一轮的思路 + 同伴的启发之上，推进或补充 1-2 个更有 insight、更可操作的角度。"
        "既承接自己、又回应他人，这才是讨论。保持发散（打开更多可能，不收敛成单一答案），"
        "务实、有依据、解决问题导向。≤170 字。")


# ----------------------------------------------------------------- run one round
def run_round(question: str, round_no: int,
              peers: dict[str, str] | None = None,
              seats_list: list[Seat] | None = None,
              timeout: float = 180.0) -> dict[str, str]:
    """Run one round: every seat answers in parallel. Returns {seat_name: text}."""
    sl = seats_list or seats()

    def _one(seat: Seat) -> tuple[str, str]:
        prompt = seat_prompt(seat, question, round_no, peers)
        try:
            out = llm.chat(seat.model, prompt, base_url=seat.base_url,
                           api_key=seat.api_key, timeout=timeout)
        except Exception as e:  # one seat failing must not kill the round
            out = f"[{seat.name} 未能作答: {e}]"
        return seat.name, out

    with ThreadPoolExecutor(max_workers=len(sl)) as ex:
        results = list(ex.map(_one, sl))
    return dict(results)


# ----------------------------------------------------------------- curator
_CURATOR_INSTRUCTIONS = (
    "把这些整合成一张『可能性地图』——这是给提问者的核心产出。严格按要求：\n"
    "1. 先接住问题：direct 用 1-2 句正面回应原问题，给提问者一个抓手（别一上来就发散）。\n"
    "2. 综述：overview 扎实总结多轮讨论的关键观点、相互启发、分歧，不遗漏（150-220 字）。\n"
    "3. 分支是核心干货：给 3-5 条彼此真正不同的探索分支（跨不同层次/视角：机制、方法、数据、"
    "应用、反直觉等，不要一个想法的多个变体），其中至少 1 条非常规/反直觉。"
    "这是开脑洞，全面打开可能性，不收敛、不替用户选。\n"
    "4. 每条分支字段：title(有信息量的洞见式标题，不是分类词) / bridge(这条路如何回应原问题) / "
    "insight(2-4 句干货：核心洞见+关键依据) / next(一句具体可操作的下一步) / premise / cost。\n"
    "5. 科学务实、抓 insight、解决问题导向；少用类比、不轻浮。more：一句『还可深挖』方向。\n"
    "只输出 JSON（无 markdown 代码块、无多余文字）：\n"
    '{"direct":"1-2句直接回应","overview":"综述",'
    '"branches":[{"title":"洞见式标题","bridge":"回到你的问题:…","insight":"干货2-4句",'
    '"next":"下一步","premise":"前提","cost":"代价"}],"more":"还可深挖(可选)"}'
)


def curator_prompt(question: str, transcript: list[tuple[int, dict[str, str]]]) -> str:
    parts = []
    for rnd, outs in transcript:
        for k, v in outs.items():
            if v:
                parts.append(f"[第{rnd}轮·{k}] {v}")
    ctx = "\n".join(parts)
    return (f"你是『三人行』的绘图者（curator）。{_PROSE}\n用户问题：{question}\n\n"
            f"以下是三位 AI 同学多轮发散讨论（开脑洞）的全部发言：\n{ctx}\n\n"
            + _CURATOR_INSTRUCTIONS)


def curate(question: str, transcript: list[tuple[int, dict[str, str]]],
           seats_list: list[Seat] | None = None,
           timeout: float = 220.0) -> dict:
    """Integrate the transcript into a possibility map dict. Retries once on
    malformed JSON, degrades gracefully to {'overview': raw_text}."""
    sl = seats_list or seats()
    model, base_url, api_key = curator_endpoint(sl)
    prompt = curator_prompt(question, transcript)
    raw = ""
    for _ in range(2):
        raw = llm.chat(model, prompt, base_url=base_url, api_key=api_key,
                       timeout=timeout, temperature=0.5)
        data = _extract_json(raw)
        if data and "branches" in data:
            return data
    return {"overview": raw.strip()[:1600], "branches": []}


# ----------------------------------------------------------------- full run (CLI/lib)
def discuss(question: str, rounds: int = 2,
            seats_list: list[Seat] | None = None) -> dict:
    """Run the full discussion and return {'transcript', 'map'}. Blocking."""
    sl = seats_list or seats()
    transcript: list[tuple[int, dict[str, str]]] = []
    peers: dict[str, str] = {}
    for r in range(1, rounds + 1):
        outs = run_round(question, r, peers, sl)
        transcript.append((r, outs))
        peers = outs
    pmap = curate(question, transcript, sl)
    return {"transcript": transcript, "map": pmap}


# ----------------------------------------------------------------- json helpers
def _extract_json(raw: str) -> dict | None:
    s = raw.strip()
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    # balanced-brace scan: robust to fences / leading or trailing prose
    i0 = s.find("{")
    if i0 < 0:
        return None
    depth = 0
    instr = False
    esc = False
    for i in range(i0, len(s)):
        c = s[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            instr = not instr
        elif not instr:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[i0:i + 1])
                    except Exception:
                        return None
    return None
