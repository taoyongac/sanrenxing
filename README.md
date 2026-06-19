# 三人行 · sanrenxing

> 三人行，必有我师。 — *Among any three, one can be my teacher.*

**Divergent, open-mind AI discussion.** Three AI seats with *complementary* lenses
debate a question — not to vote a winner, but to **open the possibility space**.
Each round, every seat reacts to the others (spark / tension / gap) and *generates*
new angles. A curator then lays out a **possibility map** of distinct branches —
each with its premise, cost, and concrete next step. **You choose the path.**

Provider-agnostic: every seat is just an OpenAI-compatible endpoint, so mix any
models you like (OpenAI, DeepSeek, Moonshot/Kimi, a local vLLM/Ollama, …).

Ships in three forms:
- **MCP server** — `trio_round` + `fanout` tools for any MCP host (Claude Code, etc.)
- **Web demo** — a zero-framework single page with live streaming (`web/`)
- **CLI / library** — `python -m sanrenxing "…"` or `import sanrenxing`

---

## Why divergent, not convergent

Most "multi-agent debate" tools push agents to argue until they **converge** on one
answer. 三人行 does the opposite on purpose:

| | convergent debate | 三人行 (divergent) |
|---|---|---|
| goal | pick the winner | open more branches |
| seats | same lens, vote | **complementary** lenses |
| cross-talk | rebut / eliminate | **yes-and** / generate |
| output | one recommendation | a **map**, human picks |

Convergence is treated as a *smell*. The three default seats are seeded to disagree
**in kind** — evidence (证据席), critique (批判席), and the unconventional angle
(发散席) — so the discussion stays heterogeneous. Convergent mode (vote/rank) is
opt-in: just ask the host to decide.

## Architecture

```
question
   │
   ├─► Seat 1 ─┐
   ├─► Seat 2 ─┼─ round 1 (parallel, distinct angles)
   ├─► Seat 3 ─┘
   │      ▼  each seat reads the others' prior round, reacts + branches
   ├─► round 2 … N  (mutual-evaluation = the interaction engine)
   │
   └─► Curator ─► possibility map { direct, overview, branches[premise/cost/next], more }
```

- `sanrenxing/config.py` — load seats from env (`SEATn_*`).
- `sanrenxing/llm.py` — minimal OpenAI-compatible client (block + stream).
- `sanrenxing/discussion.py` — seat prompts, rounds, curator. **The methodology.**
- `mcp_server/server.py` — `trio_round`, `fanout` MCP tools.
- `web/server.py` + `web/static/index.html` — stdlib HTTP + SSE demo.

## Quick start

```bash
git clone https://github.com/taoyongac/sanrenxing
cd sanrenxing
pip install -r requirements.txt
cp .env.example .env        # then edit: set SEAT1/2/3 model + base_url + api_key
```

**CLI**
```bash
set -a; source .env; set +a
python -m sanrenxing "短端粒在衰老中是刹车还是油门？"
python -m sanrenxing -r 3 "your question"     # 3 rounds
```

**Web demo**
```bash
set -a; source .env; set +a
python web/server.py        # → http://127.0.0.1:8030
```

**MCP server** — add to your host config (e.g. Claude Code `~/.claude.json`),
making sure the `SEATn_*` vars are in its environment:
```json
{
  "mcpServers": {
    "sanrenxing": {
      "command": "python",
      "args": ["/abs/path/to/sanrenxing/mcp_server/server.py"],
      "env": { "SEAT1_MODEL": "gpt-4o", "SEAT1_API_KEY": "sk-...",
               "SEAT2_MODEL": "deepseek-chat", "SEAT2_BASE_URL": "https://api.deepseek.com", "SEAT2_API_KEY": "sk-...",
               "SEAT3_MODEL": "moonshot-v1-32k", "SEAT3_BASE_URL": "https://api.moonshot.cn/v1", "SEAT3_API_KEY": "sk-..." }
    }
  }
}
```
Then the host can call `trio_round(seat1_prompt, seat2_prompt, seat3_prompt, round_num)`
once per round (embedding the prior transcript into each prompt for rounds 2+), and
`fanout(tasks)` for parallel independent angles. **The host stays the arbiter** —
the tools never merge or pick a winner.

## Configuration

All via environment (see `.env.example`). Per seat `n ∈ {1,2,3}`:

| var | meaning | default |
|---|---|---|
| `SEATn_MODEL` | model id (**required to enable the seat**) | — |
| `SEATn_BASE_URL` | OpenAI-compatible base url | `OPENAI_BASE_URL` or OpenAI |
| `SEATn_API_KEY` | api key | `OPENAI_API_KEY` |
| `SEATn_NAME` | display label | 证据席 / 批判席 / 发散席 |
| `SEATn_PERSONA` | one-line lens steering the angle | sensible per-seat default |

`CURATOR_MODEL/BASE_URL/API_KEY` override the curator (defaults to Seat 1). The web
demo also reads `SANRENXING_HOST/PORT/ROUNDS` and optional `SANRENXING_USER/PASS`
(HTTP Basic Auth for a shared deployment).

## Notes

- Seats are **pure reasoning** (no tools/web). Embed any needed facts in the
  question; tool/search augmentation is intentionally left as an extension.
- A single global lock serializes web discussions (concurrency = 1) so a shared
  demo never piles up parallel runs.

---

## From the Tao Lab

Built and used at **[Tao Lab](https://taolab.tail0ea5ac.ts.net/), School of Life
Sciences, Yunnan University** (云南大学 · 陶勇课题组) — epigenetics, aging, cancer,
and **AI-for-Science**. 三人行 is one of the lab's open tools for turning a hard
scientific question into a map of testable directions.

🔗 **Lab site:** https://taolab.tail0ea5ac.ts.net/

## License

MIT © 2026 Yong Tao (Tao Lab, Yunnan University). See [LICENSE](LICENSE).
