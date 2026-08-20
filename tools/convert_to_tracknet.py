from __future__ import print_function

import argparse
import csv
import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


TRACKNET_WIDTH = 640
TRACKNET_HEIGHT = 360


def generate_heatmap(
    x,
    y,
    width=TRACKNET_WIDTH,
    height=TRACKNET_HEIGHT,
    radius=5,
):
    """
    Generate a TrackNet-style grayscale target heatmap.

    Background:
        0

    Ball:
        Gaussian-like intensity centered at (x, y)

    The resulting image contains values in [0, 255].
    """

    image = Image.new("L", (width, height), 0)

    if x is None or y is None:
        return image

    if x < 0 or y < 0:
        return image

    if x >= width or y >= height:
        return image

    # Draw a small Gaussian-like circular target.
    #
    # TrackNet uses a heatmap representation rather than
    # directly training on x/y coordinates.
    pixels = image.load()

    sigma = max(radius / 2.0, 1.0)

    min_x = max(0, int(x - radius))
    max_x = min(width - 1, int(x + radius))
    min_y = max(0, int(y - radius))
    max_y = min(height - 1, int(y + radius))

    for py in range(min_y, max_y + 1):
        for px in range(min_x, max_x + 1):

            dx = px - x
            dy = py - y

            distance_sq = dx * dx + dy * dy

            if distance_sq > radius * radius:
                continue

            value = 255.0 * math.exp(
                -distance_sq / (2.0 * sigma * sigma)
            )

            if value > pixels[px, py]:
                pixels[px, py] = int(value)

    return image


def convert_coordinate(x, y, original_width, original_height):
    """
    Convert original image coordinates to TrackNet 640x360 coordinates.
    """

    tracknet_x = round(
        x * TRACKNET_WIDTH / original_width
    )

    tracknet_y = round(
        y * TRACKNET_HEIGHT / original_height
    )

    tracknet_x = max(
        0,
        min(TRACKNET_WIDTH - 1, tracknet_x)
    )

    tracknet_y = max(
        0,
        min(TRACKNET_HEIGHT - 1, tracknet_y)
    )

    return tracknet_x, tracknet_y


def find_annotation_column(fieldnames, candidates):
    """
    Find a CSV column using several possible names.
    """

    lookup = {
        name.strip().lower(): name
        for name in fieldnames
    }

    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]

    return None


def load_annotations(csv_path):
    """
    Load the annotation CSV.

    Supports our current annotation format.
    """

    with open(
        csv_path,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise RuntimeError(
                "CSV has no header."
            )

        fieldnames = reader.fieldnames

        frame_col = find_annotation_column(
            fieldnames,
            [
                "frame",
                "filename",
                "file",
                "image",
            ],
        )

        x_col = find_annotation_column(
            fieldnames,
            ["x"],
        )

        y_col = find_annotation_column(
            fieldnames,
            ["y"],
        )

        visibility_col = find_annotation_column(
            fieldnames,
            ["visibility"],
        )

        status_col = find_annotation_column(
            fieldnames,
            ["status"],
        )

        if frame_col is None:
            raise RuntimeError(
                "Could not find frame column."
            )

        if x_col is None:
            raise RuntimeError(
                "Could not find x column."
            )

        if y_col is None:
            raise RuntimeError(
                "Could not find y column."
            )

        if visibility_col is None:
            raise RuntimeError(
                "Could not find visibility column."
            )

        annotations = []

        for row in reader:

            frame = str(
                row[frame_col]
            ).strip()

            if not frame:
                continue

            try:
                x = float(row[x_col])
            except (ValueError, TypeError):
                x = 0

            try:
                y = float(row[y_col])
            except (ValueError, TypeError):
                y = 0

            try:
                visibility = int(
                    float(row[visibility_col])
                )
            except (ValueError, TypeError):
                visibility = 0

            status = ""

            if status_col:
                status = str(
                    row.get(status_col, "")
                ).strip()

            annotations.append(
                {
                    "frame": frame,
                    "x": x,
                    "y": y,
                    "visibility": visibility,
                    "status": status,
                }
            )

    return annotations


def split_annotations(
    annotations,
    validation_ratio=0.2,
):
    """
    Sequential split.

    We deliberately split by frame order for this first
    experiment so that the validation sequence remains
    temporally coherent.
    """

    total = len(annotations)

    if total < 2:
        return annotations, []

    validation_count = max(
        1,
        int(round(total * validation_ratio)),
    )

    training_count = total - validation_count

    if training_count < 1:
        training_count = 1
        validation_count = total - 1

    training = annotations[:training_count]
    validation = annotations[training_count:]

    return training, validation


def write_tracknet_csv(
    output_path,
    rows,
):
    """
    Official TrackNet loader expects:

    column 0 = image path
    column 3 = heatmap path

    We therefore deliberately put those paths in columns
    0 and 3.
    """

    with open(
        output_path,
        "w",
        encoding="utf-8",
        newline="",
    ) as f:

        writer = csv.writer(f)

        for row in rows:

            writer.writerow(
                [
                    row["image"],
                    row["frame"],
                    row["visibility"],
                    row["heatmap"],
                ]
            )


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Convert Frame Generator annotations "
            "into TrackNet V1 training data."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help=(
            "Directory containing original frames "
            "and annotations.csv"
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        help=(
            "Output TrackNet dataset directory"
        ),
    )

    parser.add_argument(
        "--validation-ratio",
        type=float,
        default=0.20,
        help="Validation fraction. Default: 0.20",
    )

    parser.add_argument(
        "--copy-images",
        action="store_true",
        help="Copy resized images into output/images.",
    )

    args = parser.parse_args()

    input_dir = Path(
        args.input
    ).resolve()

    output_dir = Path(
        args.output
    ).resolve()

    annotation_csv = (
        input_dir / "annotations.csv"
    )

    if not annotation_csv.exists():

        raise FileNotFoundError(
            f"annotations.csv not found:\n"
            f"{annotation_csv}"
        )

    output_images = (
        output_dir / "images"
    )

    output_heatmaps = (
        output_dir / "heatmaps"
    )

    output_images.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_heatmaps.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 70)
    print("TrackNet V1 Dataset Converter")
    print("=" * 70)

    print(
        f"Input : {input_dir}"
    )

    print(
        f"Output: {output_dir}"
    )

    annotations = load_annotations(
        annotation_csv
    )

    print(
        f"Annotations found: {len(annotations)}"
    )

    if not annotations:

        raise RuntimeError(
            "No annotations found."
        )

    training_annotations, validation_annotations = (
        split_annotations(
            annotations,
            args.validation_ratio,
        )
    )

    print(
        f"Training frames  : {len(training_annotations)}"
    )

    print(
        f"Validation frames: {len(validation_annotations)}"
    )

    training_rows = []
    validation_rows = []

    report = {
        "input_directory": str(input_dir),
        "output_directory": str(output_dir),
        "total_annotations": len(annotations),
        "training_frames": len(training_annotations),
        "validation_frames": len(validation_annotations),
        "tracknet_width": TRACKNET_WIDTH,
        "tracknet_height": TRACKNET_HEIGHT,
        "visible": 0,
        "not_visible": 0,
        "severe_motion_blur": 0,
        "fully_occluded": 0,
        "out_of_bounds": 0,
        "missing_images": 0,
        "invalid_annotations": 0,
    }

    for index, annotation in enumerate(
        annotations,
        start=1,
    ):

        frame_name = annotation["frame"]

        image_path = (
            input_dir / frame_name
        )

        if not image_path.exists():

            # Try common extensions if the CSV
            # contains only a frame stem.
            candidates = [
                input_dir / f"{frame_name}.jpg",
                input_dir / f"{frame_name}.jpeg",
                input_dir / f"{frame_name}.png",
            ]

            found = None

            for candidate in candidates:

                if candidate.exists():

                    found = candidate
                    break

            if found is None:

                report["missing_images"] += 1

                print(
                    f"[WARNING] Missing image: "
                    f"{frame_name}"
                )

                continue

            image_path = found

        try:

            image = Image.open(
                image_path
            ).convert("RGB")

        except Exception as exc:

            report["missing_images"] += 1

            print(
                f"[WARNING] Cannot open "
                f"{image_path}: {exc}"
            )

            continue

        original_width, original_height = (
            image.size
        )

        visibility = int(
            annotation["visibility"]
        )

        x = annotation["x"]
        y = annotation["y"]

        status = annotation["status"].upper()

        if visibility == 1:

            report["visible"] += 1

            tx, ty = convert_coordinate(
                x,
                y,
                original_width,
                original_height,
            )

            heatmap = generate_heatmap(
                tx,
                ty,
            )

        else:

            report["not_visible"] += 1

            heatmap = generate_heatmap(
                None,
                None,
            )

        if "MOTION_BLUR" in status:

            report["severe_motion_blur"] += 1

        if "FULLY_OCCLUDED" in status:

            report["fully_occluded"] += 1

        if "OUT_OF_BOUNDS" in status:

            report["out_of_bounds"] += 1

        if args.copy_images:

            resized = image.resize(
                (
                    TRACKNET_WIDTH,
                    TRACKNET_HEIGHT,
                ),
                Image.Resampling.LANCZOS,
            )

            output_image_path = (
                output_images / frame_name
            )

            resized.save(
                output_image_path,
                quality=95,
            )

            image_reference = str(
                output_image_path
            )

        else:

            image_reference = str(
                image_path
            )

        heatmap_path = (
            output_heatmaps / frame_name
        )

        heatmap.save(
            heatmap_path,
            quality=95,
        )

        row = {
            "image": image_reference,
            "frame": frame_name,
            "visibility": visibility,
            "heatmap": str(
                heatmap_path
            ),
        }
        training_count = int(len(annotations) * 0.8)

        training_annotations = annotations[:training_count]
        validation_annotations = annotations[training_count:]

        training_frames = {
            row["frame"]
            for row in training_annotations
        }
        if frame_name in training_frames:
            training_rows.append(row)
        else:
            validation_rows.append(row)

        if index % 25 == 0:

            print(
                f"Processed "
                f"{index}/{len(annotations)}"
            )

    training_csv = (
        output_dir /
        "training_model1.csv"
    )

    validation_csv = (
        output_dir /
        "testing_model1.csv"
    )

    write_tracknet_csv(
        training_csv,
        training_rows,
    )

    write_tracknet_csv(
        validation_csv,
        validation_rows,
    )

    report_path = (
        output_dir /
        "conversion_report.json"
    )

    with open(
        report_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            report,
            f,
            indent=2,
        )

    print()
    print("=" * 70)
    print("CONVERSION COMPLETE")
    print("=" * 70)

    print(
        f"Training CSV : {training_csv}"
    )

    print(
        f"Testing CSV  : {validation_csv}"
    )

    print(
        f"Heatmaps     : {output_heatmaps}"
    )

    print(
        f"Report       : {report_path}"
    )

    print()
    print("Statistics:")

    for key, value in report.items():

        if key in {
            "input_directory",
            "output_directory",
            "tracknet_width",
            "tracknet_height",
        }:
            continue

        print(
            f"  {key}: {value}"
        )


if __name__ == "__main__":
    main()