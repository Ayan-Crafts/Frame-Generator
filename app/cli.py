"""Command-line interface: ``tracknet-prepper-cli``.

Sub-commands
------------
doctor            Dependency and GPU capability report (also used by the
                  installers to verify an installation).
extract           Headless video -> frame extraction (same engine as the GUI).
convert-tracknet  Convert annotated frames to TrackNet V1 training data.

Exit codes: 0 success, 1 failure, 2 usage error, 3 FFmpeg unusable.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import APP_NAME, APP_VERSION  # noqa: E402


def _configure_stdio():
    # Windows consoles default to a legacy code page; FFmpeg paths and the
    # pipeline arrows are Unicode.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def cmd_doctor(args) -> int:
    from app.hardware.capabilities import get_report
    from app.utils.paths import log_dir

    report = get_report()

    if args.json:
        data = report.to_dict()
        data["app_version"] = APP_VERSION
        text = json.dumps(data, indent=2, default=str)
        if args.json == "-":
            print(text)
        else:
            Path(args.json).write_text(text, encoding="utf-8")
            print(f"Report written to {args.json}")
    else:
        print(f"{APP_NAME} {APP_VERSION}")
        print("-" * 60)
        for line in report.summary_lines():
            print(line)
        print("-" * 60)
        print(f"Logs: {log_dir()}")

    if not report.ffmpeg_ok:
        print(
            "\nFFmpeg is missing or unusable; video extraction will not work. "
            "The annotation tool is unaffected.",
            file=sys.stderr,
        )
        return 3
    if args.require_gpu and not report.gpu_pipeline_ready:
        print("\nGPU (NVDEC) extraction is not available on this system.", file=sys.stderr)
        return 1
    return 0


def cmd_extract(args) -> int:
    from app.hardware.capabilities import get_report
    from app.processing.exporter import VideoExporter
    from app.processing.scanner import DatasetScanner, output_names

    source = Path(args.input)
    output = Path(args.output)

    if source.is_file():
        videos = [source]
    elif source.is_dir():
        videos = DatasetScanner().scan(str(source)).videos
    else:
        print(f"Input not found: {source}", file=sys.stderr)
        return 2

    if not videos:
        print(f"No supported videos found in {source}", file=sys.stderr)
        return 2

    report = get_report()
    if not report.ffmpeg_ok:
        for problem in report.ffmpeg_problems or [report.ffmpeg_error]:
            print(problem, file=sys.stderr)
        return 3

    output.mkdir(parents=True, exist_ok=True)

    last_print = [0.0]

    def on_progress(data):
        now = time.monotonic()
        if data.get("status") == "processing" and now - last_print[0] < 1.0:
            return
        last_print[0] = now
        total = data.get("total_frames") or 0
        frames = data.get("frames") or 0
        pct = f"{100 * frames / total:5.1f}%" if total else "  ?  "
        print(
            f"  {data.get('video')}: {frames}/{total} {pct} "
            f"{data.get('fps', 0):.0f} fps [{data.get('status')}]",
            flush=True,
        )

    errors: list[str] = []
    warnings: list[str] = []
    exporter = VideoExporter(
        mode=args.mode,
        gpu_ready=report.gpu_pipeline_ready,
        on_progress=on_progress,
        on_error=errors.append,
        on_warning=warnings.append,
    )

    names = output_names(videos)
    failed = 0
    started = time.monotonic()
    results = []

    for video in videos:
        errors.clear()
        print(f"[{len(results) + 1}/{len(videos)}] {video.name}", flush=True)
        t0 = time.monotonic()
        result = exporter.export_video(video, output, output_name=names[video])
        elapsed = time.monotonic() - t0
        ok = result is True
        failed += 0 if ok else 1
        results.append(
            {
                "video": str(video),
                "output": str(output / names[video]),
                "ok": ok,
                "pipeline": exporter.last_pipeline,
                "seconds": round(elapsed, 3),
                "error": errors[0] if errors else None,
            }
        )
        print(
            f"    -> {'OK' if ok else 'FAILED'} in {elapsed:.2f}s via {exporter.last_pipeline}",
            flush=True,
        )
        for message in errors:
            print("    " + message.replace("\n", "\n    "), file=sys.stderr)

    for message in warnings:
        print(f"WARNING: {message}", file=sys.stderr)

    print(
        f"Done: {len(videos) - failed}/{len(videos)} succeeded in "
        f"{time.monotonic() - started:.2f}s"
    )
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if failed == 0 else 1


def cmd_convert(args) -> int:
    from app.tools.convert_to_tracknet import main as convert_main

    return convert_main(args.converter_args) or 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracknet-prepper-cli",
        description=f"{APP_NAME} command-line tools",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    parser.add_argument("--verbose", action="store_true", help="Log debug output to stderr.")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check FFmpeg, NVIDIA GPU and acceleration.")
    doctor.add_argument("--json", metavar="FILE", help="Write the report as JSON ('-' = stdout).")
    doctor.add_argument(
        "--require-gpu", action="store_true", help="Exit 1 unless GPU extraction is verified."
    )
    doctor.set_defaults(func=cmd_doctor)

    extract = sub.add_parser("extract", help="Extract frames from a video or a folder of videos.")
    extract.add_argument("input", help="Video file or folder (searched recursively).")
    extract.add_argument("output", help="Output folder; frames go to <output>/<video name>/.")
    extract.add_argument("--mode", choices=["auto", "gpu", "cpu"], default="auto")
    extract.add_argument("--json", metavar="FILE", help="Write per-video results as JSON.")
    extract.set_defaults(func=cmd_extract)

    convert = sub.add_parser(
        "convert-tracknet",
        help="Convert an annotated frame folder to TrackNet V1 training data.",
        add_help=False,
    )
    convert.add_argument("converter_args", nargs=argparse.REMAINDER)
    convert.set_defaults(func=cmd_convert)

    return parser


def main(argv=None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)

    from app.utils.logging_setup import configure_logging

    configure_logging(verbose=args.verbose, console=False)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
