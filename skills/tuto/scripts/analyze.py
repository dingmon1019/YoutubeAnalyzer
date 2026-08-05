"""패스 1 오케스트레이션: 다운로드→신호→자막→지도 프레임→보고서. 지도 예산 배분기 소유. §3.3/§4."""
import argparse
import json
import shutil
import sys
from pathlib import Path

import common
import frames
import signals as sig_mod
import transcribe

W_CHAPTER, W_HEAT, W_ACT, W_GRID = 3.0, 2.5, 2.0, 1.0


def _in_ranges(t: float, ranges: list) -> bool:
    return any(r["start"] <= t <= r["end"] for r in ranges)


def allocate_map_budget(duration: float, sig: dict, extra: int = 0) -> list:
    if duration <= 0:
        return []
    n = min(40, max(12, round(duration / 60 * 1.2)))
    target = n + max(0, extra)
    min_gap = max(8.0, duration / n / 2)
    sb = sig.get("sponsorblock", [])
    cands = []                                     # (weight, t)
    for c in sig.get("chapters", []):
        cands.append((W_CHAPTER, c["start"] + 2.0))
    heat = sorted(sig.get("heatmap", []), key=lambda h: -h["value"])[:10]
    for h in heat:
        cands.append((W_HEAT, (h["start"] + h["end"]) / 2))
    for p in sig.get("activity", {}).get("peaks", []):
        cands.append((W_ACT, float(p)))
    # 그리드는 target(기본 호출이면 n과 동일) 기준으로 촘촘히 — extra로 보강 요청 시 챕터/히트맵/
    # 활동피크가 시간상 몰려 있어도(실측 PlMpk-If9jA: 활동피크 7개가 0~4:27 구간에 편중) 그리드가
    # 유일한 여분 후보 공급원이 되므로, n 고정 그리드로는 채워줄 후보가 애초에 없어 extra가
    # 무의미해진다. min_gap은 base n으로 고정(간격 하한 의미 유지), 그리드 밀도만 target을 따른다.
    for i in range(target):
        cands.append((W_GRID, duration * (i + 0.5) / target))
    cands = [
        (w, max(0.0, min(duration, t))) for w, t in cands
        if 0 <= t <= duration and not _in_ranges(t, sb)
    ]

    # 고정 앵커(시작·끝)도 다른 후보와 동일하게 min_gap·[0,duration] 불변식을 지켜야 한다.
    # 매우 짧은/0에 가까운 영상에서는 t=1.0·t=duration-2가 서로 붙거나(간격 위반) 아예
    # 영상 길이를 벗어날 수 있어(경계 위반), 무조건 포함이 아니라 조건부로 포함한다.
    start_anchor = max(0.0, min(duration, 1.0 if duration > 2 else duration / 2))
    picked = [start_anchor]
    if duration > 4:
        end_anchor = max(0.0, min(duration, duration - 2.0))
        if end_anchor - start_anchor >= min_gap:
            picked.append(end_anchor)

    for w, t in sorted(cands, key=lambda x: -x[0]):
        if len(picked) >= target:
            break
        if all(abs(t - p) >= min_gap for p in picked):
            picked.append(t)
    return sorted(picked)[:target]


def extract_map_frames(video_path: Path, duration: float, sig: dict, out_dir: Path) -> tuple:
    """지도 프레임 추출: allocate_map_budget()의 floor는 "최소 커버리지" 보장이지 희망사항이
    아니다. dedup이 근접중복(예: 정지 화면 인접 프레임)을 솎아내며 그 floor를 갉아먹으면,
    다음 순위 후보를 추가로 요청해(extra) 목표치를 재충전한다. allocate_map_budget(extra=k)의
    선택 순서는 extra=0일 때와 동일한 그리디 결정열의 연장이므로(같은 cands, 같은 정렬,
    target만 다름) 항상 이전 결과의 상위집합을 반환 — 이미 추출된 프레임은 frames.extract_frames
    의 존재 확인으로 재추출되지 않는다. 후보 풀이 소진되면(더 못 늘면) 있는 그대로 반환한다 —
    변화가 적은 짧은 영상의 정상적 한계다."""
    ts = allocate_map_budget(duration, sig)
    target = len(ts)
    kept, dropped = [], 0
    extra = 0
    for _ in range(4):
        raw = frames.extract_frames(video_path, sorted(ts), 512, out_dir)
        kept, dropped = frames.dedup_frames(raw)
        if len(kept) >= target:
            break
        extra += max(1, target - len(kept))
        grown = allocate_map_budget(duration, sig, extra=extra)
        if len(grown) <= len(ts):
            break                                    # 후보 풀 소진 — 더 보강 불가
        ts = grown
    return kept, dropped


def download(url: str, cd: Path) -> dict:
    """yt-dlp 720p+info.json+자막(원어, auto 포함) 한 번에. info.json 반환. 이미 있으면 재사용.

    2단계 다운로드인 이유: --sub-langs "ko,en"처럼 후보 언어를 먼저 나열해 버리면, 한국어
    영상에서도 subs.ko.vtt(원어)와 subs.en.vtt(자동번역)가 함께 받아진다.
    transcribe.get_transcript()는 cache_dir의 subs*.vtt를 sorted()[0]으로 골라 쓰므로
    "en" < "ko" 알파벳 순서상 번역본이 원어를 조용히 이겨버린다. 그래서 1단계로 메타데이터만
    먼저 받아 info.json의 실제 language를 확인한 뒤, 2단계에서 그 언어(+ -orig 변형)만
    --sub-langs로 요청해 원어 자막 파일만 남긴다.
    """
    info_f = cd / "info.json"
    video_f = cd / "video.mp4"

    if not info_f.exists():
        # 1단계: 메타데이터만 (영상 다운로드 없음)
        common.run([
            "yt-dlp", url,
            "--skip-download", "--write-info-json", "-o", f"infojson:{cd / 'info'}",
            "--no-playlist", "--no-progress",
        ], timeout=300)
        # yt-dlp의 `-o "infojson:<cd>/info"` 템플릿은 "<cd>/info.info.json"을 만든다
        # ("<cd>/info.json"이 아님) — 나머지 파이프라인이 고정 파일명에 의존할 수 있도록 정규화.
        matches = list(cd.glob("*.info.json"))
        if matches:
            matches[0].rename(info_f)

    info = json.loads(info_f.read_text(encoding="utf-8", errors="replace"))

    if not video_f.exists():
        # 2단계: 실제 미디어 + 자막. language는 1단계(또는 기존 info.json)에서 확인한 값.
        lang = info.get("language")
        sub_langs = f"{lang},{lang}-orig" if lang else "ko,en"
        common.run([
            "yt-dlp", url,
            "-f", "bv*[height<=720]+ba/b[height<=720]", "--merge-output-format", "mp4",
            "-o", str(video_f),
            "--write-subs", "--write-auto-subs", "--sub-langs", sub_langs,
            "--sub-format", "vtt", "-o", f"subtitle:{cd / 'subs'}",
            "--no-playlist", "--no-progress",
        ], timeout=1800)

    return info


def lru_evict() -> list:
    limit = int(common.load_config().get("CACHE_MAX_VIDEOS", "10"))
    dirs = [d for d in common.CACHE_ROOT.iterdir() if d.is_dir()] if common.CACHE_ROOT.exists() else []
    dirs.sort(key=lambda d: d.stat().st_mtime)
    evicted = []
    excess = [d for d in dirs if (d / "video.mp4").exists()]
    while len(excess) > limit:
        victim = excess.pop(0)
        for name in ("video.mp4", "audio.mp3"):
            (victim / name).unlink(missing_ok=True)
        evicted.append(victim.name)
    return evicted


def cleanup() -> None:
    if not common.CACHE_ROOT.exists():
        print("cache: empty")
        return
    total = 0
    for d in common.CACHE_ROOT.iterdir():
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        total += size
        print(f"  {d.name}  {size / 1e6:.0f} MB")
    shutil.rmtree(common.CACHE_ROOT)
    print(f"cache: removed {total / 1e6:.0f} MB total")


def run_pass1(url: str) -> int:
    vid = common.video_id_from_url(url)
    cd = common.cache_dir(vid)
    info = download(url, cd)
    duration = float(info.get("duration") or 0)
    sig = sig_mod.build_signals(info, vid, cd / "video.mp4")
    (cd / "signals.json").write_text(json.dumps(sig, ensure_ascii=False, indent=1), encoding="utf-8")
    tr = transcribe.get_transcript(cd, mode="auto")

    kept, dropped = extract_map_frames(cd / "video.mp4", duration, sig, cd / "frames")

    hm_top = sorted(sig["heatmap"], key=lambda h: -h["value"])[:10]
    print(f"=== YTA PASS1: {vid} ===")
    print(
        f"STATUS duration={common.fmt_ts(duration)} transcript={tr['source']}({tr['lang']}) "
        f"segments={len(tr['segments'])} dupes_removed={tr['dupes_removed']} "
        f"heatmap={'yes' if sig['heatmap'] else 'no'} chapters={len(sig['chapters'])} "
        f"desc_ts={len(sig['desc_timestamps'])} sponsorblock={len(sig['sponsorblock'])}segs "
        f"activity={len(sig['activity']['curve'])}pts/{len(sig['activity']['peaks'])}peaks "
        f"map_frames={len(kept)}({dropped} dup-dropped) flags={(sig['flags'] + tr['flags']) or 'none'}"
    )
    print("== TRANSCRIPT ==")
    for s in tr["segments"]:
        print(f"[{common.fmt_ts(s['start'])}] {s['text']}")
    print("== CHAPTERS ==")
    for c in sig["chapters"]:
        print(f"[{common.fmt_ts(c['start'])}] {c['title']}")
    print("== DESC_TIMESTAMPS ==")
    for d in sig["desc_timestamps"]:
        print(f"[{common.fmt_ts(d['t'])}] {d['label']}")
    print("== SPONSORBLOCK ==")
    for s in sig["sponsorblock"]:
        print(f"[{common.fmt_ts(s['start'])}-{common.fmt_ts(s['end'])}] {s['category']}")
    print("== HEATMAP_TOP ==")
    for h in hm_top:
        print(f"[{common.fmt_ts((h['start'] + h['end']) / 2)}] {h['value']:.2f}")
    print("== ACTIVITY_PEAKS ==")
    print(", ".join(common.fmt_ts(p) for p in sig["activity"]["peaks"]) or "(none)")
    print("== FRAMES ==")
    frames.report(kept)
    print(f"== CACHE == {cd}")
    if duration > 1860:
        print("WARNING: video exceeds 30min design target — map is sparse; consider --ranges zoom on a section")
    evicted = lru_evict()
    if evicted:
        print(f"lru_evicted: {evicted}")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # Windows cp949 콘솔에서 em-dash 등 크래시 방지
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--cleanup", action="store_true")
    args = ap.parse_args()
    if args.cleanup:
        cleanup()
        return 0
    if not args.url:
        ap.error("url required")
    return run_pass1(args.url)


if __name__ == "__main__":
    sys.exit(main())
