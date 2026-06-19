"""三人行 (sanrenxing) — divergent multi-seat AI discussion.

Three complementary AI seats open the possibility space around a question; a
curator lays out a map of distinct branches. The human chooses. Provider-agnostic
(any OpenAI-compatible endpoint).
"""
from .config import Seat, load_seats
from .discussion import curate, discuss, run_round, seat_prompt

__all__ = ["Seat", "load_seats", "discuss", "run_round", "curate", "seat_prompt"]
__version__ = "0.1.0"
