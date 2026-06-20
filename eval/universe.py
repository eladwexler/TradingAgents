"""Resolve the benchmark universe from the live watchlist — NAMES ONLY.

Reads the subdirectory names under analyzed-stocks/ (read-only) so the benchmark
covers exactly the names the platform tracks, without importing any decision
content (which would risk lookahead leakage from the current theses).
"""
from __future__ import annotations

import os
from typing import List


def load_universe(repo_root: str, exclude: List[str]) -> List[str]:
    base = os.path.join(repo_root, "analyzed-stocks")
    if not os.path.isdir(base):
        return []
    excl = {e.upper() for e in (exclude or [])}
    names = [
        d for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d)) and not d.startswith(".")
    ]
    return sorted(t for t in names if t.upper() not in excl)
