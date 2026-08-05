"""프레임 추출 + dedup. 지도(analyze)와 확대(zoom)가 공용. §4."""
import argparse
import subprocess
import sys
from pathlib import Path

import common


def _frame_tag(sec: float) -> str:
    """common.ts_tag은 초 단위로 반올림해 파일명을 만든다 — zoom.py의 초당 다수 프레임
    (예: 5.0초/5.5초)이 같은 정수초로 뭉개지면 두 번째가 "이미 존재"로 취급되거나 dedup에서
    가짜 중복으로 잡힌다. common.ts_tag의 의미(다른 소비자가 그대로 씀)는 건드리지 않고,
    frames 모듈 로컬로 분수부가 있을 때만 데시초 접미사(d<N>)를 덧붙인다 (예: 312.0 ->
    t0312, 312.5 -> t0312d5). 정수초 기준(whole)은 반올림이 아니라 절삭(int())이라 report()가
    이 접미사를 떼어내면 항상 "요청한 초가 속한 정수초"를 보여준다."""
    whole = int(sec)
    frac = round((sec - whole) * 10)
    if frac >= 10:            # 부동소수 반올림 캐리 보정 (예: 4.96 -> whole=5, frac=0)
        whole += 1
        frac = 0
    tag = common.ts_tag(whole)
    return f"{tag}d{frac}" if frac else tag


def extract_frames(video, timestamps: list, res: int, out_dir) -> list:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for t in timestamps:
        p = out_dir / f"{_frame_tag(t)}_{res}.jpg"
        if not p.exists():
            try:
                common.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", video,
                            "-frames:v", "1", "-vf", f"scale={res}:-2", "-q:v", "3", p])
            except RuntimeError:
                # 범위 밖 타임스탬프 등으로 이 한 장이 실패해도 배치 전체를 죽이지 않는다 —
                # 예전엔 여기서 예외가 이미 성공한 프레임까지 통째로 날렸다.
                continue
        if p.exists():
            paths.append(p)
    return paths


_thumb_cache: dict = {}


def _thumb(path) -> bytes:
    """프로세스 내 경로별 메모이즈 — extract_map_frames의 백필 재시도 라운드는 이미
    추출된 동일 파일을 다시 dedup_frames에 넣곤 하는데(실측 2.36초/프레임), 캐시 없이는
    라운드마다 ffmpeg 썸네일을 다시 찍었다."""
    key = str(path)
    cached = _thumb_cache.get(key)
    if cached is not None:
        return cached
    p = subprocess.run(
        ["ffmpeg", "-i", str(path), "-vf", "scale=16:16,format=gray",
         "-f", "rawvideo", "-v", "error", "-"],
        capture_output=True, timeout=60,
    )
    thumb = p.stdout[:256]
    _thumb_cache[key] = thumb
    return thumb


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
        tag = p.name.split("_")[0][1:]          # t0312 → 0312 / t0312d5 → 0312d5
        tag = tag.split("d")[0]                  # 데시초 접미사 제거 — t=MM:SS는 초 단위로만 표시
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
    failed = len(ts) - len(paths)
    dropped = 0
    if not args.no_dedup:
        paths, dropped = dedup_frames(paths)
    msg = f"frames: {len(paths)} kept, {dropped} dup-dropped, res={args.res}"
    if failed:
        msg += f", {failed} failed"
    print(msg)
    report(paths)
    return 0


if __name__ == "__main__":
    sys.exit(main())
