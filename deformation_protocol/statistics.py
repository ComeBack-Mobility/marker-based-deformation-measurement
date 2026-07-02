# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Descriptive statistics for marker-pair deformation."""
from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import mean, stdev

from scipy.stats import t as student_t

from .io import load_yaml

TRIALS_FOR_ANALYSIS = {1, 2, 3}
DEFORMATION_COLUMNS = {
    'X': 'Deformation_X_mm',
    'Y': 'Deformation_Y_mm',
}


def _safe_float(value: object) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def _ci_half_width(values: list[float], confidence: float = 0.95) -> tuple[float, float | None, float | None]:
    avg = mean(values)
    n = len(values)
    if n < 2:
        return avg, None, None
    sd = stdev(values)
    alpha = 1.0 - confidence
    critical = student_t.ppf(1.0 - alpha / 2.0, n - 1)
    half_width = critical * sd / math.sqrt(n)
    return avg, sd, half_width


def _pair_output_dir(repo_root: Path, dataset_name: str, pair_cfg: dict[str, object]) -> Path:
    pair = pair_cfg['pair']
    label = str(pair_cfg['label']).lower().replace('-', '_').replace(' ', '_')
    return repo_root / 'outputs' / 'deformation_tables' / dataset_name / f'{label}_{pair[0]}_to_{pair[1]}'


def build_deformation_statistics(repo_root: Path, config_path: Path, confidence: float = 0.95) -> Path:
    """Write one combined mean/SD/CI table for marker-pair deformation.

    Trial 0 is excluded from these descriptive statistics. It remains present in
    per-image `distances.csv` tables for transparency and quality control.
    """
    cfg = load_yaml(config_path)
    summary_rows: list[dict[str, object]] = []

    for dataset_name, dataset in cfg['examples'].items():
        dataset_label = dataset.get('label', dataset_name)
        for _group_key, pair_cfg in dataset['marker_pairs'].items():
            output_dir = _pair_output_dir(repo_root, dataset_name, pair_cfg)
            csv_path = output_dir / 'distances.csv'
            if not csv_path.exists():
                continue
            rows = _read_rows(csv_path)
            marker_pair = f"{pair_cfg['pair'][0]}->{pair_cfg['pair'][1]}"
            group = pair_cfg['label']
            load_values = sorted({
                _safe_float(row.get('Load_N'))
                for row in rows
                if _safe_float(row.get('Load_N')) is not None
            })
            for load_n in load_values:
                for component, column in DEFORMATION_COLUMNS.items():
                    values: list[float] = []
                    for row in rows:
                        trial_id = _safe_float(row.get('TrialID'))
                        row_load = _safe_float(row.get('Load_N'))
                        if trial_id is None or int(trial_id) not in TRIALS_FOR_ANALYSIS:
                            continue
                        if row_load != load_n:
                            continue
                        value = _safe_float(row.get(column))
                        if value is not None:
                            values.append(value)
                    if not values:
                        continue
                    avg, sd, half_width = _ci_half_width(values, confidence=confidence)
                    summary_rows.append({
                        'Dataset': dataset_label,
                        'Group': group,
                        'MarkerPair': marker_pair,
                        'Component': component,
                        'Load_N': load_n,
                        'Trials used': '1-3',
                        'N': len(values),
                        'Mean (mm)': avg,
                        'SD (mm)': sd,
                        'CI level': confidence,
                        'CI lower (mm)': None if half_width is None else avg - half_width,
                        'CI upper (mm)': None if half_width is None else avg + half_width,
                        'CI half-width (mm)': half_width,
                    })

    output_dir = repo_root / 'outputs' / 'deformation_statistics'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_csv = output_dir / 'deformation_mean_ci.csv'
    fieldnames = [
        'Dataset', 'Group', 'MarkerPair', 'Component', 'Load_N', 'Trials used', 'N',
        'Mean (mm)', 'SD (mm)', 'CI level', 'CI lower (mm)', 'CI upper (mm)', 'CI half-width (mm)'
    ]
    with output_csv.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)
    return output_csv
