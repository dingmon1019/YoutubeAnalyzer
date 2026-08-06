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


def _probe_duration(path) -> float:
    """ffprobe로 영상 길이 측정. transcribe._probe_duration과 같은 최소 패턴을 로컬로
    복제한다 — zoom.py가 transcribe.py를 임포트하면 스크립트 간 상호 의존이 생겨 모듈
    독립성 규칙(스크립트 각자 단독 실행 가능)이 깨지므로, 공유 대신 최소 복제를 택한다."""
    import subprocess
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    return float(p.stdout.strip())


def _clamp_ranges(ranges: list, duration: float) -> list:
    """범위 밖(영상 길이 초과) 요청이 ffmpeg RuntimeError로 배치 전체를 죽이지 않도록,
    추출 전에 미리 드롭/clamp하고 사람이 보게 note를 남긴다. duration을 모르면(<=0,
    예: ffprobe 실패) 아무 것도 손대지 않는다."""
    if duration <= 0:
        return ranges
    out = []
    for r in ranges:
        if r["start"] >= duration:
            print(f"NOTE: range {common.fmt_ts(r['start'])}-{common.fmt_ts(r['end'])} starts "
                  f"beyond video duration ({common.fmt_ts(duration)}) — dropped")
            continue
        if r["end"] > duration:
            print(f"NOTE: range end {common.fmt_ts(r['end'])} clamped to video duration "
                  f"({common.fmt_ts(duration)})")
            r = dict(r, end=duration)
        out.append(r)
    return out


def _clamp_timestamps(plan: list, duration: float) -> list:
    """--timestamps 모드용 clamp: 단일 타임스탬프는 구간이 아니므로 clamp가 아니라
    드롭만 한다 (duration을 넘는 순간은 애초에 존재하지 않는 프레임이다)."""
    if duration <= 0:
        return plan
    out = []
    for t, res in plan:
        if t > duration:
            print(f"NOTE: timestamp {common.fmt_ts(t)} beyond video duration "
                  f"({common.fmt_ts(duration)}) — dropped")
            continue
        out.append((t, res))
    return out


def _dedup_plan(plan: list) -> list:
    """정확히 같은 (t, res) 쌍이 두 번 계획되면(재확대·Q&A가 이전 계획과 겹칠 때) 추출
    직전에 한 번만 남긴다 — 그대로 두면 파일명은 하나뿐인데 요청은 두 번이라 dedup 카운트가
    "중복"으로 잘못 잡혀 FRAME 카운트가 부정확해진다. 정확한 float 동등성으로만 합친다
    (근접값은 별개 프레임으로 남겨야 하므로 여기서 반올림하지 않는다)."""
    return sorted(set(plan))


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
    common.utf8_stdout()
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
    try:
        duration = _probe_duration(video)
    except Exception:
        duration = 0.0          # ffprobe 실패 — clamp 없이 이전 동작으로 저하(fail-soft)
    if args.ranges:
        plan = plan_timestamps(_clamp_ranges(parse_ranges(args.ranges), duration))
    elif args.timestamps:
        plan = _clamp_timestamps(parse_single(args.timestamps), duration)
    else:
        ap.error("--ranges or --timestamps required")
    plan = _dedup_plan(plan)
    by_res = {}
    for t, res in plan:
        by_res.setdefault(res, []).append(t)
    kept_all, dropped_all, failed_all = [], 0, 0
    pinpoint = bool(args.timestamps)
    for res, ts in sorted(by_res.items()):
        raw = frames.extract_frames(video, ts, res, cd / "frames")
        failed_all += len(ts) - len(raw)
        if pinpoint:
            kept, dropped = raw, 0    # 핀포인트는 명시 요청 시점 — 전량 반환 (스펙 D4)
        else:
            kept, dropped = frames.dedup_frames(raw)
        kept_all.extend(kept)
        dropped_all += dropped
    msg = (f"zoom: {len(kept_all)} kept, {dropped_all} dup-dropped, "
           f"ranges={args.ranges or args.timestamps}")
    if failed_all:
        msg += f", {failed_all} failed"
    print(msg)
    frames.report(sorted(kept_all, key=lambda p: p.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
