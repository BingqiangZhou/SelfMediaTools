from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pipeline_main import _build_parser, _merge_args, _validate_args, main, run

__all__ = [
    "main",
    "run",
    "_build_parser",
    "_merge_args",
    "_validate_args",
]


if __name__ == "__main__":
    main()
