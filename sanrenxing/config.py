"""Seat configuration for 三人行 (sanrenxing).

Every seat is just an OpenAI-compatible chat endpoint: a (base_url, api_key,
model) triple plus a persona. Configure three seats + an optional curator
entirely through environment variables — no provider is hard-coded, so you can
mix any models that speak the OpenAI Chat Completions protocol (OpenAI,
Anthropic via a compatible proxy, Moonshot/Kimi, DeepSeek, local vLLM/Ollama…).

Env vars (N = 1, 2, 3):
  SEATn_NAME      short label shown in the UI            (default: Seat n)
  SEATn_MODEL     model id                               (required to enable seat)
  SEATn_BASE_URL  OpenAI-compatible base url             (default: OPENAI_BASE_URL
                                                          or https://api.openai.com/v1)
  SEATn_API_KEY   api key                                (default: OPENAI_API_KEY)
  SEATn_PERSONA   one-line persona steering the angle    (sensible default per seat)

Curator (writes the final possibility map) — falls back to Seat 1:
  CURATOR_MODEL / CURATOR_BASE_URL / CURATOR_API_KEY
"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://api.openai.com/v1"

# Default personas — three complementary lenses, not three of the same voice.
# The whole point of 三人行 is divergence, so the seats are seeded to disagree
# in *kind*: evidence vs. critique vs. the unconventional angle.
_DEFAULT_PERSONA = {
    1: "你是『证据席』，擅长检索证据、整合文献，给出关键依据与机制。",
    2: "你是『批判席』，严谨、批判性强，擅长识别技术伪影、混淆变量、隐含假设与方法学缺陷。",
    3: "你是『发散席』，擅长提出别人忽略的、非常规但有科学依据的角度、机制假说或被低估的变量。",
}
_DEFAULT_NAME = {1: "证据席", 2: "批判席", 3: "发散席"}


@dataclass
class Seat:
    sid: str          # stable id: "1" | "2" | "3"
    name: str         # display label
    persona: str
    model: str
    base_url: str
    api_key: str


def _seat_from_env(n: int) -> Seat | None:
    model = os.environ.get(f"SEAT{n}_MODEL", "").strip()
    if not model:
        return None
    base_url = (os.environ.get(f"SEAT{n}_BASE_URL")
                or os.environ.get("OPENAI_BASE_URL")
                or DEFAULT_BASE_URL).strip()
    api_key = (os.environ.get(f"SEAT{n}_API_KEY")
               or os.environ.get("OPENAI_API_KEY")
               or "").strip()
    name = os.environ.get(f"SEAT{n}_NAME", _DEFAULT_NAME[n]).strip()
    persona = os.environ.get(f"SEAT{n}_PERSONA", _DEFAULT_PERSONA[n]).strip()
    return Seat(str(n), name, persona, model, base_url, api_key)


def load_seats() -> list[Seat]:
    """Return the configured seats (1..3). Raises if none are configured."""
    seats = [s for s in (_seat_from_env(n) for n in (1, 2, 3)) if s]
    if not seats:
        raise RuntimeError(
            "No seats configured. Set at least SEAT1_MODEL (and SEAT2/SEAT3 for a "
            "real trio). Copy .env.example to .env and fill it in."
        )
    return seats


def curator_endpoint(seats: list[Seat]) -> tuple[str, str, str]:
    """(model, base_url, api_key) for the curator; defaults to Seat 1."""
    s1 = seats[0]
    model = os.environ.get("CURATOR_MODEL", s1.model).strip()
    base_url = (os.environ.get("CURATOR_BASE_URL") or s1.base_url).strip()
    api_key = (os.environ.get("CURATOR_API_KEY") or s1.api_key).strip()
    return model, base_url, api_key
