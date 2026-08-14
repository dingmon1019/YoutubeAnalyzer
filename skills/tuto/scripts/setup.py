"""프리플라이트: 바이너리·키·선택 의존성 확인 + .env 스캐폴드. §9 P10."""
import argparse
import importlib.util
import json
import shutil
import sys

import common

TEMPLATE = """# yta 설정 — 값을 채우면 저장 즉시 적용
# Groq Whisper (자막 없는 영상용, console.groq.com/keys)
GROQ_API_KEY=
# 캐시에 video.mp4를 유지할 최대 영상 수 (LRU)
CACHE_MAX_VIDEOS=10
"""

# yt-dlp가 이보다 오래되면 유튜브 측 변동에 취약 (§5 P10). 연 2회 갱신.
YTDLP_MIN = "2026.01"


def scaffold_config() -> None:
    if common.CONFIG_FILE.exists():
        return
    common.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    common.CONFIG_FILE.write_text(TEMPLATE, encoding="utf-8")


def check_env() -> dict:
    missing = [b for b in ("ffmpeg", "ffprobe", "yt-dlp") if not shutil.which(b)]
    version, stale = "", False
    if "yt-dlp" not in missing:
        try:
            version = common.run(["yt-dlp", "--version"], timeout=30).stdout.strip()
            stale = version[:7] < YTDLP_MIN
        except Exception:
            stale = True
    cfg = common.load_config()
    return {
        "status": "needs_install" if missing else "ready",
        "missing": missing,
        "ytdlp_version": version,
        "ytdlp_stale": stale,
        "js_runtime": common.detect_js_runtime(),
        "has_groq_key": bool(cfg.get("GROQ_API_KEY")),
        "has_faster_whisper": importlib.util.find_spec("faster_whisper") is not None,
        "config_file": str(common.CONFIG_FILE),
    }


def main() -> int:
    common.utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    scaffold_config()
    r = check_env()
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    if args.check:
        if r["status"] == "ready":
            if r["ytdlp_stale"]:
                # exit 0은 유지한다(설치 자체는 끝난 상태) — 그래도 낡은 버전은 유튜브 측
                # 변동에 취약(§5 P10)하므로 조용히 넘기지 않고 stderr에 흔적을 남긴다.
                print(
                    f"NOTE: yt-dlp {r['ytdlp_version']} looks stale (< {YTDLP_MIN}) — "
                    f"update recommended: pip install -U yt-dlp",
                    file=sys.stderr,
                )
            if r.get("js_runtime") == "":
                # .get: 기존 테스트의 레거시 mock dict(키 부재)를 침묵 경로로 보존 (append-only)
                # 실측(2026-08-14): 런타임 부재 시 유튜브 다운로드가 403으로 즉사 —
                # 설치 자체는 끝난 상태이므로 exit 0은 유지하고 stderr에만 남긴다(F6 선례).
                print(
                    "NOTE: no JS runtime for yt-dlp (deno/node/bun) — YouTube downloads "
                    "may fail with HTTP 403. install: winget install DenoLand.Deno",
                    file=sys.stderr,
                )
            return 0
        print("MISSING: " + ", ".join(r["missing"]), file=sys.stderr)
        print("install: winget install Gyan.FFmpeg ; pip install -U yt-dlp", file=sys.stderr)
        return 2
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
