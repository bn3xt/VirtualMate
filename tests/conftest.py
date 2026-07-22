from __future__ import annotations

import sys
from pathlib import Path


PRODUCT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PRODUCT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TESTS_ROOT = PRODUCT_ROOT / "tests"
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))
