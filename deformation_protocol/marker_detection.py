# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Marker detection, center refinement, deformation calculation, and export."""
from __future__ import annotations

import csv
from pathlib import Path

import cv2

from . import marker_engine as engine
from .io import iter_trial_images, load_yaml, resolve_path
from .plotting import plot_deformation

TRIALS_FOR_ANALYSIS_SHIFT = {1, 2, 3}

CSV_COLUMNS = [
    'Image', 'TrialID', 'LoadStepID', 'Load_N', 'MarkerPair',
    'd_X_px', 'd_Y_px',
    'd_X_mm', 'd_Y_mm',
    'Deformation_from_unloaded_X_mm',
    'Deformation_from_unloaded_Y_mm',
    'Deformation_from_first_loaded_X_mm',
    'Deformation_from_first_loaded_Y_mm',
    'Deformation_X_mm',
    'Deformation_Y_mm',
]


def _write_csv(rows: list[dict[str, object]], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _old_plot_rows(rows: list[dict[str, object]]) -> list[list[object]]:
    return [[row[column] for column in CSV_COLUMNS] for row in rows]


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def add_analysis_deformation(rows: list[dict[str, object]]) -> None:
    """Add final analysis deformation columns in-place.

    The raw reference is the Trial 1 / Load 0 marker-pair distance. Values are
    calculated from dX/dY directly, not from previously derived deformation
    columns. The final curve is shifted using a stored first-loaded-step mean so
    the mean first loaded step across trials 1-3 is zero. Trial 0 is still calculated in these columns, but the
    shift value is derived only from trials 1-3.
    """
    for row in rows:
        row['Deformation_X_mm'] = None
        row['Deformation_Y_mm'] = None

    reference = next(
        (
            row for row in rows
            if row.get('TrialID') == 1
            and row.get('Load_N') == 0
            and row.get('d_X_mm') is not None
            and row.get('d_Y_mm') is not None
        ),
        None,
    )
    if reference is None:
        return

    ref_x = float(reference['d_X_mm'])
    ref_y = float(reference['d_Y_mm'])

    raw_referenced: list[tuple[dict[str, object], float, float]] = []
    for row in rows:
        dx_mm = row.get('d_X_mm')
        dy_mm = row.get('d_Y_mm')
        if dx_mm is None or dy_mm is None:
            continue
        adj_x = float(dx_mm) - ref_x
        adj_y = float(dy_mm) - ref_y
        raw_referenced.append((row, adj_x, adj_y))

    positive_loads = sorted({float(row['Load_N']) for row in rows if row.get('Load_N') is not None and float(row['Load_N']) > 0})
    if not positive_loads:
        return
    first_loaded = positive_loads[0]

    shift_x = _mean([
        adj_x for row, adj_x, _adj_y in raw_referenced
        if row.get('TrialID') in TRIALS_FOR_ANALYSIS_SHIFT and float(row.get('Load_N')) == first_loaded
    ])
    shift_y = _mean([
        adj_y for row, _adj_x, adj_y in raw_referenced
        if row.get('TrialID') in TRIALS_FOR_ANALYSIS_SHIFT and float(row.get('Load_N')) == first_loaded
    ])
    if shift_x is None or shift_y is None:
        return

    for row, adj_x, adj_y in raw_referenced:
        row['Deformation_X_mm'] = adj_x - shift_x
        row['Deformation_Y_mm'] = adj_y - shift_y


def _empty_row(image_name: str, trial_idx: int, step_idx: int, load_n: int | float, marker_pair: str) -> dict[str, object]:
    return {
        'Image': image_name,
        'TrialID': trial_idx,
        'LoadStepID': step_idx,
        'Load_N': load_n,
        'MarkerPair': marker_pair,
        'd_X_px': None,
        'd_Y_px': None,
        'd_X_mm': None,
        'd_Y_mm': None,
        'Deformation_from_unloaded_X_mm': None,
        'Deformation_from_unloaded_Y_mm': None,
        'Deformation_from_first_loaded_X_mm': None,
        'Deformation_from_first_loaded_Y_mm': None,
        'Deformation_X_mm': None,
        'Deformation_Y_mm': None,
    }


def process_marker_pair(image_paths: list[Path], params_path: Path, marker_pair: tuple[int, int], load_steps: list[int | float], output_dir: Path, debug_images: bool = False, plots: bool = False) -> Path:
    params = load_yaml(params_path)
    engine.apply_params_from_dict(params)
    engine.load_arr = list(load_steps)
    engine.previous_markers = None
    output_dir.mkdir(parents=True, exist_ok=True)
    engine.reset_warning_log(str(output_dir))
    debug_dir = output_dir / 'debug_images'
    if debug_images:
        debug_dir.mkdir(parents=True, exist_ok=True)

    m1, m2 = marker_pair
    pair_label = f'{m1}->{m2}'
    selected = [m1 - 1, m2 - 1]
    steps_per_trial = len(load_steps)
    rows: list[dict[str, object]] = []
    trial0_dx = trial0_dy = trial1_dx = trial1_dy = None

    for idx, image_path in enumerate(image_paths):
        step_idx = idx % steps_per_trial
        trial_idx = idx // steps_per_trial
        load_n = load_steps[step_idx]
        engine.current_warning_image_path = str(image_path)
        img = cv2.imread(str(image_path))
        if img is None:
            rows.append(_empty_row(image_path.name, trial_idx, step_idx, load_n, pair_label))
            continue
        rough = engine.detect_markers(img)
        annotated, refined = engine.refine_centers_by_clustering(img, rough, selected_indices=selected, preview=False)
        if len(refined) == 2:
            (x1, y1), (x2, y2) = refined
            dx, dy = x2 - x1, y2 - y1
            ex, ey = dx / engine.calib_val, dy / engine.calib_val
        else:
            dx = dy = ex = ey = None
        if step_idx == 0:
            trial0_dx, trial0_dy = dx, dy
            trial1_dx = trial1_dy = None
        if step_idx == 1 and trial1_dx is None:
            trial1_dx, trial1_dy = dx, dy
        if ex is not None and trial0_dx is not None:
            def0_x = (dx - trial0_dx) / engine.calib_val
            def0_y = (dy - trial0_dy) / engine.calib_val
        else:
            def0_x = def0_y = None
        if ex is not None and trial1_dx is not None:
            def1_x = (dx - trial1_dx) / engine.calib_val
            def1_y = (dy - trial1_dy) / engine.calib_val
        else:
            def1_x = def1_y = None
        row = _empty_row(image_path.name, trial_idx, step_idx, load_n, pair_label)
        row.update({
            'd_X_px': dx,
            'd_Y_px': dy,
            'd_X_mm': ex,
            'd_Y_mm': ey,
            'Deformation_from_unloaded_X_mm': def0_x,
            'Deformation_from_unloaded_Y_mm': def0_y,
            'Deformation_from_first_loaded_X_mm': def1_x,
            'Deformation_from_first_loaded_Y_mm': def1_y,
        })
        rows.append(row)
        if debug_images:
            cv2.imwrite(str(debug_dir / image_path.name), annotated)

    add_analysis_deformation(rows)
    output_csv = output_dir / 'distances.csv'
    _write_csv(rows, output_csv)
    if plots:
        plot_deformation(_old_plot_rows(rows), output_dir, f'Marker pair {m1}->{m2}', steps_per_trial)
    engine.flush_warning_log()
    return output_csv


def run_dataset(repo_root: Path, config_path: Path, dataset_name: str, debug_images: bool = False, plots: bool = False) -> list[Path]:
    cfg = load_yaml(config_path)
    dataset = cfg['examples'][dataset_name]
    raw_root = resolve_path(repo_root, dataset['raw_images'])
    image_paths = iter_trial_images(raw_root)
    output_paths: list[Path] = []
    base = repo_root / 'outputs' / 'deformation_tables' / dataset_name
    for group_key, pair_cfg in dataset['marker_pairs'].items():
        pair = tuple(pair_cfg['pair'])
        params_path = resolve_path(repo_root, pair_cfg['params'])
        label = pair_cfg['label'].lower().replace('-', '_').replace(' ', '_')
        pair_name = f'{label}_{pair[0]}_to_{pair[1]}'
        output_dir = base / pair_name
        output_paths.append(process_marker_pair(image_paths, params_path, pair, dataset['load_steps'], output_dir, debug_images=debug_images, plots=plots))
    return output_paths
