"""Shared pytest setup: make the project layout importable without packaging.

Run the suite from the repo root:  python -m pytest
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"

for p in (str(REPO), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)
