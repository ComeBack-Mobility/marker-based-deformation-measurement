# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Article-terminology plots for marker-pair deformation outputs."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt


def plot_deformation(rows: list[list], output_dir: Path, title: str, steps_per_trial: int) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 7.0), sharex=True)
    labels = [
        (9, 'Deformation normal to load direction, mm'),
        (10, 'Deformation in load direction, mm'),
    ]
    for ax, (col_idx, ylabel) in zip(axes, labels):
        for trial_id in sorted({int(r[1]) for r in rows}):
            trial_rows = [r for r in rows if int(r[1]) == trial_id]
            x = [r[3] for r in trial_rows]
            y = [r[col_idx] for r in trial_rows]
            ax.plot(x, y, marker='o', linewidth=1.6, label=f'Trial {trial_id}')
        ax.axhline(0, color='0.4', linewidth=0.8)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25)
    axes[-1].set_xlabel('Load, N')
    axes[0].set_title(title)
    axes[0].legend(frameon=False, ncol=2, fontsize=8)
    fig.tight_layout()
    out = output_dir / 'deformation_plot.png'
    fig.savefig(out, dpi=300)
    plt.close(fig)
    return out
