from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib


def save_model(model: Any, metadata: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    version = metadata["model_version"]
    model_path = output_dir / f"{version}.joblib"
    metadata_path = output_dir / f"{version}.metadata.json"
    joblib.dump(model, model_path, compress=3)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return model_path, metadata_path


def load_model(model_path: Path) -> Any:
    return joblib.load(model_path)
