"""Benchmark frame extraction: CPU vs GPU (NVDEC) pipelines.

Measures, per run: wall time, frames, throughput, output size, average and
peak process-tree CPU %, and (when an NVIDIA GPU is present) GPU, NVDEC
decoder utilisation and GPU memory sampled with nvidia-smi during the run.
A non-zero decoder utilisation during GPU runs (and ~0 during CPU runs) is
the evidence that NVDEC was really used.

Usage:
  python tools/benchmark_extraction.py --generate 720p50:120 --runs 3 --json out.json
  python tools/benchmark_extraction.py --video "my clip.mp4" --modes cpu gpu
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil  # noqa: E402

from app.hardware.capabilities import find_nvidia_smi, get_report  # noqa: E402
from app.processing.exporter import VideoExporter  # noqa: E402
from app.utils import proc  # noqa: E402
from app.utils.ffmpeg import probe_ffmpeg  # noqa: E402

PRESETS = {
    "720p50": ("1280x720", 50),
    "1080p30": ("1920x1080", 30),
    "1080p60": ("1920x1080", 60),
    "4k30": ("3840x2160", 30),
}


def generate(spec: str, directory: Path) -> Path:
    name, seconds = spec.split(":")
    size, rate = PRESETS[name]
    path = directory / f"bench_{name}_{seconds}s.mp4"
    if not path.exists():
        info = probe_ffmpeg()
        print(f"Generating {path.name} ...", flush=True)
        # testsrc2 + noise gives realistic-ish decode cost (pure test
        # patterns compress unrealistically well).
        subprocess.run(
            [
                info.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}",
                "-vf", "noise=alls=12:allf=t",
                "-t", seconds, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-g", str(rate * 2), "-pix_fmt", "yuv420p", str(path),
            ],
            check=True, **proc.popen_kwargs(),
        )
    return path


class Sampler(threading.Thread):
    def __init__(self, smi: str | None):
        super().__init__(daemon=True)
        self.smi = smi
        self.running = True
        self.cpu: list[float] = []
        self.gpu: list[float] = []
        self.dec: list[float] = []
        self.mem: list[float] = []
        psutil.cpu_percent(None)

    def run(self):
        while self.running:
            self.cpu.append(psutil.cpu_percent(None))
            if self.smi:
                r = proc.run(
                    [self.smi, "--query-gpu=utilization.gpu,utilization.decoder,memory.used",
                     "--format=csv,noheader,nounits"],
                    timeout=3,
                )
                if r is not None and r.returncode == 0 and r.stdout.strip():
                    try:
                        g, d, m = [float(x) for x in r.stdout.strip().splitlines()[0].split(",")]
                        self.gpu.append(g)
                        self.dec.append(d)
                        self.mem.append(m)
                    except ValueError:
                        pass
            time.sleep(0.25)

    def stop(self):
        self.running = False
        self.join()


def stats(values):
    return (round(statistics.mean(values), 1), round(max(values), 1)) if values else (None, None)


def run_once(video: Path, mode: str, gpu_ready: bool, smi: str | None, workdir: Path) -> dict:
    out = workdir / f"out_{mode}"
    shutil.rmtree(out, ignore_errors=True)
    errors = []
    exporter = VideoExporter(mode=mode, gpu_ready=gpu_ready, on_error=errors.append)
    baseline_mem = None
    if smi:
        r = proc.run([smi, "--query-gpu=memory.used", "--format=csv,noheader,nounits"], timeout=3)
        if r is not None and r.returncode == 0:
            baseline_mem = float(r.stdout.strip().splitlines()[0])
    sampler = Sampler(smi)
    sampler.start()
    t0 = time.perf_counter()
    result = exporter.export_video(video, out)
    elapsed = time.perf_counter() - t0
    sampler.stop()
    frames_dir = out / video.stem
    frames = list(frames_dir.glob("*.jpg"))
    size = sum(f.stat().st_size for f in frames)
    cpu = stats(sampler.cpu)
    gpu = stats(sampler.gpu)
    dec = stats(sampler.dec)
    mem = stats(sampler.mem)
    shutil.rmtree(out, ignore_errors=True)
    return {
        "mode": mode,
        "ok": result is True,
        "error": errors[0] if errors else None,
        "pipeline": exporter.last_pipeline,
        "seconds": round(elapsed, 3),
        "frames": len(frames),
        "fps": round(len(frames) / elapsed, 1) if elapsed else None,
        "output_mb": round(size / 1048576, 1),
        "cpu_avg_pct": cpu[0], "cpu_peak_pct": cpu[1],
        "gpu_avg_pct": gpu[0], "gpu_peak_pct": gpu[1],
        "nvdec_avg_pct": dec[0], "nvdec_peak_pct": dec[1],
        "gpu_mem_peak_mb": mem[1],
        "gpu_mem_delta_mb": (round(mem[1] - baseline_mem, 1)
                             if mem[1] is not None and baseline_mem is not None else None),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", action="append", default=[], help="Video file(s) to benchmark.")
    parser.add_argument("--generate", action="append", default=[],
                        help=f"Synthetic clip PRESET:SECONDS, presets: {', '.join(PRESETS)}")
    parser.add_argument("--modes", nargs="+", default=["cpu", "gpu"], choices=["cpu", "gpu", "auto"])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--workdir", default=None)
    parser.add_argument("--json", default=None)
    args = parser.parse_args(argv)

    workdir = Path(args.workdir or tempfile.mkdtemp(prefix="tnp-bench-"))
    workdir.mkdir(parents=True, exist_ok=True)
    videos = [Path(v) for v in args.video] + [generate(s, workdir) for s in args.generate]
    if not videos:
        parser.error("give --video or --generate")

    report = get_report()
    smi = find_nvidia_smi() if report.gpu_detected else None
    env = {
        "platform": f"{platform.system()} {platform.release()}",
        "os": report.os_version,
        "cpu": platform.processor() or platform.machine(),
        "cpu_threads": report.cpu_threads,
        "ram_gb": round(report.ram_total_gb, 1),
        "ffmpeg": report.ffmpeg["version"] if report.ffmpeg else None,
        "gpu": report.gpus[0].name if report.gpus else None,
        "driver": report.driver_version,
        "nvdec": report.nvdec_state,
    }
    print(json.dumps(env, indent=2))

    results = []
    for video in videos:
        info = VideoExporter().get_video_info(video)
        meta = {
            "video": video.name,
            "resolution": f"{info.width}x{info.height}",
            "fps_source": round(info.fps, 3),
            "codec": info.codec,
            "frames_expected": info.total_frames,
            "size_mb": round(video.stat().st_size / 1048576, 1),
            "duration_s": round(info.duration, 2),
        }
        for mode in args.modes:
            if mode == "gpu" and not report.gpu_pipeline_ready:
                results.append({**meta, "mode": mode, "skipped": "NVDEC not verified"})
                print(f"{video.name} [{mode}] skipped: NVDEC not verified", flush=True)
                continue
            runs = []
            for i in range(args.runs):
                r = run_once(video, mode, report.gpu_pipeline_ready, smi, workdir)
                runs.append(r)
                print(f"{video.name} [{mode}] run {i + 1}: {r['seconds']}s {r['fps']} fps "
                      f"cpu {r['cpu_avg_pct']}% nvdec {r['nvdec_avg_pct']}% ok={r['ok']}", flush=True)
            best = min((r for r in runs if r["ok"]), key=lambda r: r["seconds"], default=runs[0])
            results.append({
                **meta, **best,
                "runs": len(runs),
                "seconds_median": round(statistics.median(r["seconds"] for r in runs), 3),
                "fps_median": round(statistics.median(r["fps"] or 0 for r in runs), 1),
            })

    output = {"environment": env, "results": results}
    if args.json:
        Path(args.json).write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"Wrote {args.json}")
    else:
        print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
