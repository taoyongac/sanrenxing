"""CLI: run a full 三人行 discussion from the terminal.

    python -m sanrenxing "your question here"          # 2 rounds (default)
    python -m sanrenxing -r 3 "your question here"     # 3 rounds
"""
from __future__ import annotations

import argparse

from .discussion import discuss


def main() -> None:
    ap = argparse.ArgumentParser(prog="sanrenxing",
                                 description="Divergent 3-seat AI discussion.")
    ap.add_argument("question", help="the question to explore")
    ap.add_argument("-r", "--rounds", type=int, default=2,
                    help="seat discussion rounds (default 2)")
    args = ap.parse_args()

    result = discuss(args.question, rounds=args.rounds)
    for rnd, outs in result["transcript"]:
        print(f"\n══════ 第 {rnd} 轮 ══════")
        for name, txt in outs.items():
            print(f"\n【{name}】\n{txt}")

    m = result["map"]
    print("\n══════ 可能性地图 ══════")
    if m.get("direct"):
        print(f"\n▸ {m['direct']}")
    if m.get("overview"):
        print(f"\n{m['overview']}")
    for i, b in enumerate(m.get("branches", [])):
        letter = "ABCDE"[i] if i < 5 else str(i + 1)
        print(f"\n[{letter}] {b.get('title','')}")
        if b.get("bridge"):
            print(f"    ↳ {b['bridge']}")
        print(f"    {b.get('insight','')}")
        if b.get("next"):
            print(f"    下一步 · {b['next']}")
        print(f"    前提 · {b.get('premise','—')} ｜ 代价 · {b.get('cost','—')}")
    if m.get("more"):
        print(f"\n还可深挖 · {m['more']}")


if __name__ == "__main__":
    main()
