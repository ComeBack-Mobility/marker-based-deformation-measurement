# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Input/output helpers for the deformation measurement protocol."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _trial_sort_key(path: Path) -> tuple[int, str]:
    try:
        return int(path.name.split("_", 1)[1]), path.name
    except Exception:
        return 999999, path.name


def iter_trial_images(raw_images_root: Path) -> list[Path]:
    trial_dirs = sorted(
        [p for p in raw_images_root.iterdir() if p.is_dir() and p.name.lower().startswith("trial_")],
        key=_trial_sort_key,
    )
    if trial_dirs:
        images: list[Path] = []
        for trial_dir in trial_dirs:
            images.extend(sorted(p for p in trial_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}))
        return images
    return sorted(p for p in raw_images_root.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"})
