"""yta 공용 유틸: 설정·캐시 경로·시간 파싱·subprocess. 스크립트 간 유일한 공유 모듈."""
import re
import subprocess
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
