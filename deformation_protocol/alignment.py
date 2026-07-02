# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Rigid in-plane image alignment for bending image series."""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

import cv2
import numpy as np

from .io import iter_trial_images, load_yaml, resolve_path


def _load_gray(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(path)
    return image


def _roi(image: np.ndarray, roi_xywh):
    if not roi_xywh:
        return image
    x, y, w, h = [int(v) for v in roi_xywh]
    return image[y:y+h, x:x+w]


def _maybe_blur(image: np.ndarray, kernel: int) -> np.ndarray:
    if kernel and kernel > 1:
        if kernel % 2 == 0:
            kernel += 1
        return cv2.GaussianBlur(image, (kernel, kernel), 0)
    return image


def _confirm_overwrite(path: Path) -> bool:
    try:
        answer = input(f"{path} already exists. Overwrite it? [y/N]: " ).strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def align_dataset(
    repo_root: Path,
    config_path: Path,
    dataset_name: str,
    write_images: bool = False,
    save_roi_info: bool = False,
    overwrite_existing: bool | None = None,
) -> Path:
    cfg = load_yaml(config_path)
    dataset = cfg['examples'][dataset_name]
    alignment_cfg = dataset.get('alignment', {})
    if not alignment_cfg.get('enabled', False):
        raise ValueError(f'Alignment is disabled for dataset: {dataset_name}')
    raw_root = resolve_path(repo_root, dataset['raw_images'])
    roi_xywh = alignment_cfg.get('roi_xywh')
    threshold = float(alignment_cfg.get('ecc_threshold', 0.99))
    iterations = int(alignment_cfg.get('ecc_iterations', 200))
    epsilon = float(alignment_cfg.get('ecc_epsilon', 1e-6))
    blur_kernel = int(alignment_cfg.get('blur_kernel', 0))
    images = iter_trial_images(raw_root)
    load_steps = dataset['load_steps']
    steps_per_trial = len(load_steps)
    output_root = repo_root / 'outputs' / 'aligned_images' / dataset_name
    output_root.mkdir(parents=True, exist_ok=True)

    if save_roi_info and alignment_cfg.get('roi_selection_output'):
        roi_src = resolve_path(repo_root, alignment_cfg['roi_selection_output'])
        roi_dst = output_root / 'roi_selection_output'
        should_copy_roi = True
        if roi_dst.exists():
            should_overwrite = overwrite_existing if overwrite_existing is not None else _confirm_overwrite(roi_dst)
            if should_overwrite:
                shutil.rmtree(roi_dst)
            else:
                should_copy_roi = False
                print(f'Keeping existing ROI-selection output: {roi_dst}')
        if should_copy_roi:
            shutil.copytree(roi_src, roi_dst, ignore=lambda _dir, names: {'desktop.ini', '__pycache__'} & set(names))

    rows = []
    for start in range(0, len(images), steps_per_trial):
        trial_images = images[start:start + steps_per_trial]
        if not trial_images:
            continue
        trial_id = start // steps_per_trial
        reference_path = trial_images[0]
        reference_roi = _maybe_blur(_roi(_load_gray(reference_path), roi_xywh), blur_kernel)
        trial_out = output_root / f'trial_{trial_id}'
        if write_images:
            trial_out.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(trial_out / reference_path.name), cv2.imread(str(reference_path)))
        for step_idx, current_path in enumerate(trial_images):
            current_roi = _maybe_blur(_roi(_load_gray(current_path), roi_xywh), blur_kernel)
            warp = np.eye(2, 3, dtype=np.float32)
            ecc = 1.0 if step_idx == 0 else None
            status = 'reference' if step_idx == 0 else 'ok'
            if step_idx != 0:
                try:
                    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, iterations, epsilon)
                    ecc, warp = cv2.findTransformECC(reference_roi, current_roi, warp, cv2.MOTION_EUCLIDEAN, criteria)
                    if ecc < threshold:
                        status = 'below_threshold'
                except cv2.error as exc:
                    status = f'failed: {exc}'
                    ecc = None
            if write_images and step_idx != 0 and ecc is not None:
                color = cv2.imread(str(current_path))
                aligned = cv2.warpAffine(color, warp, (color.shape[1], color.shape[0]), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)
                cv2.imwrite(str(trial_out / current_path.name), aligned)
            rows.append({'trial_id': trial_id, 'load_step_id': step_idx, 'load': load_steps[step_idx], 'image': current_path.name, 'reference_image': reference_path.name, 'ecc': ecc, 'status': status, 'warp_00': warp[0,0], 'warp_01': warp[0,1], 'warp_02': warp[0,2], 'warp_10': warp[1,0], 'warp_11': warp[1,1], 'warp_12': warp[1,2]})
    manifest = output_root / 'alignment_manifest.csv'
    with manifest.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ['trial_id'])
        writer.writeheader()
        writer.writerows(rows)
    return manifest
