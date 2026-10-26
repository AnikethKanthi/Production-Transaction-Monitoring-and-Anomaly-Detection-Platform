"""Run from the repository root: python scripts/evaluate_threshold.py."""

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

if __name__ == "__main__":
    evaluation = importlib.import_module("app.ml.thresholds")
    result = evaluation.run_evaluation(ROOT)
    print(
        json.dumps(
            {
                "threshold": result["configuration"]["threshold"],
                "holdout": result["holdout"],
            },
            indent=2,
        )
    )
