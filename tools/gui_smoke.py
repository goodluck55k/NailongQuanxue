"""Compatibility entry point for the upgraded V1.1 native smoke test."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.v11_smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
