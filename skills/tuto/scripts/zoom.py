"""패스 2 확대·검증 재확대·Q&A 재확대. 확대 예산 가드 소유. §3.3/§4."""
import argparse
import sys
from pathlib import Path

import common
import frames

RANGE_CAP = 20
GLOBAL_CAP = 60
MAX_FPS = 2.0


def _parse_res(token: str):
    if "@" in token:
        body, res = token.rsplit("@", 1)
        return body, int(res)
    return token, 512


def parse_ranges(spec: str) -> list:
    out = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        body, res = _parse_res(token)
        a, b = body.split("-")
        out.append({"start": common.parse_ts(a), "end": common.parse_ts(b), "res": res})
    return out


def parse_single(spec: str) -> list:
    out = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        body, res = _parse_res(token)
        out.append((common.parse_ts(body), res))
    return out


def plan_timestamps(ranges: list) -> list:
    per_range = []
    for r in ranges:
        dur = max(0.5, r["end"] - r["start"])
        count = min(RANGE_CAP, max(1, int(dur * MAX_FPS)))
        step = dur / count
        per_range.append([(r["start"] + step * (i + 0.5), r["res"]) for i in range(count)])
    total = sum(len(x) for x in per_range)
    while total > GLOBAL_CAP:                      # 균등 감축: 가장 많은 구간에서 1장씩
        biggest = max(per_range, key=len)
        if len(biggest) <= 1:
            break
        biggest.pop(len(biggest) // 2)
        total -= 1
    return [t for chunk in per_range for t in chunk]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="video_id 또는 캐시 경로")
    ap.add_argument("--ranges")
    ap.add_argument("--timestamps")
    args = ap.parse_args()
    cd = Path(args.target) if Path(args.target).exists() else common.CACHE_ROOT / args.target
    video = cd / "video.mp4"
    if not video.exists():
        print(f"ERROR: video.mp4 evicted — re-run analyze.py <url> to re-download ({cd})")
        return 3
    if args.ranges:
        plan = plan_timestamps(parse_ranges(args.ranges))
    elif args.timestamps:
        plan = parse_single(args.timestamps)
    else:
        ap.error("--ranges or --timestamps required")
    by_res = {}
    for t, res in plan:
        by_res.setdefault(res, []).append(t)
    kept_all, dropped_all = [], 0
    for res, ts in sorted(by_res.items()):
        raw = frames.extract_frames(video, ts, res, cd / "frames")
        kept, dropped = frames.dedup_frames(raw)
        kept_all.extend(kept)
        dropped_all += dropped
    print(f"zoom: {len(kept_all)} kept, {dropped_all} dup-dropped, "
          f"ranges={args.ranges or args.timestamps}")
    frames.report(sorted(kept_all, key=lambda p: p.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
