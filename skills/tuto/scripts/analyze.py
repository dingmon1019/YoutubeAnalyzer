"""패스 1 오케스트레이션: 다운로드→신호→자막→지도 프레임→보고서. 지도 예산 배분기 소유. §3.3/§4."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import common
import evidence
import frames
import signals as sig_mod
import transcribe

W_CHAPTER, W_HEAT, W_ACT, W_GRID = 3.0, 2.5, 2.0, 1.0


def _in_ranges(t: float, ranges: list) -> bool:
    return any(r["start"] <= t <= r["end"] for r in ranges)


def allocate_map_budget(duration: float, sig: dict, extra: int = 0) -> list:
    if duration <= 0:
        return []
    # solo 모드(스펙 2026-08-18 §4): 지도는 확대 판정용 개요다 — 값 판독은 확대가 담당하므로
    # 밀도를 절반으로 줄인다. 11:27 영상 기준 14 → 8장, 30분 캡 40 → 16장.
    n = min(16, max(6, round(duration / 60 * 0.7)))
    target = min(16, n + max(0, extra))            # 상한 16은 extra 보강에도 재적용(§3.3 예산 상한, solo 모드)
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
    다음 순위 후보를 추가로 요청해(extra) 목표치를 재충전한다.

    **target-growth retry with best-of selection이지 상위집합(superset) 보장이 아니다.**
    allocate_map_budget(extra=k)는 그리드를 매번 target 기준으로 재생성하므로(§P4 참조) 이전
    호출과 그리드 후보 자체가 달라져, 라운드가 진행될수록 결과가 항상 더 커지거나 이전 결과를
    포함한다는 보장이 없다 — 오히려 그리드가 촘촘해질수록 인접 후보가 시각적으로 더 비슷해져
    dedup에서 더 많이 깎일 수 있다(실측: EMPTY_SIG에서 extra=1 시 상위집합 불성립 확인). 그래서
    라운드마다 kept 개수를 비교해 **최댓값(best-so-far)** 만 유지한다 — 나중 라운드가 더
    나쁘면 그 결과는 버리고 이전 best를 반환한다. target은 allocate_map_budget 쪽에서 40으로
    상한(§3.3 예산 상한)이 걸려 있어, extra가 아무리 커져도 그리드 재생성 결과가 결국
    수렴하고(더 못 늘어나면 grown이 성장을 멈춰) 루프가 유한 회 안에 종료된다."""
    ts = allocate_map_budget(duration, sig)
    target = len(ts)
    best_kept, best_dropped = [], 0
    extra = 0
    for _ in range(4):
        raw = frames.extract_frames(video_path, sorted(ts), 512, out_dir)
        kept, dropped = frames.dedup_frames(raw)
        if len(kept) > len(best_kept):
            best_kept, best_dropped = kept, dropped
        if len(best_kept) >= target:
            break
        extra += max(1, target - len(best_kept))
        grown = allocate_map_budget(duration, sig, extra=extra)
        if len(grown) <= len(ts):
            break                                    # 후보 풀 소진(또는 40 상한 도달) — 더 보강 불가
        ts = grown
    return best_kept, best_dropped


def _pick_lang_from_info(info: dict) -> str:
    """info['subtitles'] 다음 info['automatic_captions'] 순으로 실제 트랙 딕셔너리 키를
    조사해 원어로 보이는 트랙 코드 하나를 고른다. 하이픈 포함 키(지역 변형·자동자막의
    "-orig" 자체 등)는 표기 변형/파생 트랙으로 보고 후보에서 제외한다. 남은 후보 중
    "ko" 우선, 그다음 "en", 그래도 없으면 (딕셔너리 삽입 순서상) 첫 키를 쓴다. 두 필드가
    다 없거나 비어 있으면 빈 문자열을 반환해 호출부가 기존 폴백("ko,en")을 쓰게 한다."""
    for field in ("subtitles", "automatic_captions"):
        keys = [k for k in (info.get(field) or {}).keys() if "-" not in k]
        if not keys:
            continue
        if "ko" in keys:
            return "ko"
        if "en" in keys:
            return "en"
        return keys[0]
    return ""


def _sub_langs_for(lang: str, info: dict = None) -> str:
    """언어 코드 → yt-dlp `--sub-langs` 후보 CSV. YouTube의 info['language']는 지역 변형
    (예: en-US, ko-KR)일 수 있지만 자막/자동자막 트랙 딕셔너리 키는 보통 기본 코드(en, ko)다.
    exact-match인 --sub-langs에 지역 변형만 넘기면 조용히 0건 매치되어(에러 없이 그냥 subs
    파일이 안 생김) 자막 사슬 전체가 whisper 폴백으로 샌다 — 실측(YKSpANU8jPE, language=
    en-US)에서 STATUS가 captions(en) 대신 local()로 나온 원인. 같은 언어의 표기 변형만
    넓히므로 함수 docstring이 경계하는 "다른 언어가 함께 받아지는" 오염 위험은 없다.

    lang 자체가 없는 영상(info['language'] 필드 부재)은 예전엔 무조건 "ko,en"을 요청해,
    두 트랙이 다 있는 한국어 영상에서도 영어 자동번역이 섞여 들어올 여지가 있었다 —
    info가 주어지면 실제 트랙 목록(_pick_lang_from_info)을 먼저 봐서 그 오염을 줄인다."""
    if not lang:
        lang = _pick_lang_from_info(info) if info else ""
        if not lang:
            return "ko,en"
    base = lang.split("-")[0]
    seen = dict.fromkeys((lang, f"{lang}-orig", base, f"{base}-orig"))  # 순서 보존 dedup
    return ",".join(seen)


def _media_cmd(url, video_f, cd, sub_langs, js_rt: str = "", android: bool = False) -> list:
    """미디어+자막 yt-dlp 명령 구성. deno는 yt-dlp가 자동 사용하므로 node/bun만 명시한다."""
    cmd = ["yt-dlp", url]
    if js_rt in ("node", "bun"):
        cmd += ["--js-runtimes", js_rt]
    if android:
        cmd += ["--extractor-args", "youtube:player_client=android"]
    cmd += [
        "-f", "bv*[height<=720]+ba/b[height<=720]", "--merge-output-format", "mp4",
        "-o", str(video_f),
        "--write-subs", "--write-auto-subs", "--sub-langs", sub_langs,
        "--sub-format", "vtt", "-o", f"subtitle:{cd / 'subs'}",
        "--no-playlist", "--no-progress",
    ]
    return cmd


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
        sub_langs = _sub_langs_for(info.get("language"), info)
        js_rt = common.detect_js_runtime()
        try:
            common.run(_media_cmd(url, video_f, cd, sub_langs, js_rt), timeout=1800)
        except RuntimeError as e:
            # 재시도 루프가 아니라 방법 전환 1회다(§9 재시도 금지와 구분). 실측(2026-08-14):
            # 403 2건 모두 android client 전환 1회로 해소. 조용한 폴백 금지 — NOTE를 남겨
            # 패스1 보고서에 실리게 한다.
            print(f"NOTE: media download failed once — retrying with android player client "
                  f"({(str(e).splitlines() or [str(e)])[-1][:120]})")
            common.run(_media_cmd(url, video_f, cd, sub_langs, js_rt, android=True),
                       timeout=1800)

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


def _load_or_build_signals(cd: Path, info: dict, vid: str) -> dict:
    """signals.json이 video.mp4보다 새로우면 재사용한다 — build_signals의 활동곡선이
    전체 영상을 디코드해 캐시 히트 재실행도 ~100초를 쓰던 것을 없앤다(스펙 D5).
    eviction 후 재다운로드는 video.mp4 mtime이 새로워져 자동 무효화. 파손·비정형
    파일은 재계산한다."""
    sig_f = cd / "signals.json"
    video_f = cd / "video.mp4"
    if sig_f.exists() and video_f.exists() and sig_f.stat().st_mtime >= video_f.stat().st_mtime:
        try:
            sig = json.loads(sig_f.read_text(encoding="utf-8"))
            if isinstance(sig, dict) and "activity" in sig and "flags" in sig:
                return sig
        except (json.JSONDecodeError, OSError):
            pass
    sig = sig_mod.build_signals(info, vid, video_f)
    sig_f.write_text(json.dumps(sig, ensure_ascii=False, indent=1), encoding="utf-8")
    return sig


def run_pass1(url: str) -> int:
    vid = common.video_id_from_url(url)
    cd = common.cache_dir(vid)
    info = download(url, cd)
    duration = float(info.get("duration") or 0)
    sig = _load_or_build_signals(cd, info, vid)
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
    # evidence 골격을 여기서 만들어 둔다 — 하류(판독 에이전트·빌더·감사)가 직접 JSON을
    # 쓰지 않고 evidence.py CLI로만 기여하게 해서 스키마 위반을 exit 2로 잡기 위함이다.
    ev = evidence.build_skeleton(info, sig, tr, kept, url)
    evidence.save(cd, ev)
    print("== EVIDENCE ==")
    print(evidence.summary_line(ev))
    hint = ev["video_type"]["hint"]
    print(f"TYPE_HINT candidates={'|'.join(hint['candidates'])} basis={hint['basis']}")
    print(f"EVIDENCE_FILE {evidence.evidence_path(cd)}")
    print(f"== CACHE == {cd}")
    if duration > 1860:
        print("WARNING: video exceeds 30min design target — map is sparse; consider --ranges zoom on a section")
    transcript_chars = sum(len(s["text"]) for s in tr["segments"])
    if transcript_chars > 30000:
        # v1은 자동 압축하지 않는다(fail-loud) — §3.3 토큰 예산(패스1 자막 ~15k) 초과
        # 가능성을 사람이 보게만 한다.
        print(f"WARNING: transcript large (~{transcript_chars // 1000}k chars) — "
              f"consider chapter-level condensation per spec §3.3")
    evicted = lru_evict()
    if evicted:
        print(f"lru_evicted: {evicted}")
    return 0


def main() -> int:
    common.utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--cleanup", action="store_true")
    args = ap.parse_args()
    if args.cleanup:
        cleanup()
        return 0
    if not args.url:
        ap.error("url required")
    try:
        return run_pass1(args.url)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        # design §9 fail-loud: traceback 금지 — 원인 요약과 다음 행동만 평문으로.
        # stdout은 pass1-report.txt로 리다이렉트될 수 있어 stderr에도 한 줄 미러한다.
        msg = str(e)[:600]
        print("=== YTA PASS1: FAILED ===")
        print(f"ERROR: {msg}")
        if "403" in msg:
            print("HINT: JS 런타임(deno/node) 부재 가능 — setup.py --check의 NOTE 확인. "
                  "일시적 차단일 수 있으니 잠시 후 재실행도 유효하다.")
        print(f"ERROR: pass1 failed — {(msg.splitlines() or [msg])[-1][:160]}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
