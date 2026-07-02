# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Command-line interface for the deformation measurement protocol."""
from __future__ import annotations

import argparse
from pathlib import Path

from .alignment import align_dataset
from .marker_detection import run_dataset
from .marker_overview import build_marker_overview
from .statistics import build_deformation_statistics


def repo_root_from_config(config: Path) -> Path:
    return config.resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Bone 2 deformation measurement protocol CLI')
    sub = parser.add_subparsers(dest='command', required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--config', type=Path, default=Path('configs/bone2_example_config.yaml'))
    common.add_argument('--dataset', choices=['bending_in_sagittal_plane', 'compression'])
    align = sub.add_parser('align', parents=[common], help='Run rigid ECC alignment for a dataset')
    align.add_argument('--write-images', action='store_true', help='Write aligned images to outputs/aligned_images')
    align.add_argument('--save-roi-info', action='store_true', help='Copy bundled ROI-selection outputs into the alignment output folder')
    align.add_argument('--overwrite-existing', action='store_true', help='Overwrite existing auxiliary alignment outputs without prompting')
    run = sub.add_parser('run', parents=[common], help='Calculate marker-pair deformation for one dataset')
    run.add_argument('--debug-images', action='store_true', help='Write annotated marker quality-control images')
    run.add_argument('--plots', action='store_true', help='Write deformation plots')
    run_all = sub.add_parser('run-all', help='Run deformation calculation for all configured datasets')
    run_all.add_argument('--config', type=Path, default=Path('configs/bone2_example_config.yaml'))
    run_all.add_argument('--debug-images', action='store_true')
    run_all.add_argument('--plots', action='store_true')
    overview = sub.add_parser('marker-overview', parents=[common], help='Generate one all-marker overview image for a dataset')
    overview_all = sub.add_parser('marker-overview-all', help='Generate all-marker overview images for all configured datasets')
    overview_all.add_argument('--config', type=Path, default=Path('configs/bone2_example_config.yaml'))
    stats = sub.add_parser('stats', help='Calculate combined mean, SD, and 95%% CI for marker-pair deformation')
    stats.add_argument('--config', type=Path, default=Path('configs/bone2_example_config.yaml'))
    stats.add_argument('--confidence', type=float, default=0.95, help='Confidence level for Student t intervals')
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = args.config.resolve()
    repo_root = repo_root_from_config(config)
    if args.command == 'align':
        if args.dataset is None:
            parser.error('--dataset is required for align')
        try:
            manifest = align_dataset(
                repo_root,
                config,
                args.dataset,
                write_images=args.write_images,
                save_roi_info=args.save_roi_info,
                overwrite_existing=True if args.overwrite_existing else None,
            )
        except ValueError as exc:
            parser.exit(1, f'{exc}\n')
        print(f'Alignment manifest: {manifest}')
        return 0
    if args.command == 'run':
        if args.dataset is None:
            parser.error('--dataset is required for run')
        outputs = run_dataset(repo_root, config, args.dataset, debug_images=args.debug_images, plots=args.plots)
        for output in outputs:
            print(f'Wrote: {output}')
        return 0
    if args.command == 'run-all':
        for dataset_name in ['bending_in_sagittal_plane', 'compression']:
            outputs = run_dataset(repo_root, config, dataset_name, debug_images=args.debug_images, plots=args.plots)
            for output in outputs:
                print(f'Wrote: {output}')
        return 0
    if args.command == 'marker-overview':
        if args.dataset is None:
            parser.error('--dataset is required for marker-overview')
        output = build_marker_overview(repo_root, config, args.dataset)
        print(f'Wrote: {output}')
        return 0
    if args.command == 'marker-overview-all':
        for dataset_name in ['bending_in_sagittal_plane', 'compression']:
            output = build_marker_overview(repo_root, config, dataset_name)
            print(f'Wrote: {output}')
        return 0
    if args.command == 'stats':
        output = build_deformation_statistics(repo_root, config, confidence=args.confidence)
        print(f'Wrote: {output}')
        return 0
    parser.error(f'Unknown command: {args.command}')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())

