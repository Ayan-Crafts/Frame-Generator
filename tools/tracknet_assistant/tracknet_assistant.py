from __future__ import print_function

import argparse
import csv
import json
import math
from pathlib import Path

import cv2
import numpy as np
import tensorflow as tf


TRACKNET_WIDTH = 640
TRACKNET_HEIGHT = 360
N_CLASSES = 256


def load_annotations(csv_path):
    annotations = {}

    with open(
        csv_path,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            frame = row["frame"]

            annotations[frame] = {
                "x": float(row["x"]),
                "y": float(row["y"]),
                "visibility": int(float(row["visibility"])),
                "status": row.get("status", ""),
            }

    return annotations


def load_tracknet_model(weights_path):

    # Import official TrackNet V1 model.
    import sys

    tracknet_dir = Path(
        r"S:\Thotta_Nee_Keta\Projects\TrackNet-V1"
    )

    model_dir = (
        tracknet_dir
        / "Code_Python3"
        / "TrackNet_One_Frame_Input"
    )

    sys.path.insert(
        0,
        str(model_dir),
    )

    import Models

    model = Models.TrackNet.TrackNet(
        N_CLASSES,
        input_height=TRACKNET_HEIGHT,
        input_width=TRACKNET_WIDTH,
    )

    model.compile(
        loss="categorical_crossentropy",
        optimizer="adadelta",
        metrics=["accuracy"],
    )

    model.load_weights(
        str(weights_path)
    )

    return model


def heatmap_prediction(model, frame):

    resized = cv2.resize(
        frame,
        (
            TRACKNET_WIDTH,
            TRACKNET_HEIGHT,
        ),
    )

    resized = resized.astype(
        np.float32
    )

    # TrackNet expects channels-first.
    x = np.rollaxis(
        resized,
        2,
        0,
    )

    prediction = model.predict(
        np.array([x]),
        verbose=0,
    )[0]

    prediction = prediction.reshape(
        (
            TRACKNET_HEIGHT,
            TRACKNET_WIDTH,
            N_CLASSES,
        )
    )

    # Highest probability class at each pixel.
    class_map = prediction.argmax(
        axis=2
    ).astype(
        np.uint8
    )

    # Maximum predicted class value.
    peak_value = int(
        class_map.max()
    )

    # Threshold exactly as the original
    # TrackNet V1 prediction implementation.
    _, binary = cv2.threshold(
        class_map,
        127,
        255,
        cv2.THRESH_BINARY,
    )

    # Find connected components rather than
    # immediately relying only on Hough circles.
    num_labels, labels, stats, centroids = (
        cv2.connectedComponentsWithStats(
            binary,
            connectivity=8,
        )
    )

    candidates = []

    for i in range(1, num_labels):

        area = int(
            stats[i, cv2.CC_STAT_AREA]
        )

        if area <= 0:
            continue

        cx, cy = centroids[i]

        candidates.append(
            {
                "x": float(cx),
                "y": float(cy),
                "area": area,
            }
        )

    candidates.sort(
        key=lambda c: c["area"],
        reverse=True,
    )

    return (
        class_map,
        candidates,
        peak_value,
    )


def choose_prediction(
    candidates,
    peak_value,
):

    if not candidates:

        return None

    # Largest connected component.
    candidate = candidates[0]

    x = candidate["x"]
    y = candidate["y"]
    area = candidate["area"]

    # Basic quality scoring.
    #
    # This is intentionally conservative.
    # We will calibrate it against your 233
    # ground-truth annotations.
    score = 0.0

    if peak_value >= 200:
        score += 0.5
    elif peak_value >= 160:
        score += 0.35
    elif peak_value >= 128:
        score += 0.2

    if 1 <= area <= 100:
        score += 0.5
    elif area <= 250:
        score += 0.25

    score = min(
        1.0,
        score,
    )

    return {
        "x_tracknet": x,
        "y_tracknet": y,
        "confidence": score,
        "area": area,
        "peak": peak_value,
        "candidate_count": len(candidates),
    }


def tracknet_to_original(
    x,
    y,
    width,
    height,
):

    return (
        x * width / TRACKNET_WIDTH,
        y * height / TRACKNET_HEIGHT,
    )


def distance(
    x1,
    y1,
    x2,
    y2,
):

    return math.sqrt(
        (x1 - x2) ** 2
        +
        (y1 - y2) ** 2
    )


def draw_result(
    frame,
    manual,
    prediction,
    output_path,
):

    image = frame.copy()

    # Manual ground truth: GREEN
    if manual["visibility"] == 1:

        mx = int(manual["x"])
        my = int(manual["y"])

        cv2.circle(
            image,
            (mx, my),
            7,
            (0, 255, 0),
            2,
        )

        cv2.putText(
            image,
            "GT",
            (mx + 10, my),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

    # TrackNet prediction: RED
    if prediction is not None:

        px = int(
            prediction["x_original"]
        )

        py = int(
            prediction["y_original"]
        )

        cv2.circle(
            image,
            (px, py),
            7,
            (0, 0, 255),
            2,
        )

        cv2.putText(
            image,
            "TrackNet",
            (px + 10, py),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2,
        )

        if (
            manual["visibility"] == 1
        ):

            error = distance(
                manual["x"],
                manual["y"],
                prediction["x_original"],
                prediction["y_original"],
            )

            cv2.putText(
                image,
                f"Error: {error:.1f}px",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
            )

    cv2.imwrite(
        str(output_path),
        image,
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--frames",
        required=True,
    )

    parser.add_argument(
        "--annotations",
        required=True,
    )

    parser.add_argument(
        "--weights",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    args = parser.parse_args()

    frames_dir = Path(
        args.frames
    ).resolve()

    annotations_path = Path(
        args.annotations
    ).resolve()

    weights_path = Path(
        args.weights
    ).resolve()

    output_dir = Path(
        args.output
    ).resolve()

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    visualization_dir = (
        output_dir / "visualizations"
    )

    visualization_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 70)
    print("TRACKNET V1 ANNOTATION ASSISTANT")
    print("=" * 70)

    print(
        f"Frames      : {frames_dir}"
    )

    print(
        f"Annotations : {annotations_path}"
    )

    print(
        f"Weights     : {weights_path}"
    )

    print(
        f"Output      : {output_dir}"
    )

    print()

    annotations = load_annotations(
        annotations_path
    )

    print(
        f"Ground-truth annotations: "
        f"{len(annotations)}"
    )

    print()

    print(
        "Loading TrackNet V1..."
    )

    model = load_tracknet_model(
        weights_path
    )

    print(
        "TrackNet loaded."
    )

    print()

    prediction_csv = (
        output_dir
        / "tracknet_predictions.csv"
    )

    results = []

    errors = []

    exact_or_near = {
        "5px": 0,
        "10px": 0,
        "20px": 0,
        "over20px": 0,
    }

    misses = 0

    frames = sorted(
        frames_dir.glob("*.jpg")
    )

    print(
        f"Frames found: {len(frames)}"
    )

    print()

    for index, frame_path in enumerate(
        frames,
        start=1,
    ):

        frame_name = frame_path.name

        frame = cv2.imread(
            str(frame_path)
        )

        if frame is None:

            print(
                f"[WARNING] Cannot read "
                f"{frame_name}"
            )

            continue

        height, width = frame.shape[:2]

        manual = annotations.get(
            frame_name
        )

        if manual is None:

            continue

        (
            class_map,
            candidates,
            peak_value,
        ) = heatmap_prediction(
            model,
            frame,
        )

        prediction = choose_prediction(
            candidates,
            peak_value,
        )

        error = None

        if prediction is not None:

            px, py = tracknet_to_original(
                prediction["x_tracknet"],
                prediction["y_tracknet"],
                width,
                height,
            )

            prediction["x_original"] = px
            prediction["y_original"] = py

            if manual["visibility"] == 1:

                error = distance(
                    manual["x"],
                    manual["y"],
                    px,
                    py,
                )

                errors.append(
                    error
                )

                if error <= 5:
                    exact_or_near["5px"] += 1
                elif error <= 10:
                    exact_or_near["10px"] += 1
                elif error <= 20:
                    exact_or_near["20px"] += 1
                else:
                    exact_or_near["over20px"] += 1

        else:

            misses += 1

        status = "NO_DETECTION"

        if prediction is not None:

            if manual["visibility"] == 0:

                status = (
                    "PREDICTED_WHILE_NOT_VISIBLE"
                )

            elif error is not None:

                if error <= 10:

                    status = "GOOD"

                elif error <= 20:

                    status = "REVIEW"

                else:

                    status = "BAD"

            else:

                status = "PREDICTED"

        results.append(
            {
                "frame": frame_name,
                "manual_x": manual["x"],
                "manual_y": manual["y"],
                "visibility": manual["visibility"],
                "predicted_x": (
                    prediction["x_original"]
                    if prediction
                    else ""
                ),
                "predicted_y": (
                    prediction["y_original"]
                    if prediction
                    else ""
                ),
                "error_px": (
                    error
                    if error is not None
                    else ""
                ),
                "confidence": (
                    prediction["confidence"]
                    if prediction
                    else 0
                ),
                "heatmap_peak": (
                    prediction["peak"]
                    if prediction
                    else 0
                ),
                "component_area": (
                    prediction["area"]
                    if prediction
                    else 0
                ),
                "candidate_count": (
                    prediction[
                        "candidate_count"
                    ]
                    if prediction
                    else 0
                ),
                "status": status,
            }
        )

        draw_result(
            frame,
            manual,
            prediction,
            visualization_dir / frame_name,
        )

        if index % 10 == 0:

            print(
                f"Processed "
                f"{index}/{len(frames)}"
            )

    with open(
        prediction_csv,
        "w",
        encoding="utf-8",
        newline="",
    ) as f:

        if results:

            writer = csv.DictWriter(
                f,
                fieldnames=results[0].keys(),
            )

            writer.writeheader()

            writer.writerows(
                results
            )

    visible_count = sum(
        1
        for a in annotations.values()
        if a["visibility"] == 1
    )

    mean_error = (
        float(np.mean(errors))
        if errors
        else None
    )

    median_error = (
        float(np.median(errors))
        if errors
        else None
    )

    evaluation = {
        "total_frames": len(frames),
        "annotated_frames": len(annotations),
        "visible_ground_truth_frames": visible_count,
        "predictions_with_detection": (
            len(errors)
        ),
        "misses": misses,
        "mean_error_px": mean_error,
        "median_error_px": median_error,
        "within_5px": exact_or_near["5px"],
        "within_10px": (
            exact_or_near["5px"]
            + exact_or_near["10px"]
        ),
        "within_20px": (
            exact_or_near["5px"]
            + exact_or_near["10px"]
            + exact_or_near["20px"]
        ),
        "over_20px": exact_or_near[
            "over20px"
        ],
    }

    evaluation_path = (
        output_dir
        / "evaluation.json"
    )

    with open(
        evaluation_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            evaluation,
            f,
            indent=2,
        )

    print()
    print("=" * 70)
    print("TRACKNET ASSISTANT TEST COMPLETE")
    print("=" * 70)

    print(
        f"Total frames       : "
        f"{len(frames)}"
    )

    print(
        f"Visible GT frames  : "
        f"{visible_count}"
    )

    print(
        f"Predictions tested : "
        f"{len(errors)}"
    )

    print(
        f"Misses             : "
        f"{misses}"
    )

    if mean_error is not None:

        print(
            f"Mean error         : "
            f"{mean_error:.2f}px"
        )

        print(
            f"Median error       : "
            f"{median_error:.2f}px"
        )

    print()

    print(
        f"≤ 5 px             : "
        f"{exact_or_near['5px']}"
    )

    print(
        f"≤ 10 px            : "
        f"{exact_or_near['5px'] + exact_or_near['10px']}"
    )

    print(
        f"≤ 20 px            : "
        f"{exact_or_near['5px'] + exact_or_near['10px'] + exact_or_near['20px']}"
    )

    print(
        f"> 20 px            : "
        f"{exact_or_near['over20px']}"
    )

    print()

    print(
        f"Predictions CSV:"
    )

    print(
        prediction_csv
    )

    print()

    print(
        f"Visualizations:"
    )

    print(
        visualization_dir
    )

    print()

    print(
        f"Evaluation:"
    )

    print(
        evaluation_path
    )


if __name__ == "__main__":
    main()