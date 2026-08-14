"""yta 공용 유틸: 설정·캐시 경로·시간 파싱·subprocess. 스크립트 간 유일한 공유 모듈."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

CACHE_ROOT = Path.home() / ".yta" / "cache"
CONFIG_FILE = Path.home() / ".config" / "yta" / ".env"

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    cfg = {}
    for line in CONFIG_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    return cfg


def cache_dir(video_id: str) -> Path:
    d = CACHE_ROOT / video_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def parse_ts(s: str) -> float:
    parts = [float(p) for p in str(s).split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def fmt_ts(sec: float) -> str:
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def ts_tag(sec: float) -> str:
    return "t" + fmt_ts(sec).replace(":", "")


def video_id_from_url(url: str) -> str:
    url = url.strip()
    if _ID_RE.match(url):
        return url
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", url)
    if not m:
        raise ValueError(f"cannot extract video id from: {url}")
    return m.group(1)


def run(cmd: list, timeout: int = 600) -> subprocess.CompletedProcess:
    p = subprocess.run(
        [str(c) for c in cmd], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    if p.returncode != 0:
        raise RuntimeError(
            f"command failed ({p.returncode}): {' '.join(str(c) for c in cmd)}\n{p.stderr[-2000:]}"
        )
    return p


def frame_label(path) -> str:
    """프레임 파일명(t0312_512.jpg / t0312d5_1024.jpg / t0618d4_1024c10_200_400_120.jpg)에서 t=MM:SS 라벨을
    복원한다. frames.report가 쓰는 공용 헬퍼 — 크롭 파일명(c 접미사) 포함 파싱 규칙을 한
    곳에 둔다. 구 frames.report()는 p.name만 참조하고 Path(p)로 재구성하지 않았다 — 테스트 더블(예:
    test_zoom.py의 name 속성만 있는 mock 객체)이 그 경로를 타므로, 이미 .name이 있으면
    그대로 쓰고 없을 때만 Path()로 감싸 하위 호환을 유지한다."""
    name = path.name if hasattr(path, "name") else Path(path).name
    tag = name.split("_")[0][1:]                # t0312d5 → 0312d5
    tag = tag.split("d")[0].split("c")[0]       # 데시초·크롭 접미사 제거
    if len(tag) <= 4:
        return tag[:-2] + ":" + tag[-2:]
    return tag[:-4] + ":" + tag[-4:-2] + ":" + tag[-2:]


def utf8_stdout() -> None:
    """stdout/stderr를 UTF-8로 강제한다. Windows에서 파이프로 실행되면 기본 인코딩이
    로케일(cp949)이라 한글·em-dash가 깨진 바이트로 나간다 — errors만 바꾸는 것으로는
    부족하고(과거 결함) encoding까지 지정해야 한다. reconfigure 미지원 스트림(테스트
    캡처 등)은 조용히 무시한다."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def detect_js_runtime() -> str:
    """yt-dlp EJS용 JS 런타임 탐지. yt-dlp는 deno만 기본 활성이라 deno가 있으면 플래그가
    필요 없고, node/bun은 다운로드 명령에 --js-runtimes로 명시해야 쓰인다. 없으면 ""
    — 2026-08-14 실측: 런타임 부재 시 YouTube 다운로드가 HTTP 403으로 즉사했다."""
    for rt in ("deno", "node", "bun"):
        if shutil.which(rt):
            return rt
    return ""
