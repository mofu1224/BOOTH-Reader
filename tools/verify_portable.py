"""Compatibility entry point for complete Git clone portability verification."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.verify_clone import main

if __name__ == "__main__":
    raise SystemExit(main())
