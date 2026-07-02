# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Generate a single-image overview with all refined marker centers."""
from __future__ import annotations

from pathlib import Path

import cv2

from . import marker_engine as engine
from .io import iter_trial_images, load_yaml, resolve_path


def _draw_label(img, text: str, org: tuple[int, int], scale: float = 3.0) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(text, font, scale, 4)
    x, y = org
    pad_x, pad_y = 18, 14
    x0 = max(0, x - pad_x)
    y0 = max(0, y - th - pad_y)
    x1 = min(img.shape[1] - 1, x + tw + pad_x)
    y1 = min(img.shape[0] - 1, y + baseline + pad_y)
    overlay = img.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)
    cv2.rectangle(img, (x0, y0), (x1, y1), (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(img, text, org, font, scale, (0, 0, 0), 11, cv2.LINE_AA)
    cv2.putText(img, text, org, font, scale, (255, 255, 255), 4, cv2.LINE_AA)


def _draw_cross(img, x: float, y: float, size: int = 22) -> None:
    xi, yi = int(round(x)), int(round(y))
    cv2.line(img, (xi - size, yi), (xi + size, yi), (0, 0, 0), 8, cv2.LINE_AA)
    cv2.line(img, (xi, yi - size), (xi, yi + size), (0, 0, 0), 8, cv2.LINE_AA)
    cv2.line(img, (xi - size, yi), (xi + size, yi), (0, 0, 255), 4, cv2.LINE_AA)
    cv2.line(img, (xi, yi - size), (xi, yi + size), (0, 0, 255), 4, cv2.LINE_AA)


def _label_position(x: float, y: float, w: int, h: int, marker_id: int, dataset_name: str) -> tuple[int, int]:
    custom_offsets = {
        'bending_in_sagittal_plane': {
            1: (34, -34),
            2: (40, 72),
            3: (-100, 80),
            4: (-108, 82),
            5: (62, 14),
            6: (-112, -34),
        },
        'compression': {
            1: (-126, -32),
            2: (74, 84),
            3: (-84, -42),
            4: (-94, 76),
            5: (72, -26),
            6: (-128, 82),
            7: (56, -44),
        },
    }
    dx, dy = custom_offsets.get(dataset_name, {}).get(marker_id, (38, -30))
    return max(10, min(int(round(x + dx)), w - 145)), max(58, min(int(round(y + dy)), h - 18))


def build_marker_overview(repo_root: Path, config_path: Path, dataset_name: str) -> Path:
    cfg = load_yaml(config_path)
    dataset = cfg['examples'][dataset_name]
    raw_root = resolve_path(repo_root, dataset['raw_images'])
    first_pair_cfg = next(iter(dataset['marker_pairs'].values()))
    params = load_yaml(resolve_path(repo_root, first_pair_cfg['params']))
    engine.apply_params_from_dict(params)
    engine.previous_markers = None
    image_path = iter_trial_images(raw_root)[0]
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    rough = engine.detect_markers(image, track_previous=False)
    _, refined = engine.refine_centers_by_clustering(image, rough, selected_indices=None, preview=False, show_mask=False)
    out = image.copy()
    h, w = out.shape[:2]
    for idx, (x, y) in enumerate(refined, start=1):
        _draw_cross(out, x, y)
        lx, ly = _label_position(x, y, w, h, idx, dataset_name)
        _draw_label(out, str(idx), (lx, ly), scale=3.1)
    output_dir = repo_root / 'outputs' / 'marker_overview' / dataset_name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / 'all_markers_trial_0_load_0.png'
    cv2.imwrite(str(output_path), out)
    return output_path
