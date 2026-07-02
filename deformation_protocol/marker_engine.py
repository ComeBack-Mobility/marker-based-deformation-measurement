# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Internal algorithm engine refactored from the original research script.

from skimage.morphology import skeletonize
import cv2
import numpy as np
import matplotlib.pyplot as plt
import math
from sklearn.cluster import AgglomerativeClustering
from itertools import combinations
import matplotlib.patches as mpatches
import os
import glob
import csv
import builtins

# NEW: YAML support (PyYAML)
import yaml


# --- Parameters ---
load_arr = [0, 10, 20, 30, 40]
calibration_value_str = "17.080989552178547" #px/mm 
calib_val = eval(calibration_value_str)
gray_delta = 20
circle_radius = 40  # px bone 3 = 40
red_thresh_high = 120  # bone 3 = 75
blue_thresh_high = 120 
green_thresh_high = 120
angle_tol = 10  # degrees
min_cluster_size = 5

#Find markers correctly
lower_green = np.array([35, 90, 80])  # bone 3 35, 90, 100
upper_green = np.array([100, 255, 255])
max_marker_jump = 70
track_previous = True


# System params
wkdir = ""  # set by CLI; no hardcoded default data path
output_folder = None  # set by CLI
marker_pair = (6, 2)  # 1-based marker ids, for example (2, 3)
debug_mode = True
rewrite_config = True
plot_debug = True
preview_first_frame = True
show_plots = True
vline_every_n = len(load_arr)
previous_markers = None # Global marker cache
current_warning_image_path = None
warning_log_rows = []
warning_log_path = None


def reset_warning_log(result_folder: str):
    global current_warning_image_path, warning_log_rows, warning_log_path
    current_warning_image_path = None
    warning_log_rows = []
    warning_log_path = os.path.join(result_folder, "warnings.csv")


def log_warning(message: str):
    entry = {
        "image_path": current_warning_image_path or "",
        "warning": message,
    }
    warning_log_rows.append(entry)
    print(message)


def flush_warning_log():
    if not warning_log_path:
        return

    if not warning_log_rows:
        if os.path.exists(warning_log_path):
            os.remove(warning_log_path)
        return

    with open(warning_log_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["image_path", "warning"])
        writer.writeheader()
        writer.writerows(warning_log_rows)


# NEW: YAML export helpers
def resolve_load_arr(folder: str):
    folder_lower = folder.lower()
    is_bone3 = "bone 3" in folder_lower

    if "bending" in folder_lower:
        return [0, 10, 20, 30, 40, 50, 60] if is_bone3 else [0, 10, 20, 30, 40]
    if "compression" in folder_lower:
        return [0, 100, 200, 300, 400, 500, 600] if is_bone3 else [0, 100, 200, 300, 400]

    if "load_arr" not in globals() or not isinstance(load_arr, (list, tuple)) or len(load_arr) == 0:
        raise ValueError("Please define load_arr in parameters section, e.g. load_arr = [0, 100, 200, 300, 400]")

    return list(load_arr)


def apply_params_from_dict(params: dict):
    """
    Update runtime parameters from a dictionary loaded from YAML.
    """
    global calibration_value_str, calib_val
    global circle_radius, red_thresh_high, green_thresh_high, blue_thresh_high
    global gray_delta, angle_tol, min_cluster_size
    global lower_green, upper_green
    global track_previous, max_marker_jump, load_arr

    calibration_value_str = params["calibration_value_str"]
    calib_val = eval(calibration_value_str)
    circle_radius = int(params["circle_radius"])
    red_thresh_high = int(params["red_thresh_high"])
    green_thresh_high = int(params["green_thresh_high"])
    blue_thresh_high = int(params["blue_thresh_high"])
    gray_delta = int(params.get("grey_delta", params.get("gray_delta", gray_delta)))
    angle_tol = float(params["angle_tol"])
    min_cluster_size = int(params["min_cluster_size"])
    lower_green = np.array(params["lower_green"], dtype=np.uint8)
    upper_green = np.array(params["upper_green"], dtype=np.uint8)
    track_previous = bool(params.get("track_previous", track_previous))
    max_marker_jump = float(params.get("max_marker_jump", max_marker_jump))
    if "load_arr" in params:
        load_arr = [float(x) if isinstance(x, float) else int(x) for x in params["load_arr"]]


def export_params_to_yaml(folder: str,
                          filename: str = "params.yaml",
                          rewrite: bool = False):
    """
    Export current parameters to YAML in `folder/filename`.
    If rewrite=False and file exists, do nothing.
    """
    path = os.path.join(folder, filename)

    params = {
        "calibration_value_str": calibration_value_str,
        "calibration_value": float(calib_val),
        "load_arr": [int(x) if float(x).is_integer() else float(x) for x in resolve_load_arr(folder)],
        "circle_radius": int(circle_radius),
        "red_thresh_high": int(red_thresh_high),
        "green_thresh_high": int(green_thresh_high),
        "blue_thresh_high": int(blue_thresh_high),
        "grey_delta": int(gray_delta),
        "angle_tol": float(angle_tol),
        "min_cluster_size": int(min_cluster_size),
        "lower_green": [int(x) for x in lower_green.tolist()],
        "upper_green": [int(x) for x in upper_green.tolist()],
        "track_previous": bool(track_previous),
        "max_marker_jump": float(max_marker_jump),
    }

    if os.path.exists(path) and not rewrite:
        print(f"Config exists, not rewritten: {path}")
        return path

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(params, f, sort_keys=False)

    print("Parameters exported to:", path)
    return path

def draw_debug_label_with_outline(img, text, org, scale=3.0):
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


def debug_label_position(x, y, w, h, dx=38, dy=-30):
    return max(10, min(int(round(x + dx)), w - 145)), max(58, min(int(round(y + dy)), h - 18))


def intersect_line_eq(A1, B1, C1, A2, B2, C2):
    denom = A1 * B2 - A2 * B1
    if abs(denom) < 1e-6:
        return None
    x = (B2 * (-C1) - B1 * (-C2)) / denom
    y = (A1 * (-C2) - A2 * (-C1)) / denom
    return x, y  # floats

def refine_centers_by_clustering(
    img,
    rough_centers,
    selected_indices=None,
    preview=False,
    show_mask=False
):
    """
    For each selected rough center:
     - cluster dark pixels into 4 groups,
     - identify two pairs of parallel clusters,
     - merge each parallel pair and fit a PCA line,
     - intersect the two merged lines to obtain refined center.
    Returns annotated image and list of refined centers.
    """

    annotated = img.copy()
    mask_vis = annotated.copy()
    refined_centers = []

    parallel_tol = angle_tol  # degrees, tolerance for parallel clusters

    if selected_indices is None:
        selected_indices = range(len(rough_centers))

    for out_idx, i in enumerate(selected_indices, start=1):
        cx, cy = rough_centers[i]

        # ROI in image coords
        x0, y0 = max(cx - circle_radius, 0), max(cy - circle_radius, 0)
        x1, y1 = min(cx + circle_radius, img.shape[1] - 1), min(cy + circle_radius, img.shape[0] - 1)
        roi = img[y0:y1, x0:x1]

        # -------------------------------------------------
        # mask dark pixels in circle 
        b, g, r = cv2.split(roi)
        b16 = b.astype(np.int16)
        g16 = g.astype(np.int16)
        r16 = r.astype(np.int16)

        # channel similarity condition (gray / black)
        mask_similar = (
            (np.abs(r16 - g16) <= gray_delta) &
            (np.abs(r16 - b16) <= gray_delta) &
            (np.abs(g16 - b16) <= gray_delta)
        )


        # optional absolute darkness constraint
        mask_dark = (
            (r <= red_thresh_high) &
            (g <= green_thresh_high) &
            (b <= blue_thresh_high)
        )

        mask_black = (mask_dark & mask_similar).astype(np.uint8) * 255
        if show_mask:
            # paint selected pixels as BLACK, leave others unchanged
            roi_vis = roi.copy()
            roi_vis[mask_black == 255] = (0, 0, 0)

            mask_vis[y0:y1, x0:x1] = roi_vis

            # draw ROI circle and marker index
            cv2.circle(mask_vis, (cx, cy), circle_radius, (0, 255, 0), 2)
            lx, ly = debug_label_position(cx, cy, mask_vis.shape[1], mask_vis.shape[0])
            draw_debug_label_with_outline(mask_vis, f"M{out_idx}", (lx, ly), scale=3.1)

            refined_centers.append((cx, cy))
            continue
        Y, X = np.ogrid[:roi.shape[0], :roi.shape[1]]
        circ = (X - (cx - x0)) ** 2 + (Y - (cy - y0)) ** 2 <= circle_radius ** 2
        pts = np.column_stack(np.where((mask_black > 0) & circ))
        # -------------------------------------------------

        # Not enough data
        if pts.shape[0] < 4 * min_cluster_size:
            cv2.circle(annotated, (cx, cy), circle_radius, (0, 0, 255), 2)
            log_warning("No 4 clusters for refinement found! Review the debug pictures.")
            refined_centers.append((cx, cy))
            continue

        # cluster into 4
        clustering = AgglomerativeClustering(n_clusters=4).fit(pts)
        labels = clustering.labels_
        uniq = np.unique(labels)

        if uniq.size != 4:
            cv2.circle(annotated, (cx, cy), circle_radius, (0, 0, 255), 2)
            log_warning("No 4 clusters for refinement found! Review the debug pictures.")
            refined_centers.append((cx, cy))
            continue

        # overlay clusters (debug)
        cols = [(200, 200, 0), (200, 0, 200), (0, 200, 200), (100, 100, 200)]
        for lab, col in zip(uniq, cols):
            for (r0, c0) in pts[labels == lab]:
                annotated[y0 + r0, x0 + c0] = col

        # -------------------------------------------------
        # Step 1: preliminary PCA direction per cluster
        cluster_dirs = {}
        cluster_pts = {}

        for lab in uniq:
            arr = pts[labels == lab]
            XY = np.column_stack((arr[:, 1], arr[:, 0])).astype(float)
            m = XY.mean(axis=0)
            cov = np.cov((XY - m).T)
            w, v = np.linalg.eigh(cov)
            dir_v = v[:, np.argmax(w)]
            dir_v /= np.linalg.norm(dir_v)

            cluster_dirs[lab] = dir_v
            cluster_pts[lab] = XY

        # -------------------------------------------------
        # Step 2: find parallel cluster pairs
        parallel_pairs = []

        for a, b in combinations(uniq, 2):
            d1 = cluster_dirs[a]
            d2 = cluster_dirs[b]
            ang = abs(
                math.degrees(
                    math.acos(np.clip(np.dot(d1, d2), -1.0, 1.0))
                )
            )
            ang = min(ang, abs(180 - ang))  # handle opposite directions

            if ang <= parallel_tol:
                parallel_pairs.append((a, b))

        if len(parallel_pairs) != 2:
            cv2.circle(annotated, (cx, cy), circle_radius, (0, 0, 255), 2)
            refined_centers.append((cx, cy))
            log_warning("No parallel lines from clusters for refinement found! Review the debug pictures.")
            continue

        # -------------------------------------------------
        # Step 3: merge each parallel pair and fit line
        merged_lines = []

        for (a, b) in parallel_pairs:
            XY = np.vstack((cluster_pts[a], cluster_pts[b]))
            m = XY.mean(axis=0)
            cov = np.cov((XY - m).T)
            w, v = np.linalg.eigh(cov)
            dir_v = v[:, np.argmax(w)]

            A, B = -dir_v[1], dir_v[0]
            C = -(A * m[0] + B * m[1])
            merged_lines.append((A, B, C))

        # -------------------------------------------------
        # Step 4: check perpendicularity
        (A1, B1, C1), (A2, B2, C2) = merged_lines
        d1 = np.array([B1, -A1])
        d2 = np.array([B2, -A2])

        ang = abs(
            math.degrees(
                math.acos(
                    np.dot(d1, d2) / (np.linalg.norm(d1) * np.linalg.norm(d2))
                )
            )
        )

        if abs(ang - 90) > angle_tol:
            cv2.circle(annotated, (cx, cy), circle_radius, (0, 0, 255), 2)
            refined_centers.append((cx, cy))
            log_warning("Refinement lines are not perpendicular! Review the debug pictures")
            continue

        # -------------------------------------------------
        # Step 5: draw merged lines
        for (A, B, C), color in zip(merged_lines, [(0, 255, 255), (255, 0, 255)]):
            pts_line = []
            for x_rel in (0, x1 - x0):
                if abs(B) > 1e-6:
                    y_rel = -(A * x_rel + C) / B
                    if 0 <= y_rel <= (y1 - y0):
                        pts_line.append((int(x0 + x_rel), int(y0 + y_rel)))
            for y_rel in (0, y1 - y0):
                if abs(A) > 1e-6:
                    x_rel = -(B * y_rel + C) / A
                    if 0 <= x_rel <= (x1 - x0):
                        pts_line.append((int(x0 + x_rel), int(y0 + y_rel)))
            if len(pts_line) >= 2:
                cv2.line(annotated, pts_line[0], pts_line[1], color, 1)

        # -------------------------------------------------
        # Step 6: intersection → refined center
        inter = intersect_line_eq(A1, B1, C1, A2, B2, C2)
        if inter is None:
            cv2.circle(annotated, (cx, cy), circle_radius, (0, 0, 255), 2)
            refined_centers.append((cx, cy))
            log_warning("No intersection between refinement lines!")
            continue

        x_int = int(inter[0] + x0)
        x_float = inter[0] + x0
        y_int = int(inter[1] + y0)
        y_float = inter[1] + y0

        refined_centers.append((x_float, y_float))
        cv2.circle(annotated, (x_int, y_int), 2, (0, 0, 0), 1)
        cv2.circle(annotated, (x_int, y_int), 1, (0, 0, 255), -1)
        lx, ly = debug_label_position(x_int, y_int, annotated.shape[1], annotated.shape[0])
        draw_debug_label_with_outline(annotated, f"C{out_idx}", (lx, ly), scale=3.1)

    # -------------------------------------------------
    # preview
    if preview:
        plt.figure(figsize=(8, 8))

        if show_mask:
            plt.imshow(cv2.cvtColor(mask_vis, cv2.COLOR_BGR2RGB))
            plt.title("Black / Gray Mask Visualization")
        else:
            plt.imshow(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB))
            plt.title("Parallel-Cluster Line Merging & Center Detection")

        plt.axis("off")
        plt.show()

    return annotated, refined_centers

def detect_markers(
    img,
    lower_green=None,
    upper_green=None,
    kernel_size=7,
    area_thresh=200,
    track_previous=None,
    max_marker_jump=None
):
    """
    Detect green markers and return ordered list of centroids [(x1,y1), ...].

    Robust ordering logic:
    - First frame: markers are sorted by x, then y
    - Next frames: current detections are matched to previous markers by nearest distance
    - If a marker disappears, its previous position is kept
    - Extra detections are ignored to preserve marker indexing
    """
    global previous_markers

    if lower_green is None:
        lower_green = globals()["lower_green"]
    if upper_green is None:
        upper_green = globals()["upper_green"]
    if track_previous is None:
        track_previous = globals()["track_previous"]
    if max_marker_jump is None:
        max_marker_jump = globals()["max_marker_jump"]

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower_green, upper_green)

    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)

    detected = []
    for label in range(1, num_labels):  # skip background
        if stats[label, cv2.CC_STAT_AREA] >= area_thresh:
            cx, cy = int(centroids[label][0]), int(centroids[label][1])
            detected.append((cx, cy))

    # First frame: initialize ordering
    if not track_previous or previous_markers is None:
        detected.sort(key=lambda c: (c[0], c[1]))
        previous_markers = detected.copy()
        return detected

    # No detections at all -> keep previous order and positions
    if len(detected) == 0:
        return previous_markers.copy()

    matched = [None] * len(previous_markers)
    used_detected = set()

    # Match each previous marker to nearest current detection within threshold
    for i, (px, py) in enumerate(previous_markers):
        best_j = None
        best_dist = float("inf")

        for j, (cx, cy) in enumerate(detected):
            if j in used_detected:
                continue

            dist = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_j = j

        # Accept only if movement is realistic
        if best_j is not None and best_dist <= max_marker_jump:
            matched[i] = detected[best_j]
            used_detected.add(best_j)
        else:
            # Marker disappeared -> keep previous position
            matched[i] = (px, py)

    previous_markers = matched.copy()
    return matched

def plot_dx_dy(rows,
               title_suffix="",
               vline_every_n=None,
               save_path=None,
               dpi=300,
               show_plot=True):
    """
    Plot dx and dy versus image index and optionally save figure.

    Parameters
    ----------
    rows : list
        [ImageName, MarkerPair, dx, dy]
    title_suffix : str
        Optional title suffix
    vline_every_n : int or None
        Draw vertical lines every N images
    save_path : str or None
        If provided, save figure to this path
    dpi : int
        Resolution for saved image
    """

    img_ids = []
    dx_vals = []
    dy_vals = []

    for i, row in enumerate(rows):
        dx, dy = row[5], row[6]
        if dx is not None and dy is not None:
            img_ids.append(i)
            dx_vals.append(dx)
            dy_vals.append(dy)

    if not img_ids:
        print("No valid dx/dy values to plot.")
        return

    fig, axs = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

    # ΔX
    axs[0].plot(img_ids, dx_vals, "o-", linewidth=1.5)
    axs[0].set_ylabel("ΔX (px)")
    axs[0].grid(True)

    # ΔY
    axs[1].plot(img_ids, dy_vals, "o-", linewidth=1.5)
    axs[1].set_ylabel("ΔY (px)")
    axs[1].set_xlabel("Image ID")
    axs[1].grid(True)

    # Vertical lines
    if vline_every_n is not None and vline_every_n > 0:
        for x in range(0, max(img_ids) + 1, vline_every_n):
            axs[0].axvline(x, linestyle="--", alpha=0.5)
            axs[1].axvline(x, linestyle="--", alpha=0.5)

    fig.suptitle(f"Interfragmentary Motion {title_suffix}")
    plt.tight_layout()

    # --- Save ---
    if save_path is not None:
        plt.savefig(os.path.join(save_path, "plot.png"), dpi=dpi, bbox_inches="tight")
        print(f"Plot saved to: {save_path}")

    if show_plot:
        plt.show()
    else:
        plt.close(fig)


def main(folder: str,
         debug_mode: bool = False,
         rewrite_config: bool = False,
         plot_debug: bool = False,
         marker_pair=None,
         output_folder: str = None,
         preview_first_frame: bool = True,
         show_plots: bool = True):
    result_folder = output_folder

    image_paths = sorted(
        p for p in glob.glob(os.path.join(folder, "*.*"))
        if p.lower().endswith(".jpg")
    )

    if not image_paths:
        print("No .jpg images found")
        return

    # --- First image: marker selection ---
    img0 = cv2.imread(image_paths[0])
    rough0 = detect_markers(img0)

    global current_warning_image_path
    current_warning_image_path = image_paths[0]
    refine_centers_by_clustering(
        img0, rough0, preview=preview_first_frame, show_mask=False
    )

    n = len(rough0)
    if marker_pair is None:
        sel = input(f"Select two markers (1-{n}): ")
        m1, m2 = map(int, sel.split())
    else:
        m1, m2 = marker_pair
        if not (1 <= m1 <= n and 1 <= m2 <= n):
            raise ValueError(f"Marker pair {marker_pair} is out of range for {n} detected markers")
    selected = [m1 - 1, m2 - 1]

    if result_folder is None:
        result_folder = os.path.join(folder, f"{m1} to {m2}")

    os.makedirs(result_folder, exist_ok=True)
    reset_warning_log(result_folder)

    export_params_to_yaml(result_folder,
                          filename="params.yaml",
                          rewrite=rewrite_config)

    # --- Resolve load array ---
    active_load_arr = resolve_load_arr(folder)
    steps_per_trial = len(active_load_arr)

    if debug_mode:
        debug_folder = os.path.join(result_folder, "debug_marked")
        os.makedirs(debug_folder, exist_ok=True)

    rows = []

    # We need per-trial reference values for deformation
    trial0_dx = None  # dx at load step 0 (index 0) within current trial
    trial0_dy = None
    trial1_dx = None  # dx at load step 1 (index 1) within current trial (first non-zero step)
    trial1_dy = None

    # --- Process all images ---
    for idx, path in enumerate(image_paths):
        print("Processing:", path)
        current_warning_image_path = path

        # Determine trial index and load step index inside trial
        step_idx = idx % steps_per_trial          # 0..steps_per_trial-1
        trial_idx = idx // steps_per_trial        # 0..Ntrials-1
        load_N = active_load_arr[step_idx]

        img = cv2.imread(path)
        if img is None:
            # still write load + placeholders to keep alignment
            rows.append([
                os.path.basename(path),
                trial_idx,
                step_idx,
                load_N,
                f"{m1}->{m2}",
                None, None, None, None,   # dx/dy px, ex/ey mm
                None, None, None, None    # def0 x/y, def1 x/y (mm)
            ])
            continue

        rough = detect_markers(img)

        ann, ref = refine_centers_by_clustering(
            img,
            rough,
            selected_indices=selected,
            preview=False
        )

        if len(ref) == 2:
            (x1, y1), (x2, y2) = ref
            dx, dy = x2 - x1, y2 - y1
            ex, ey = dx / calib_val, dy / calib_val  # mm (signed)
        else:
            dx = dy = None
            ex = ey = None

        # ---- Update trial reference points ----
        # Reset references at start of each trial (step 0)
        if step_idx == 0:
            trial0_dx, trial0_dy = dx, dy
            trial1_dx, trial1_dy = None, None

        # Store step 1 reference (first load step after step 0) if available
        if step_idx == 1 and trial1_dx is None:
            trial1_dx, trial1_dy = dx, dy

        # ---- Deformation calculations (mm) ----
        # Variant A: deformation relative to step 0 in the same trial
        if (ex is not None) and (trial0_dx is not None):
            def0_x = (dx - trial0_dx) / calib_val
            def0_y = (dy - trial0_dy) / calib_val
        else:
            def0_x = def0_y = None

        # Variant B: deformation relative to step 1 in the same trial
        # If step 1 reference isn't available (e.g., missing marker), keep None
        if (ex is not None) and (trial1_dx is not None):
            def1_x = (dx - trial1_dx) / calib_val
            def1_y = (dy - trial1_dy) / calib_val
        else:
            def1_x = def1_y = None

        rows.append([
            os.path.basename(path),
            trial_idx,
            step_idx,
            load_N,
            f"{m1}->{m2}",
            dx, dy, ex, ey,
            def0_x, def0_y,
            def1_x, def1_y
        ])

        if debug_mode:
            cv2.imwrite(
                os.path.join(debug_folder, os.path.basename(path)),
                ann
            )

    # --- CSV ---
    csv_file = os.path.join(result_folder, "distances.csv")
    with open(csv_file, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "Image",
            "TrialID",
            "LoadStepID",
            "Load_N",
            "MarkerPair",
            "dX_px", "dY_px",
            "dX_mm", "dY_mm",
            "Def_from_0_mm_X", "Def_from_0_mm_Y",
            "Def_from_step1_mm_X", "Def_from_step1_mm_Y"
        ])
        w.writerows(rows)

    if plot_debug:
        plot_dx_dy(
            rows,
            title_suffix=f"(markers {m1}->{m2})",
            vline_every_n=steps_per_trial,
            save_path=result_folder,
            show_plot=show_plots
        )

    flush_warning_log()
    print("Finished. Results:", csv_file)


    




def run_current_configuration():
    """
    Manual workflow entry point. Prefer the package CLI.
    """
    if marker_pair is None:
        return main(
            wkdir,
            debug_mode,
            rewrite_config,
            plot_debug,
            output_folder=output_folder,
            preview_first_frame=preview_first_frame,
            show_plots=show_plots,
        )

    if len(marker_pair) != 2:
        raise ValueError("marker_pair must contain exactly two marker ids, e.g. (2, 3)")

    original_input = builtins.input
    builtins.input = lambda prompt="": f"{marker_pair[0]} {marker_pair[1]}"
    try:
        return main(
            wkdir,
            debug_mode,
            rewrite_config,
            plot_debug,
            output_folder=output_folder,
            preview_first_frame=preview_first_frame,
            show_plots=show_plots,
        )
    finally:
        builtins.input = original_input


if __name__ == "__main__":
    run_current_configuration()
