from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))
training = importlib.import_module("app.ml.train")


if __name__ == "__main__":
    training.print_result(training.train(ROOT))
