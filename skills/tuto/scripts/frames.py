"""프레임 추출 + dedup. 지도(analyze)와 확대(zoom)가 공용. §4."""
import argparse
import subprocess
import sys
from pathlib import Path

import common


def extract_frames(video, timestamps: list, res: int, out_dir) -> list:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for t in timestamps:
        p = out_dir / f"{common.ts_tag(t)}_{res}.jpg"
        if not p.exists():
            common.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", video,
                        "-frames:v", "1", "-vf", f"scale={res}:-2", "-q:v", "3", p])
        if p.exists():
            paths.append(p)
    return paths


def _thumb(path) -> bytes:
    p = subprocess.run(
        ["ffmpeg", "-i", str(path), "-vf", "scale=16:16,format=gray",
         "-f", "rawvideo", "-v", "error", "-"],
        capture_output=True, timeout=60,
    )
    return p.stdout[:256]


def dedup_frames(paths: list, threshold: float = 2.0) -> tuple:
    kept, ref = [], None
    for p in paths:
        t = _thumb(p)
        if len(t) < 256:
            kept.append(p)          # 썸네일 실패 프레임은 보수적으로 유지
            continue
        if ref is not None:
            diff = sum(abs(a - b) for a, b in zip(ref, t)) / 256
            if diff <= threshold:
                continue
        kept.append(p)
        ref = t
    return kept, len(paths) - len(kept)


def report(paths: list) -> None:
    for p in paths:
        tag = p.name.split("_")[0][1:]          # t0312 → 0312
        mmss = tag[:-2] + ":" + tag[-2:] if len(tag) <= 4 else tag[:-4] + ":" + tag[-4:-2] + ":" + tag[-2:]
        print(f"FRAME {p} t={mmss}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--timestamps", required=True, help="쉼표구분 초/MM:SS")
    ap.add_argument("--res", type=int, default=512)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-dedup", action="store_true")
    args = ap.parse_args()
    ts = [common.parse_ts(x) for x in args.timestamps.split(",") if x.strip()]
    paths = extract_frames(Path(args.video), ts, args.res, Path(args.out))
    dropped = 0
    if not args.no_dedup:
        paths, dropped = dedup_frames(paths)
    print(f"frames: {len(paths)} kept, {dropped} dup-dropped, res={args.res}")
    report(paths)
    return 0


if __name__ == "__main__":
    sys.exit(main())
