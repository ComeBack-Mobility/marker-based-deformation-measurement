# Marker-Based Deformation Measurement

This repository contains source-available research software for marker-based photogrammetric measurement of lower-limb fracture-fixation deformation. It is aligned with the article section **2.3 Deformations measurement protocol** and contains only the Bone 2 example.

The repository name, **marker-based-deformation-measurement**, reflects the broader use of the workflow. Although the included example is from fracture-fixation biomechanics, the same approach can be adapted to other experimental fields where deformation is quantified from sparse marker pairs in sequential images rather than from full-field surface strain.

![Figure X workflow](docs/figure_x_reference/Fig%20X%20Workflow.png)

## License and Use

The source code is available under the PolyForm Noncommercial License 1.0.0. Academic, educational, public research, personal research, review, and reproducibility uses are permitted under that license.

Commercial use is not permitted under the public repository license. Commercial use requires a separate written agreement with the authors. See `COMMERCIAL_LICENSE.md`.

The Bone 2 images and derived example data are provided for non-commercial research, review, and reproducibility only. See `DATA_NOTICE.md`.

If you use this repository, please cite this repository using `CITATION.cff`. After the associated article is accepted and published, please cite both the repository and the article.

## Funding And Affiliations

This work was funded by ComeBack Mobility.

Author affiliation: Frantsevich Institute for Problems of Materials Science National Academy of Sciences of Ukraine; ComeBack Mobility.

## Article Terminology Used In This Repository

- `bending_in_sagittal_plane`: bending in sagittal plane.
- `compression`: compression.
- `normal_to_load_direction`: former internal `X` axis.
- `in_load_direction`: former internal `Y` axis.
- `Whole-bone`: marker pair describing construct-level deformation.
- `Fracture zone`: marker pair spanning the osteotomy region.

## Included Bone 2 Example

| Dataset | Group | Marker pair |
|---|---|---|
| Bending in sagittal plane | Whole-bone | 2->6 |
| Bending in sagittal plane | Fracture zone | 3->5 |
| Compression | Whole-bone | 4->7 |
| Compression | Fracture zone | 6->1 |

Raw images are separated by loading series in `raw_images/trial_*` folders. Trial 0 is a stabilizational loading series performed to remove unnecessary gaps between loading interfaces. Trial 0 is retained in per-image outputs for transparency and quality control, but it is not used for deformation mean/CI calculation. Only the first photographs of this image series were used for calibration purposes; in bending, the trial 0 load 0 frames were also used as reference/provenance images for the alignment step.

## Installation

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Reproduce The Example Outputs

Generate deformation tables only:

```powershell
python -m deformation_protocol.cli run-all --config configs/bone2_example_config.yaml
```

Generate deformation tables, quality-control/debug images, and plots:

```powershell
python -m deformation_protocol.cli run-all --config configs/bone2_example_config.yaml --debug-images --plots
```

Run bending in sagittal plane only:

```powershell
python -m deformation_protocol.cli run --config configs/bone2_example_config.yaml --dataset bending_in_sagittal_plane --debug-images --plots
```

Run compression only:

```powershell
python -m deformation_protocol.cli run --config configs/bone2_example_config.yaml --dataset compression --debug-images --plots
```

Run bending image alignment and write aligned images. This is intentionally available only for `bending_in_sagittal_plane`; compression does not require alignment. The fixed ROI comes from `roi_xywh` in the config, so the ROI-reference folder is provenance only:

```powershell
python -m deformation_protocol.cli align --config configs/bone2_example_config.yaml --dataset bending_in_sagittal_plane --write-images --save-roi-info --overwrite-existing
```


Generate one image with all refined markers for both load types:

```powershell
python -m deformation_protocol.cli marker-overview-all --config configs/bone2_example_config.yaml
```

Calculate one combined mean/SD/95% CI table from final marker-pair deformation values. Trial 0 is excluded from this table; trials 1-3 are used:

```powershell
python -m deformation_protocol.cli stats --config configs/bone2_example_config.yaml
```


## Detailed Documentation

- [Marker detection, center refinement, and marker-pair YAML parameters](docs/marker_detection_and_refinement.md)
- [Bending image alignment procedure and alignment YAML parameters](docs/alignment_procedure.md)
## Workflow Stages And Algorithms

1. **Image ordering**: `deformation_protocol.io.iter_trial_images` reads images trial-by-trial from `raw_images/trial_*` folders and matches them to the load sequence in the config.
2. **Bending image alignment**: `deformation_protocol.alignment` performs rigid in-plane ECC registration with translation and rotation only. The Bone 2 example uses the fixed ROI defined by `roi_xywh` in `configs/bone2_example_config.yaml`. ROI provenance files are stored in `example_data/Bone_2/bending_in_sagittal_plane/roi_reference/`; `--save-roi-info` copies these metadata files into the alignment output. If the ROI output already exists, the command prompts before overwriting; use `--overwrite-existing` for non-interactive reruns. The manifest stores ECC values and transformation matrices. Alignment is disabled for compression.
3. **Calibration**: each marker-pair `params.yaml` stores the pixel/mm calibration value obtained from the caliper image.
4. **Marker candidate detection**: `deformation_protocol.marker_engine.detect_markers` segments green marker centers in HSV color space and tracks marker order between frames.
5. **Marker center refinement**: `deformation_protocol.marker_engine.refine_centers_by_clustering` extracts dark pixels around each candidate, clusters marker-line pixels, fits line directions, and uses the line intersection as the refined marker center.
6. **Pairwise deformation calculation**: `deformation_protocol.marker_detection.process_marker_pair` calculates signed pair distances, deformation relative to the unloaded image, deformation relative to the first loaded step, and final marker-pair deformation columns `Deformation_X_mm` and `Deformation_Y_mm`. Final marker-pair deformation is calculated directly from signed `dX`/`dY` marker-pair distances using Trial 1 at 0 N as the common reference and then shifted so the mean first loaded step across trials 1-3 is zero.
7. **Quality control**: enabled with `--debug-images`; annotated marker images and warnings are written inside each marker-pair output folder, for example `outputs/deformation_tables/.../debug_images/`.
8. **Plotting and export**: enabled with `--plots`; deformation plots and `distances.csv` are written to `outputs/`.

## Output Locations

```text
outputs/deformation_tables/
outputs/deformation_tables/.../debug_images/
outputs/aligned_images/
outputs/deformation_statistics/
```

All CSV component columns use generic `X` and `Y` names for broader reuse. In this Bone 2 example, `X` corresponds to deformation normal to the load direction and `Y` corresponds to deformation in the load direction.

## Important Note

This repository is **source-available**, not OSI open-source, because commercial use is restricted.

Marker measurement commands use the trial images configured under `raw_images`; they do not automatically switch to `outputs/aligned_images`.



