"""Thin OpenAI-compatible chat client — the only thing a seat needs.

Both a blocking call (`chat`) and a streaming generator (`chat_stream`) are
provided. Any endpoint that implements the OpenAI Chat Completions API works:
just point base_url/api_key/model at it.
"""
from __future__ import annotations

from typing import Iterator

try:
    from openai import OpenAI
except ImportError as e:  # pragma: no cover
    raise ImportError("pip install openai  (>=1.0)") from e


def _client(base_url: str, api_key: str) -> "OpenAI":
    # api_key may be empty for keyless local servers (vLLM/Ollama); send a dummy.
    return OpenAI(base_url=base_url, api_key=api_key or "sk-no-key")


def chat(model: str, prompt: str, *, base_url: str, api_key: str,
         timeout: float = 180.0, temperature: float = 0.7) -> str:
    """Blocking single-turn completion. Returns the assistant text."""
    client = _client(base_url, api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        timeout=timeout,
    )
    return (resp.choices[0].message.content or "").strip()


def chat_stream(model: str, prompt: str, *, base_url: str, api_key: str,
                timeout: float = 180.0, temperature: float = 0.7) -> Iterator[str]:
    """Yield text deltas as they arrive."""
    client = _client(base_url, api_key)
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        timeout=timeout,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
