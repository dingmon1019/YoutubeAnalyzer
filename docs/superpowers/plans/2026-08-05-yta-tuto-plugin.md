# yta (`/tuto`) 유튜브 튜토리얼 분석 플러그인 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 30분 이내 한/영 튜토리얼 영상을 ~60k 토큰으로 분석해 스텝 가이드·요약·Q&A 상태를 산출하는 Claude Code 플러그인.

**Architecture:** 2-패스 coarse-to-fine + 검증 패스 (스펙 §3.3). 패스 1이 신호(히트맵·챕터·SponsorBlock·활동 곡선)와 자막으로 지도를 만들고, Claude가 확대 계획(zoom-plan.json)을 판정하면 패스 2가 핵심 구간만 고밀도 추출한다. 산출물의 모든 주장은 프레임 근거를 인용하며 표본 감사를 거친다.

**Tech Stack:** Python 3.11+ 순수 stdlib(선택 의존: faster-whisper), yt-dlp·ffmpeg CLI subprocess, pytest(개발용), Claude Code plugin(skills/ 규약).

**스펙:** `docs/superpowers/specs/2026-08-05-youtube-tutorial-analyzer-design.md` (모든 § 참조는 이 문서)

## Global Constraints

- Windows 우선: 모든 파이썬 실행은 `python` (`python3` 금지 — MS Store 스텁). 경로는 `pathlib.Path`만 사용
- 프레임 파일명에 `:` 금지 (Windows) — 타임스탬프는 `t0312_512.jpg` 형식 (3분12초, 512px)
- 런타임 의존성은 stdlib만. 예외: `faster-whisper`(로컬 ASR 폴백, 지연 임포트, 미설치 허용), 개발 시 `pytest`
- 캐시: `~/.yta/cache/{video_id}/`, 설정: `~/.config/yta/.env` (KEY=VALUE, `#` 주석, 인라인 주석 금지)
- fail-loud: 모든 스크립트 stdout 보고서는 상태 헤더로 시작 (§9). 0건·빈 결과도 명시 보고
- 다운로드 720p 고정: `-f "bv*[height<=720]+ba/b[height<=720]"` (§3.3)
- dedup 임계값 2.0 (16×16 그레이스케일 평균절대차, watch 실측 패턴)
- 지도 프레임 수: `n = min(40, max(12, round(dur_min * 1.2)))` (30분 → 36)
- 확대 캡: 구간당 20장, 글로벌 60장. 2fps 상한
- 커밋 메시지 끝: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`

## 파일 구조 (최종)

```
YoutubeAnalayzer/
├── .claude-plugin/plugin.json        # T10 — 플러그인 매니페스트
├── skills/tuto/
│   ├── SKILL.md                      # T10 — 오케스트레이션 계약서
│   └── scripts/
│       ├── common.py                 # T1 — 설정·캐시 경로·시간 파싱·subprocess 헬퍼
│       ├── setup.py                  # T2 — 프리플라이트
│       ├── signals.py                # T3+T4 — 4신호 수집 (+설명란 타임스탬프)
│       ├── transcribe.py             # T5+T6 — 자막 사슬
│       ├── frames.py                 # T7 — 추출+dedup
│       ├── analyze.py                # T8 — 패스1 오케스트레이션+예산 배분기+cleanup
│       └── zoom.py                   # T9 — 패스2+재확대+예산 가드
├── tests/
│   ├── conftest.py                   # T1 — 합성 클립 픽스처
│   ├── test_common.py                # T1
│   ├── test_signals.py               # T3+T4
│   ├── test_transcribe.py            # T5+T6
│   ├── test_frames.py                # T7
│   ├── test_analyze.py               # T8
│   └── test_zoom.py                  # T9
└── README.md                         # T10
```

설계 원칙: 스크립트 간 직접 import는 `common.py`만 허용. 나머지는 캐시 파일로 통신 (§3.1).

**v1 범위 결정 (스펙 §8.2 구체화):** 외부 GT diff는 설명란 타임스탬프(info.json의 `description`, 항상 취득 가능)와 챕터만. 고정 댓글은 `--write-comments`가 무거워 향후 확장으로 미룸.

---

### Task 1: 플러그인 뼈대 + common.py

**Files:**
- Create: `skills/tuto/scripts/common.py`
- Create: `tests/conftest.py`, `tests/test_common.py`

**Interfaces:**
- Produces (이후 모든 태스크가 사용):
  - `CACHE_ROOT: Path` = `Path.home()/".yta"/"cache"`, `CONFIG_FILE: Path` = `Path.home()/".config"/"yta"/".env"`
  - `load_config() -> dict[str, str]` — .env 파싱, 파일 없으면 `{}`
  - `cache_dir(video_id: str) -> Path` — 생성 포함
  - `parse_ts(s: str) -> float` — `"75"`/`"1:15"`/`"1:01:15"` → 초
  - `fmt_ts(sec: float) -> str` — `75.0` → `"01:15"`, 1시간+ → `"1:01:15"`
  - `ts_tag(sec: float) -> str` — `192.0` → `"t0312"` (파일명용, 콜론 없음)
  - `video_id_from_url(url: str) -> str` — watch?v= / youtu.be/ / shorts/ / 11자 ID 직접
  - `run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess` — text=True, 실패 시 stderr 포함 RuntimeError

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_common.py`

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import common


def test_parse_ts():
    assert common.parse_ts("75") == 75.0
    assert common.parse_ts("1:15") == 75.0
    assert common.parse_ts("1:01:15") == 3675.0


def test_fmt_ts():
    assert common.fmt_ts(75) == "01:15"
    assert common.fmt_ts(3675) == "1:01:15"


def test_ts_tag_windows_safe():
    assert common.ts_tag(192) == "t0312"
    assert ":" not in common.ts_tag(3675)


def test_video_id_from_url():
    vid = "dQw4w9WgXcQ"
    assert common.video_id_from_url(f"https://www.youtube.com/watch?v={vid}") == vid
    assert common.video_id_from_url(f"https://youtu.be/{vid}?t=30") == vid
    assert common.video_id_from_url(f"https://www.youtube.com/shorts/{vid}") == vid
    assert common.video_id_from_url(vid) == vid


def test_load_config_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "CONFIG_FILE", tmp_path / "none.env")
    assert common.load_config() == {}


def test_load_config_parses_kv(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# comment\nGROQ_API_KEY=abc\nCACHE_MAX_VIDEOS=10\n", encoding="utf-8")
    monkeypatch.setattr(common, "CONFIG_FILE", f)
    cfg = common.load_config()
    assert cfg["GROQ_API_KEY"] == "abc"
    assert cfg["CACHE_MAX_VIDEOS"] == "10"
```

`tests/conftest.py` — 합성 클립 픽스처 (T4·T7·T9가 사용, 지금 만들어 둔다):

```python
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))

FFMPEG = shutil.which("ffmpeg")


@pytest.fixture(scope="session")
def synth_clip(tmp_path_factory):
    """11초 합성 클립: 0-5s 정지(파랑) → 5-6s 변화(노이즈) → 6-11s 정지(빨강)."""
    if not FFMPEG:
        pytest.skip("ffmpeg not on PATH")
    out = tmp_path_factory.mktemp("clip") / "synth.mp4"
    filt = (
        "color=blue:s=320x240:d=5[a];"
        "testsrc2=s=320x240:d=1[b];"
        "color=red:s=320x240:d=5[c];"
        "[a][b][c]concat=n=3:v=1:a=0"
    )
    subprocess.run(
        [FFMPEG, "-y", "-filter_complex", filt, "-r", "10", str(out)],
        check=True, capture_output=True,
    )
    return out
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_common.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'common'`

- [ ] **Step 3: 최소 구현** — `skills/tuto/scripts/common.py`

```python
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
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
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
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_common.py -v`
Expected: 6 PASS

- [ ] **Step 5: 커밋**

```bash
git add skills/tuto/scripts/common.py tests/conftest.py tests/test_common.py
git commit -m "feat: common 유틸 — 설정·캐시·시간 파싱·subprocess 헬퍼"
```

---

### Task 2: setup.py 프리플라이트

**Files:**
- Create: `skills/tuto/scripts/setup.py`
- Test: `tests/test_setup.py`

**Interfaces:**
- Consumes: `common.load_config`, `common.CONFIG_FILE`
- Produces:
  - CLI `python setup.py --check` — 종료코드 0(진행 가능)/2(바이너리 부재). stdout 무음(성공 시)
  - CLI `python setup.py --json` — `{"status": "ready|needs_install", "missing": [...], "ytdlp_version": "...", "ytdlp_stale": bool, "has_groq_key": bool, "has_faster_whisper": bool, "config_file": "..."}`
  - `check_env() -> dict` — 위 JSON과 동일 구조 (테스트 대상)
  - 부수효과: CONFIG_FILE 없으면 주석 템플릿 스캐폴드 (`GROQ_API_KEY=`, `CACHE_MAX_VIDEOS=10`)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_setup.py`

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import setup as yta_setup


def test_check_env_reports_structure(monkeypatch, tmp_path):
    monkeypatch.setattr(yta_setup.common, "CONFIG_FILE", tmp_path / ".env")
    r = yta_setup.check_env()
    assert set(r) >= {"status", "missing", "ytdlp_stale", "has_groq_key", "has_faster_whisper"}
    assert r["status"] in ("ready", "needs_install")


def test_missing_binary_detected(monkeypatch, tmp_path):
    monkeypatch.setattr(yta_setup.common, "CONFIG_FILE", tmp_path / ".env")
    monkeypatch.setattr(yta_setup.shutil, "which", lambda name: None)
    r = yta_setup.check_env()
    assert r["status"] == "needs_install"
    assert "ffmpeg" in r["missing"] and "yt-dlp" in r["missing"]


def test_scaffold_creates_env(monkeypatch, tmp_path):
    env = tmp_path / "cfg" / ".env"
    monkeypatch.setattr(yta_setup.common, "CONFIG_FILE", env)
    yta_setup.scaffold_config()
    text = env.read_text(encoding="utf-8")
    assert "GROQ_API_KEY=" in text and "CACHE_MAX_VIDEOS=10" in text
    yta_setup.scaffold_config()  # 멱등 — 기존 파일 덮어쓰지 않음
    assert env.read_text(encoding="utf-8") == text
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_setup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'setup'` 또는 AttributeError

- [ ] **Step 3: 최소 구현** — `skills/tuto/scripts/setup.py`

```python
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
        "has_groq_key": bool(cfg.get("GROQ_API_KEY")),
        "has_faster_whisper": importlib.util.find_spec("faster_whisper") is not None,
        "config_file": str(common.CONFIG_FILE),
    }


def main() -> int:
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
            return 0
        print("MISSING: " + ", ".join(r["missing"]), file=sys.stderr)
        print("install: winget install Gyan.FFmpeg ; pip install -U yt-dlp", file=sys.stderr)
        return 2
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_setup.py -v`
Expected: 3 PASS

- [ ] **Step 5: 커밋**

```bash
git add skills/tuto/scripts/setup.py tests/test_setup.py
git commit -m "feat: setup 프리플라이트 — 바이너리·yt-dlp 버전·키 확인, .env 스캐폴드"
```

---

### Task 3: signals.py — 메타데이터 신호 (히트맵·챕터·SponsorBlock·설명란 타임스탬프)

**Files:**
- Create: `skills/tuto/scripts/signals.py`
- Test: `tests/test_signals.py`, `tests/fixtures/info_sample.json`

**Interfaces:**
- Consumes: `common.run`, `common.parse_ts`
- Produces:
  - `parse_heatmap(info: dict) -> list[dict]` — `[{"start": float, "end": float, "value": float}]` (yt-dlp info.json의 `heatmap` 필드, 없으면 `[]`)
  - `parse_chapters(info: dict) -> list[dict]` — `[{"start": float, "end": float, "title": str}]`
  - `parse_description_timestamps(info: dict) -> list[dict]` — `[{"t": float, "label": str}]` (설명란 `MM:SS 제목` 줄, §8.2 외부 GT)
  - `fetch_sponsorblock(video_id: str) -> list[dict]` — `[{"start": float, "end": float, "category": str}]`; 404→`[]`, 네트워크 오류→`[]` + `"sponsorblock_error"` 플래그는 build_signals에서 기록
  - `build_signals(info: dict, video_id: str, video_path, curve: list[float] | None) -> dict` — signals.json 전체 구조:
    `{"heatmap": [...], "chapters": [...], "desc_timestamps": [...], "sponsorblock": [...], "activity": {"curve": [...], "peaks": [...]}, "flags": [...]}`
  - CLI `python signals.py <cache_dir>` — cache_dir의 `info.json`·`video.mp4` 읽어 `signals.json` 기록, 요약 1줄 stdout (활동 곡선은 T4에서 합류)

- [ ] **Step 1: 픽스처 작성** — `tests/fixtures/info_sample.json`

```json
{
  "id": "abc12345678",
  "duration": 300,
  "chapters": [
    {"start_time": 0, "end_time": 60, "title": "인트로"},
    {"start_time": 60, "end_time": 200, "title": "설치"},
    {"start_time": 200, "end_time": 300, "title": "실행"}
  ],
  "heatmap": [
    {"start_time": 0.0, "end_time": 3.0, "value": 1.0},
    {"start_time": 3.0, "end_time": 6.0, "value": 0.4},
    {"start_time": 6.0, "end_time": 9.0, "value": 0.1}
  ],
  "description": "튜토리얼입니다\n00:00 시작\n01:00 설치 방법\n03:20 실행하기\n감사합니다"
}
```

- [ ] **Step 2: 실패하는 테스트 작성** — `tests/test_signals.py`

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import signals

INFO = json.loads((Path(__file__).parent / "fixtures" / "info_sample.json").read_text(encoding="utf-8"))


def test_parse_heatmap():
    hm = signals.parse_heatmap(INFO)
    assert hm[0] == {"start": 0.0, "end": 3.0, "value": 1.0}
    assert signals.parse_heatmap({}) == []


def test_parse_chapters():
    ch = signals.parse_chapters(INFO)
    assert len(ch) == 3 and ch[1]["title"] == "설치" and ch[1]["start"] == 60.0


def test_parse_description_timestamps():
    ts = signals.parse_description_timestamps(INFO)
    assert {"t": 200.0, "label": "실행하기"} in ts
    assert len(ts) == 3


def test_fetch_sponsorblock_404(monkeypatch):
    def fake_get(url, timeout):
        raise signals.urllib.error.HTTPError(url, 404, "nf", {}, None)
    monkeypatch.setattr(signals, "_http_get", fake_get)
    assert signals.fetch_sponsorblock("abc12345678") == []


def test_fetch_sponsorblock_parses(monkeypatch):
    payload = json.dumps([{"segment": [10.0, 42.5], "category": "sponsor"}])
    monkeypatch.setattr(signals, "_http_get", lambda url, timeout: payload)
    segs = signals.fetch_sponsorblock("abc12345678")
    assert segs == [{"start": 10.0, "end": 42.5, "category": "sponsor"}]
```

- [ ] **Step 3: 실패 확인**

Run: `python -m pytest tests/test_signals.py -v`
Expected: FAIL — No module named 'signals' (주의: stdlib `signal`과 다름 — 단수/복수 구분)

- [ ] **Step 4: 최소 구현** — `skills/tuto/scripts/signals.py`

```python
"""4신호 수집: 히트맵·챕터·SponsorBlock·설명란 타임스탬프 (+활동 곡선은 T4). §6."""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import common

SB_API = "https://sponsor.ajay.app/api/skipSegments"
SB_CATS = '["sponsor","selfpromo","intro","outro","filler"]'
_DESC_TS = re.compile(r"^\s*\(?(\d{1,2}:\d{2}(?::\d{2})?)\)?\s*[-–—:]?\s*(.+)$")


def _http_get(url: str, timeout: int = 15) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")


def parse_heatmap(info: dict) -> list:
    return [
        {"start": float(h["start_time"]), "end": float(h["end_time"]), "value": float(h["value"])}
        for h in (info.get("heatmap") or [])
    ]


def parse_chapters(info: dict) -> list:
    return [
        {"start": float(c["start_time"]), "end": float(c["end_time"]), "title": c.get("title", "")}
        for c in (info.get("chapters") or [])
    ]


def parse_description_timestamps(info: dict) -> list:
    out = []
    for line in (info.get("description") or "").splitlines():
        m = _DESC_TS.match(line)
        if m and m.group(2).strip():
            out.append({"t": common.parse_ts(m.group(1)), "label": m.group(2).strip()})
    return out


def fetch_sponsorblock(video_id: str) -> list:
    url = f"{SB_API}?videoID={video_id}&categories={urllib.request.quote(SB_CATS)}"
    try:
        data = json.loads(_http_get(url, timeout=15))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    return [
        {"start": float(s["segment"][0]), "end": float(s["segment"][1]), "category": s["category"]}
        for s in data
    ]


def build_signals(info: dict, video_id: str, video_path, curve=None) -> dict:
    flags = []
    try:
        sb = fetch_sponsorblock(video_id)
    except Exception as e:
        sb, flags = [], [f"sponsorblock_error: {e}"]
    sig = {
        "heatmap": parse_heatmap(info),
        "chapters": parse_chapters(info),
        "desc_timestamps": parse_description_timestamps(info),
        "sponsorblock": sb,
        "activity": {"curve": curve or [], "peaks": []},
        "flags": flags,
    }
    if not sig["heatmap"]:
        sig["flags"].append("heatmap_absent")
    if not sig["chapters"]:
        sig["flags"].append("chapters_absent")
    return sig


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cache_dir")
    args = ap.parse_args()
    cd = Path(args.cache_dir)
    info = json.loads((cd / "info.json").read_text(encoding="utf-8"))
    sig = build_signals(info, info["id"], cd / "video.mp4")
    (cd / "signals.json").write_text(json.dumps(sig, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"signals: heatmap={len(sig['heatmap'])} chapters={len(sig['chapters'])} "
        f"desc_ts={len(sig['desc_timestamps'])} sponsorblock={len(sig['sponsorblock'])} "
        f"flags={sig['flags'] or 'none'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest tests/test_signals.py -v`
Expected: 5 PASS

- [ ] **Step 6: 커밋**

```bash
git add skills/tuto/scripts/signals.py tests/test_signals.py tests/fixtures/info_sample.json
git commit -m "feat: signals — 히트맵·챕터·SponsorBlock·설명란 타임스탬프 수집"
```

---

### Task 4: signals.py — 활동 곡선 (P1·P2의 핵심)

**Files:**
- Modify: `skills/tuto/scripts/signals.py` (함수 추가)
- Test: `tests/test_signals.py` (추가)

**Interfaces:**
- Consumes: `common.run`, T1 `synth_clip` 픽스처
- Produces:
  - `activity_curve(video_path: Path) -> list[float]` — 인덱스 = 초, 값 = 직전 초 대비 16×16 그레이스케일 평균절대차 (0–255). ffmpeg 1회 호출
  - `find_peaks(curve: list[float], min_gap: int = 10) -> list[int]` — 임계값(평균+1σ) 이상 로컬 맥시마, min_gap 초 간격 보장, 값 내림차순 아닌 시간순 반환
  - `build_signals(...)`의 `activity` 채움: `{"curve": [...], "peaks": [...]}`

- [ ] **Step 1: 실패하는 테스트 추가** — `tests/test_signals.py`에 append

```python
def test_activity_curve_finds_change(synth_clip):
    curve = signals.activity_curve(synth_clip)
    assert len(curve) >= 9  # 11초 클립 → ~10개 차분
    peak_t = max(range(len(curve)), key=lambda i: curve[i])
    assert 4 <= peak_t <= 7  # 변화 구간(5-6s) 부근
    flat = curve[1:4]  # 정지(파랑) 구간
    assert max(flat) < max(curve) * 0.3  # 정지 구간은 피크 대비 확연히 낮음


def test_find_peaks_min_gap():
    curve = [0.0] * 60
    curve[10] = 50.0
    curve[12] = 40.0  # 10과 2초 간격 — min_gap=10에 걸려 제외
    curve[40] = 45.0
    peaks = signals.find_peaks(curve, min_gap=10)
    assert 10 in peaks and 40 in peaks and 12 not in peaks
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_signals.py -v -k activity`
Expected: FAIL — AttributeError: no attribute 'activity_curve'

- [ ] **Step 3: 구현** — `signals.py`에 추가, `main()`에서 video.mp4 존재 시 곡선 계산하도록 `build_signals` 호출부 수정

```python
FRAME_BYTES = 256  # 16x16 gray


def activity_curve(video_path) -> list:
    import subprocess
    p = subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-vf", "fps=1,scale=16:16,format=gray",
         "-f", "rawvideo", "-v", "error", "-"],
        capture_output=True, timeout=600,
    )
    if p.returncode != 0:
        raise RuntimeError(f"activity_curve ffmpeg failed: {p.stderr[-500:]}")
    raw = p.stdout
    frames = [raw[i:i + FRAME_BYTES] for i in range(0, len(raw) - FRAME_BYTES + 1, FRAME_BYTES)]
    curve = [0.0]
    for prev, cur in zip(frames, frames[1:]):
        curve.append(sum(abs(a - b) for a, b in zip(prev, cur)) / FRAME_BYTES)
    return curve


def find_peaks(curve: list, min_gap: int = 10) -> list:
    if not curve:
        return []
    mean = sum(curve) / len(curve)
    var = sum((v - mean) ** 2 for v in curve) / len(curve)
    thresh = mean + var ** 0.5
    cands = sorted(
        (i for i in range(1, len(curve) - 1)
         if curve[i] >= thresh and curve[i] >= curve[i - 1] and curve[i] >= curve[i + 1]),
        key=lambda i: -curve[i],
    )
    kept = []
    for i in cands:
        if all(abs(i - k) >= min_gap for k in kept):
            kept.append(i)
    return sorted(kept)
```

`build_signals` 수정 — 시그니처 유지, 내부에서:

```python
    if curve is None and video_path and Path(video_path).exists():
        curve = activity_curve(video_path)
    curve = curve or []
    sig["activity"] = {"curve": [round(v, 2) for v in curve], "peaks": find_peaks(curve)}
    if not curve:
        sig["flags"].append("activity_absent")
```

`main()`의 stdout 요약에 `activity={len(curve)}pts/{len(peaks)}peaks` 추가.

- [ ] **Step 4: 전체 통과 확인**

Run: `python -m pytest tests/test_signals.py -v`
Expected: 7 PASS (ffmpeg 없으면 activity 1건 skip)

- [ ] **Step 5: 커밋**

```bash
git add skills/tuto/scripts/signals.py tests/test_signals.py
git commit -m "feat: 활동 곡선 — 1fps 16x16 차분 + 피크 감지 (P1/P2 방어)"
```

---

### Task 5: transcribe.py — VTT 파싱 + 롤링 중복 제거

**Files:**
- Create: `skills/tuto/scripts/transcribe.py`
- Test: `tests/test_transcribe.py`

**Interfaces:**
- Consumes: `common.fmt_ts`
- Produces:
  - `parse_vtt(text: str) -> list[dict]` — `[{"start": float, "end": float, "text": str}]`, 인라인 태그(`<00:..>`, `<c>`) 제거
  - `dedup_cues(cues: list[dict]) -> tuple[list[dict], int]` — 자동자막 롤링 중복 제거, (정제된 큐, 제거 수)
  - transcript.json 스키마 (T6에서 완성): `{"source": "captions|groq|local|none", "lang": str, "segments": [{"start","end","text"}], "flags": [str], "dupes_removed": int}`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_transcribe.py`

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import transcribe

AUTO_VTT = """WEBVTT
Kind: captions
Language: ko

00:00:00.000 --> 00:00:02.500
안녕하세요<00:00:01.000><c> 여러분</c>

00:00:02.500 --> 00:00:05.000
안녕하세요 여러분
오늘은 힉스필드를

00:00:05.000 --> 00:00:07.500
오늘은 힉스필드를
써보겠습니다
"""


def test_parse_vtt_strips_inline_tags():
    cues = transcribe.parse_vtt(AUTO_VTT)
    assert cues[0]["start"] == 0.0 and cues[0]["end"] == 2.5
    assert "<" not in cues[0]["text"]
    assert cues[0]["text"] == "안녕하세요 여러분"


def test_dedup_removes_rolling_lines():
    cues = transcribe.parse_vtt(AUTO_VTT)
    clean, removed = transcribe.dedup_cues(cues)
    joined = " ".join(c["text"] for c in clean)
    assert joined.count("안녕하세요") == 1
    assert joined.count("힉스필드를") == 1
    assert removed >= 2
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_transcribe.py -v`
Expected: FAIL — No module named 'transcribe'

- [ ] **Step 3: 최소 구현** — `skills/tuto/scripts/transcribe.py`

```python
"""자막 사슬: VTT 파싱·롤링 중복 제거 (+Groq/로컬 whisper는 T6). §5 P5/P6."""
import re
import sys
from pathlib import Path

import common

_TS_LINE = re.compile(
    r"(\d{2}:\d{2}:\d{2})\.(\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2})\.(\d{3})"
)
_INLINE = re.compile(r"<[^>]+>")


def parse_vtt(text: str) -> list:
    cues, cur = [], None
    for line in text.splitlines():
        m = _TS_LINE.search(line)
        if m:
            if cur and cur["text"]:
                cues.append(cur)
            start = common.parse_ts(m.group(1)) + int(m.group(2)) / 1000
            end = common.parse_ts(m.group(3)) + int(m.group(4)) / 1000
            cur = {"start": start, "end": end, "text": ""}
        elif cur is not None:
            clean = _INLINE.sub("", line).strip()
            if clean and not clean.startswith(("WEBVTT", "Kind:", "Language:")):
                cur["text"] = (cur["text"] + "\n" + clean).strip() if cur["text"] else clean
    if cur and cur["text"]:
        cues.append(cur)
    return cues


def dedup_cues(cues: list) -> tuple:
    """자동자막 롤링 중복: 각 큐의 앞줄 = 직전 큐의 마지막 줄 반복 → 제거."""
    removed = 0
    prev_last = None
    out = []
    for c in cues:
        lines = c["text"].split("\n")
        if prev_last is not None and lines and lines[0] == prev_last:
            lines = lines[1:]
            removed += 1
        prev_last = lines[-1] if lines else prev_last
        text = " ".join(lines).strip()
        if text:
            out.append({"start": c["start"], "end": c["end"], "text": text})
    return out, removed
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_transcribe.py -v`
Expected: 2 PASS

- [ ] **Step 5: 커밋**

```bash
git add skills/tuto/scripts/transcribe.py tests/test_transcribe.py
git commit -m "feat: VTT 파싱 + 자동자막 롤링 중복 제거 (P6)"
```

---

### Task 6: transcribe.py — Whisper 사슬 (Groq→로컬) + 환각 방어

**Files:**
- Modify: `skills/tuto/scripts/transcribe.py`
- Test: `tests/test_transcribe.py` (추가)

**Interfaces:**
- Consumes: `common.load_config`, `common.run`
- Produces:
  - `collapse_repeats(segs: list[dict], n: int = 3) -> tuple[list[dict], int]` — 동일 텍스트 n회+ 연속 → 1개로 붕괴 (P5 반복 루프)
  - `detect_silences(audio_path) -> list[tuple[float, float]]` — ffmpeg silencedetect (noise=-35dB, d=2)
  - `drop_silence_overlap(segs, silences) -> tuple[list[dict], int]` — 세그먼트 중심이 무음 구간 안이면 드롭 (P5 무음 환각; 오디오 절단 대신 후처리 드롭 — 타임스탬프 매핑 불필요)
  - `groq_transcribe(audio_path, api_key: str) -> list[dict]` — verbose_json, `no_speech_prob > 0.6` 세그먼트 드롭, 25MB 초과 시 ffmpeg 시간 분할 후 이어붙임
  - `local_transcribe(audio_path) -> list[dict]` — faster-whisper large-v3, `vad_filter=True`, ImportError 시 `None` 반환
  - `get_transcript(cache_dir: Path, mode: str) -> dict` — 사슬 오케스트레이션: cache의 `subs.vtt` → groq → local → none. transcript.json 기록 후 반환
  - CLI `python transcribe.py <cache_dir> [--whisper groq|local] [--no-whisper]`

- [ ] **Step 1: 실패하는 테스트 추가**

```python
def test_collapse_repeats():
    segs = [{"start": float(i), "end": i + 1.0, "text": "감사합니다"} for i in range(5)]
    segs.append({"start": 5.0, "end": 6.0, "text": "다음 단계로"})
    out, n = transcribe.collapse_repeats(segs, n=3)
    texts = [s["text"] for s in out]
    assert texts.count("감사합니다") == 1 and n == 4
    assert "다음 단계로" in texts


def test_drop_silence_overlap():
    segs = [
        {"start": 1.0, "end": 3.0, "text": "진짜 말"},
        {"start": 10.0, "end": 12.0, "text": "시청해주셔서 감사합니다"},  # 무음 구간 안 = 환각
    ]
    out, n = transcribe.drop_silence_overlap(segs, [(8.0, 20.0)])
    assert len(out) == 1 and out[0]["text"] == "진짜 말" and n == 1


def test_groq_drops_no_speech(monkeypatch):
    fake = {"segments": [
        {"start": 0.0, "end": 2.0, "text": " 안녕하세요", "no_speech_prob": 0.1},
        {"start": 2.0, "end": 4.0, "text": " 구독과 좋아요", "no_speech_prob": 0.95},
    ]}
    monkeypatch.setattr(transcribe, "_groq_request", lambda path, key: fake)
    monkeypatch.setattr(transcribe.Path, "stat", lambda self: type("S", (), {"st_size": 1000})())
    segs = transcribe.groq_transcribe(Path("fake.mp3"), "key")
    assert len(segs) == 1 and segs[0]["text"] == "안녕하세요"


def test_chain_none_when_all_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(transcribe.common, "load_config", lambda: {})
    monkeypatch.setattr(transcribe, "local_transcribe", lambda p: None)
    r = transcribe.get_transcript(tmp_path, mode="auto")
    assert r["source"] == "none" and r["segments"] == []
    assert any("no transcript" in f for f in r["flags"])
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_transcribe.py -v`
Expected: 신규 4건 FAIL (AttributeError)

- [ ] **Step 3: 구현** — `transcribe.py`에 추가

```python
import argparse
import json
import mimetypes
import urllib.request
import uuid

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_LIMIT = 24 * 1024 * 1024  # 25MB 제한에 여유
NO_SPEECH_MAX = 0.6
_SIL = re.compile(r"silence_(start|end): ([\d.]+)")


def collapse_repeats(segs: list, n: int = 3) -> tuple:
    out, removed, i = [], 0, 0
    while i < len(segs):
        j = i
        while j < len(segs) and segs[j]["text"].strip() == segs[i]["text"].strip():
            j += 1
        run_len = j - i
        if run_len >= n:
            merged = dict(segs[i])
            merged["end"] = segs[j - 1]["end"]
            out.append(merged)
            removed += run_len - 1
        else:
            out.extend(segs[i:j])
        i = j
    return out, removed


def detect_silences(audio_path) -> list:
    import subprocess
    p = subprocess.run(
        ["ffmpeg", "-i", str(audio_path), "-af", "silencedetect=noise=-35dB:d=2",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    events, start = [], None
    for kind, val in _SIL.findall(p.stderr):
        if kind == "start":
            start = float(val)
        elif start is not None:
            events.append((start, float(val)))
            start = None
    return events


def drop_silence_overlap(segs: list, silences: list) -> tuple:
    def in_silence(s):
        mid = (s["start"] + s["end"]) / 2
        return any(a <= mid <= b for a, b in silences)
    kept = [s for s in segs if not in_silence(s)]
    return kept, len(segs) - len(kept)


def _groq_request(audio_path, api_key: str) -> dict:
    boundary = uuid.uuid4().hex
    data = audio_path.read_bytes()
    parts = []
    for name, val in (("model", "whisper-large-v3"), ("response_format", "verbose_json")):
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n".encode()
        )
    ctype = mimetypes.guess_type(str(audio_path))[0] or "audio/mpeg"
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{audio_path.name}\"\r\nContent-Type: {ctype}\r\n\r\n".encode()
        + data + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        GROQ_URL, data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def _split_audio(audio_path, chunk_sec: int = 1200) -> list:
    """25MB 초과 시 시간 분할. 64kbps mono mp3 기준 20분 ≈ 9.6MB."""
    out_tpl = audio_path.parent / "chunk_%03d.mp3"
    common.run(["ffmpeg", "-y", "-i", audio_path, "-f", "segment",
                "-segment_time", chunk_sec, "-c", "copy", out_tpl])
    return sorted(audio_path.parent.glob("chunk_*.mp3"))


def groq_transcribe(audio_path, api_key: str) -> list:
    chunks = [audio_path] if audio_path.stat().st_size <= GROQ_LIMIT else _split_audio(audio_path)
    segs, offset = [], 0.0
    chunk_sec = 1200.0
    for i, chunk in enumerate(chunks):
        resp = _groq_request(chunk, api_key)
        for s in resp.get("segments", []):
            if s.get("no_speech_prob", 0.0) > NO_SPEECH_MAX:
                continue
            segs.append({
                "start": float(s["start"]) + offset,
                "end": float(s["end"]) + offset,
                "text": s["text"].strip(),
            })
        offset = (i + 1) * chunk_sec
    return segs


def local_transcribe(audio_path):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    model = WhisperModel("large-v3", device="auto", compute_type="int8")
    raw, _info = model.transcribe(str(audio_path), vad_filter=True)
    return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in raw]


def _extract_audio(cache_dir: Path) -> Path:
    audio = cache_dir / "audio.mp3"
    if not audio.exists():
        common.run(["ffmpeg", "-y", "-i", cache_dir / "video.mp4",
                    "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", audio])
    return audio


def get_transcript(cache_dir: Path, mode: str = "auto") -> dict:
    result = {"source": "none", "lang": "", "segments": [], "flags": [], "dupes_removed": 0}
    vtts = sorted(cache_dir.glob("subs*.vtt"))
    if vtts and mode != "no-captions-test":
        lang = "ko" if ".ko" in vtts[0].name else ("en" if ".en" in vtts[0].name else "?")
        cues = parse_vtt(vtts[0].read_text(encoding="utf-8", errors="replace"))
        segs, removed = dedup_cues(cues)
        result.update(source="captions", lang=lang, segments=segs, dupes_removed=removed)
    elif mode != "no-whisper":
        video = cache_dir / "video.mp4"
        if video.exists():
            audio = _extract_audio(cache_dir)
            cfg = common.load_config()
            segs = None
            if mode in ("auto", "groq") and cfg.get("GROQ_API_KEY"):
                try:
                    segs = groq_transcribe(audio, cfg["GROQ_API_KEY"])
                    result["source"] = "groq"
                except Exception as e:
                    result["flags"].append(f"groq_failed: {str(e)[:200]}")
            if segs is None and mode in ("auto", "local"):
                segs = local_transcribe(audio)
                if segs is not None:
                    result["source"] = "local"
            if segs:
                silences = detect_silences(audio)
                segs, sil_n = drop_silence_overlap(segs, silences)
                segs, rep_n = collapse_repeats(segs)
                if sil_n:
                    result["flags"].append(f"silence_dropped: {sil_n}")
                if rep_n:
                    result["flags"].append(f"repeats_collapsed: {rep_n}")
                result["segments"] = segs
    if not result["segments"]:
        result["source"] = "none"
        result["flags"].append("no transcript available — frames-only mode")
    (cache_dir / "transcript.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cache_dir")
    ap.add_argument("--whisper", choices=["groq", "local"], default=None)
    ap.add_argument("--no-whisper", action="store_true")
    args = ap.parse_args()
    mode = "no-whisper" if args.no_whisper else (args.whisper or "auto")
    r = get_transcript(Path(args.cache_dir), mode)
    print(f"transcript: source={r['source']} lang={r['lang']} segments={len(r['segments'])} "
          f"dupes_removed={r['dupes_removed']} flags={r['flags'] or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 전체 통과 확인**

Run: `python -m pytest tests/test_transcribe.py -v`
Expected: 6 PASS

- [ ] **Step 5: 커밋**

```bash
git add skills/tuto/scripts/transcribe.py tests/test_transcribe.py
git commit -m "feat: Whisper 사슬(Groq→로컬) + 무음·반복 환각 방어 (P5)"
```

---

### Task 7: frames.py — 타임스탬프 추출 + dedup

**Files:**
- Create: `skills/tuto/scripts/frames.py`
- Test: `tests/test_frames.py`

**Interfaces:**
- Consumes: `common.run`, `common.ts_tag`, `synth_clip` 픽스처
- Produces:
  - `extract_frames(video: Path, timestamps: list[float], res: int, out_dir: Path) -> list[Path]` — 시점당 1장, `-ss T -i video -frames:v 1 -vf scale=RES:-2 -q:v 3`, 파일명 `{ts_tag}_{res}.jpg` (예: `t0312_1024.jpg`), 기존 파일 재사용(멱등)
  - `dedup_frames(paths: list[Path], threshold: float = 2.0) -> tuple[list[Path], int]` — 16×16 gray 평균절대차 ≤ threshold → 뒤 프레임 드롭 (직전 *유지* 프레임과 비교)
  - stdout 계약 (analyze/zoom 공용): 한 줄에 `FRAME <path> t=<MM:SS>` — Claude가 이 줄들을 파싱해 Read

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_frames.py`

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import frames


def test_extract_frames_names_and_count(synth_clip, tmp_path):
    out = frames.extract_frames(synth_clip, [1.0, 8.0], 512, tmp_path)
    assert len(out) == 2
    assert out[0].name == "t0001_512.jpg" and out[0].exists()
    assert out[1].name == "t0008_512.jpg"


def test_dedup_drops_static(synth_clip, tmp_path):
    # 1s,2s,3s = 전부 파랑 정지 → 2장 드롭. 8s = 빨강 → 유지
    out = frames.extract_frames(synth_clip, [1.0, 2.0, 3.0, 8.0], 512, tmp_path)
    kept, dropped = frames.dedup_frames(out)
    assert dropped == 2
    assert [p.name for p in kept] == ["t0001_512.jpg", "t0008_512.jpg"]
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_frames.py -v`
Expected: FAIL — No module named 'frames'

- [ ] **Step 3: 최소 구현** — `skills/tuto/scripts/frames.py`

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_frames.py -v`
Expected: 2 PASS

- [ ] **Step 5: 커밋**

```bash
git add skills/tuto/scripts/frames.py tests/test_frames.py
git commit -m "feat: frames — 타임스탬프 추출 + 16x16 dedup, FRAME 출력 계약"
```

---

### Task 8: analyze.py — 패스 1 오케스트레이션 + 지도 예산 배분기 + cleanup

**Files:**
- Create: `skills/tuto/scripts/analyze.py`
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `signals.build_signals`·`find_peaks`, `transcribe.get_transcript`, `frames.extract_frames`·`dedup_frames`·`report`, `common.*`
- Produces:
  - `allocate_map_budget(duration: float, sig: dict) -> list[float]` — **지도 예산 배분기 (스펙 §4 소유)**:
    - `n = min(40, max(12, round(duration/60 * 1.2)))`
    - 후보와 가중치: 챕터 시작+2s(3.0) > 히트맵 상위 10구간 중심(2.5) > 활동 피크(2.0) > 균등 그리드(1.0)
    - SponsorBlock(전 카테고리) 구간 내 후보 제거
    - 그리디: 가중치 내림차순, 최소 간격 `max(8.0, duration/n/2)` 초
    - `t=1.0`과 `t=duration-2`는 항상 포함, 모자라면 그리드로 충원, 시간순 반환
  - `download(url: str, cache_dir: Path) -> dict` — yt-dlp 720p+info.json+자막(ko/en, auto 포함) 한 번에. info.json 반환. 이미 있으면 재사용
  - CLI `python analyze.py <url>` — 전체 패스 1 실행, stdout 보고서:
    ```
    === YTA PASS1: <video_id> ===
    STATUS duration=<MM:SS> transcript=<source>(<lang>) segments=<n> dupes_removed=<n> heatmap=<yes/no> chapters=<n> desc_ts=<n> sponsorblock=<n>segs activity=<n>pts/<n>peaks map_frames=<kept>(<dropped> dup-dropped) flags=<...>
    == TRANSCRIPT ==
    [MM:SS] 텍스트...
    == CHAPTERS ==  / == DESC_TIMESTAMPS ==  / == SPONSORBLOCK ==  (각 목록)
    == HEATMAP_TOP ==  (상위 10구간 중심 MM:SS와 값)
    == ACTIVITY_PEAKS ==  (MM:SS 목록)
    == FRAMES ==
    FRAME <path> t=<MM:SS>   (frames.report 형식)
    == CACHE ==  <cache_dir>
    ```
  - CLI `python analyze.py --cleanup` — 캐시 전체 목록·용량 출력 후 삭제
  - `lru_evict() -> list[str]` — `CACHE_MAX_VIDEOS`(기본 10) 초과분의 video.mp4·audio.mp3만 삭제(가이드·전사·signals 보존, §7), 매 실행 끝 자동 호출, 삭제 목록 반환

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_analyze.py` (배분기·LRU 중심 — 다운로드는 L3에서)

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import analyze

SIG = {
    "chapters": [{"start": 0, "end": 300, "title": "인트로"}, {"start": 300, "end": 900, "title": "본론"}],
    "heatmap": [{"start": 600, "end": 630, "value": 1.0}],
    "sponsorblock": [{"start": 100, "end": 160, "category": "sponsor"}],
    "activity": {"curve": [], "peaks": [450]},
}


def test_allocate_count_formula():
    ts = analyze.allocate_map_budget(1800.0, SIG)   # 30분
    assert len(ts) == 36


def test_allocate_includes_chapter_starts_and_ends():
    ts = analyze.allocate_map_budget(900.0, SIG)
    assert any(abs(t - 302.0) < 1 for t in ts)      # 챕터 시작+2s
    assert any(abs(t - 1.0) < 0.5 for t in ts)      # 시작
    assert any(abs(t - 898.0) < 1 for t in ts)      # 끝-2s


def test_allocate_excludes_sponsor_range():
    ts = analyze.allocate_map_budget(900.0, SIG)
    assert not any(100 <= t <= 160 for t in ts)


def test_allocate_min_gap():
    ts = sorted(analyze.allocate_map_budget(900.0, SIG))
    n = len(ts)
    min_gap = max(8.0, 900.0 / n / 2)
    assert all(b - a >= min_gap * 0.99 for a, b in zip(ts, ts[1:]))


def test_lru_evict_removes_oldest_video_only(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(analyze.common, "load_config", lambda: {"CACHE_MAX_VIDEOS": "2"})
    import os, time
    for i, vid in enumerate(["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"]):
        d = tmp_path / vid
        d.mkdir()
        (d / "video.mp4").write_bytes(b"x")
        (d / "guide.md").write_text("g", encoding="utf-8")
        t = time.time() - (10 - i) * 100
        os.utime(d, (t, t))
    evicted = analyze.lru_evict()
    assert evicted == ["aaaaaaaaaaa"]
    assert not (tmp_path / "aaaaaaaaaaa" / "video.mp4").exists()
    assert (tmp_path / "aaaaaaaaaaa" / "guide.md").exists()   # 가이드는 보존
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_analyze.py -v`
Expected: FAIL — No module named 'analyze'

- [ ] **Step 3: 구현** — `skills/tuto/scripts/analyze.py`

```python
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


def allocate_map_budget(duration: float, sig: dict) -> list:
    n = min(40, max(12, round(duration / 60 * 1.2)))
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
    for i in range(n):
        cands.append((W_GRID, duration * (i + 0.5) / n))
    cands = [(w, t) for w, t in cands if 0 <= t <= duration and not _in_ranges(t, sb)]

    picked = [1.0, max(2.0, duration - 2.0)]       # 시작·끝 고정
    for w, t in sorted(cands, key=lambda x: -x[0]):
        if len(picked) >= n:
            break
        if all(abs(t - p) >= min_gap for p in picked):
            picked.append(t)
    return sorted(picked)[:n]


def download(url: str, cd: Path) -> dict:
    info_f = cd / "info.json"
    if not info_f.exists():
        common.run([
            "yt-dlp", url,
            "-f", "bv*[height<=720]+ba/b[height<=720]", "--merge-output-format", "mp4",
            "-o", cd / "video.mp4",
            "--write-info-json", "-o", f"infojson:{cd / 'info'}",
            "--write-subs", "--write-auto-subs", "--sub-langs", "ko,en,ko-orig",
            "--sub-format", "vtt", "-o", f"subtitle:{cd / 'subs'}",
            "--no-playlist", "--no-progress",
        ], timeout=1800)
    return json.loads(info_f.read_text(encoding="utf-8", errors="replace"))


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

    ts = allocate_map_budget(duration, sig)
    raw = frames.extract_frames(cd / "video.mp4", ts, 512, cd / "frames")
    kept, dropped = frames.dedup_frames(raw)

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
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_analyze.py -v`
Expected: 5 PASS

- [ ] **Step 5: 전체 회귀**

Run: `python -m pytest tests/ -v`
Expected: 전부 PASS (ffmpeg 의존 테스트는 환경에 따라 skip 허용)

- [ ] **Step 6: 커밋**

```bash
git add skills/tuto/scripts/analyze.py tests/test_analyze.py
git commit -m "feat: analyze 패스1 — 신호 가중 지도 배분기·보고서·LRU (P1/P7/P9)"
```

---

### Task 9: zoom.py — 패스 2 확대 + 예산 가드

**Files:**
- Create: `skills/tuto/scripts/zoom.py`
- Test: `tests/test_zoom.py`

**Interfaces:**
- Consumes: `frames.extract_frames`·`dedup_frames`·`report`, `common.*`
- Produces:
  - `parse_ranges(spec: str) -> list[dict]` — `"3:10-3:50@1024,12:11-12:40"` → `[{"start": 190.0, "end": 230.0, "res": 1024}, {"start": 731.0, "end": 760.0, "res": 512}]` (기본 512)
  - `plan_timestamps(ranges: list[dict]) -> list[tuple[float, int]]` — **확대 예산 가드 (스펙 §4 소유)**: 구간당 2fps 상한·최대 20장, 글로벌 60장 초과 시 구간별 균등 감축(1024px 구간 우선 감축 아님 — 감축은 장수 기준, 해상도 선택은 Claude 몫), `(timestamp, res)` 목록
  - CLI `python zoom.py <video_id|cache_dir> --ranges "..."` — 캐시 video.mp4에서 추출, `FRAME` 계약으로 출력. `--timestamps "12:34@1024,..."` 단발 시점 모드(검증 패스·Q&A용)
  - video.mp4 부재 시(LRU 삭제) 명시 에러: `ERROR: video.mp4 evicted — re-run analyze.py <url> to re-download`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_zoom.py`

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import zoom


def test_parse_ranges():
    r = zoom.parse_ranges("3:10-3:50@1024,12:11-12:40")
    assert r[0] == {"start": 190.0, "end": 230.0, "res": 1024}
    assert r[1]["res"] == 512


def test_plan_caps_2fps_and_20_per_range():
    ts = zoom.plan_timestamps([{"start": 0.0, "end": 5.0, "res": 512}])
    assert len(ts) == 10                       # 5초 × 2fps
    ts = zoom.plan_timestamps([{"start": 0.0, "end": 60.0, "res": 512}])
    assert len(ts) == 20                       # 구간 캡


def test_plan_global_cap_60():
    ranges = [{"start": i * 100.0, "end": i * 100.0 + 60.0, "res": 512} for i in range(5)]
    ts = zoom.plan_timestamps(ranges)          # 5구간 × 20 = 100 → 60으로 감축
    assert len(ts) <= 60
    starts = {r["start"] for r in ranges}
    covered = {min(starts, key=lambda s: abs(s - t)) for t, _ in ts}
    assert covered == starts                   # 감축돼도 모든 구간 커버 (P3)


def test_single_timestamps_mode():
    ts = zoom.parse_single("12:34@1024,0:05")
    assert ts == [(754.0, 1024), (5.0, 512)]
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_zoom.py -v`
Expected: FAIL — No module named 'zoom'

- [ ] **Step 3: 최소 구현** — `skills/tuto/scripts/zoom.py`

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_zoom.py -v`
Expected: 4 PASS

- [ ] **Step 5: 커밋**

```bash
git add skills/tuto/scripts/zoom.py tests/test_zoom.py
git commit -m "feat: zoom 패스2 — 구간 파싱·2fps/20/60 예산 가드·커버리지 보존 (P3)"
```

---

### Task 10: SKILL.md + plugin.json + README — 오케스트레이션 계약

**Files:**
- Create: `.claude-plugin/plugin.json`, `skills/tuto/SKILL.md`, `README.md`

**Interfaces:**
- Consumes: T2~T9의 모든 CLI 계약 (setup/analyze/zoom 명령과 stdout 형식)
- Produces: Claude가 따르는 오케스트레이션 절차 전체. **아래 명시된 규약 항목은 표현만 다듬고 내용은 그대로 유지할 것**

- [ ] **Step 1: plugin.json 작성** — `.claude-plugin/plugin.json`

```json
{
  "name": "yta",
  "version": "0.1.0",
  "description": "유튜브 튜토리얼 영상 분석 — 신호 가중 2패스로 스텝 가이드·요약·Q&A 산출",
  "author": {"name": "hwangjs"}
}
```

- [ ] **Step 2: SKILL.md 작성** — 아래 골격과 규약 전부 포함 (frontmatter 포함)

````markdown
---
name: tuto
description: 유튜브 튜토리얼 영상(≤30분, 한/영)을 분석해 따라하기 스텝 가이드·요약·Q&A 상태를 만든다. URL을 받아 신호(히트맵·챕터·활동곡선) 가중 2패스로 화면 조작 순서와 설정값을 추출한다. "튜토리얼 분석", "따라하기 정리", "영상 스텝 뽑아줘" 요청 시 사용.
argument-hint: "<video-url> [질문]"
allowed-tools: Bash, Read, AskUserQuestion, Agent
user-invocable: true
---

# /tuto — 튜토리얼 영상 → 따라하기 가이드

SKILL_DIR 결정: 이 SKILL.md가 있는 디렉토리. 모든 명령은 `python "<SKILL_DIR>/scripts/….py"` (Windows: python, python3 금지).

## 0. 프리플라이트 (세션 첫 호출만)
`python scripts/setup.py --check` — 종료 0이면 무언 진행. 2면 stderr의 설치 명령을 사용자에게 안내.

## 1. 패스 1 — 지도
`python scripts/analyze.py "<url>"` 실행 → 보고서의 STATUS 줄을 먼저 확인:
- flags에 no transcript → 사용자에게 알리고 프레임 중심으로 진행 (가이드 상단에 한계 명시)
- 30분 초과 WARNING → 사용자에게 구간 지정 제안 후 진행 여부 확인
== FRAMES == 의 모든 FRAME 경로를 병렬 Read.

## 2. 확대 계획 판정 → zoom-plan.json
자막·챕터·히트맵·활동 피크·지도 프레임을 종합해 스텝 후보와 확대 구간을 판정한다.

**판정 루브릭 (전부 적용):**
1. 자막 지시어 큐가 있는 시점은 확대 후보다. 지시어 사전 —
   한국어: "여기(를) 보시면/보세요", "이렇게", "이 부분", "클릭", "누르면/누릅니다", "선택", "설정", "입력", "들어가서", "이 값", "요기"
   영어: "look here", "as you can see", "click", "select", "notice", "right here", "this setting", "type in", "go to", "hit"
2. 챕터 경계마다 스텝 후보 1개 이상.
3. == ACTIVITY_PEAKS == 중 어떤 확대 구간에도 덮이지 않는 피크는 반드시 구간 1개를 배정한다 (말 없는 조작 방어).
4. 커버리지 제약: 모든 스텝 후보에 최소 1개 확대 구간. 한 주제에 구간을 3개 이상 몰지 않는다.
5. 해상도: 설정값·코드·메뉴 텍스트를 읽어야 하는 구간만 @1024, 나머지 512.

판정 결과를 `<cache_dir>/zoom-plan.json`으로 저장 (Write):
```json
{"steps": [{"idx": 1, "title": "프로젝트 생성", "t_start": 65, "t_end": 190}],
 "zooms": [{"range": "1:05-1:35", "res": 1024, "reason": "설정 패널 값 입력"}]}
```

## 3. 패스 2 — 확대
`python scripts/zoom.py <video_id> --ranges "1:05-1:35@1024,4:10-4:40"` → FRAME 경로 전부 병렬 Read.

## 4. 가이드 초안 → 검증 패스
`<cache_dir>/guide.md` 작성. 형식:
- 헤더: 제목·URL·길이·자막 출처·검증 범위 명시
- ## 요약 (5줄 이내)
- ## 준비물 (영상이 전제하는 도구·계정)
- ## 스텝 N: <제목> — 본문에 행동·설정값. **모든 설정값·버튼명에 근거 인용 `(t=MM:SS)` 필수**
- ## 감사 스탬프 (아래 5단계에서 채움)

**검증 규칙 (환각 방지 철칙):**
- 프레임에서 또렷이 읽히지 않는 값은 쓰지 않는다. 재확대: `python scripts/zoom.py <id> --timestamps "12:34@1024"`
- 재확대 후에도 불확실하면 그 값 자리에 `⚠️ 화면 확인 필요 (t=MM:SS)` 표기. 추측 금지.
- 자막이 말한 값과 화면의 값이 다르면 화면 우선, 불일치를 각주로 남긴다.

## 5. 표본 감사 (Agent 서브에이전트, 독립 컨텍스트)
가이드의 검증형 주장(설정값·버튼명·순서) 중 무작위 10개(10개 미만이면 전부)를 뽑아, **가이드 본문을 주지 않고** 서브에이전트에 보낸다:
> "주장: <스텝 텍스트 1개>. 근거 프레임: <frame 경로>. 이 프레임을 Read하고 주장을 반박하라. 프레임만으로 판정 불가면 UNVERIFIABLE."
불일치 주장은 가이드에서 수정하거나 ⚠️ 표기로 강등. 스탬프 형식:
`📋 표본 감사: 10개 주장 중 9 일치, 1 수정 — 추정 오류율 ~10% (검증 범위: 설정값·버튼명·순서)`

## 6. 외부 GT diff
== DESC_TIMESTAMPS == 가 있으면 가이드 스텝과 대조 — 설명란에 있는데 가이드에 없는 항목을 "누락 후보"로 가이드 말미에 보고.

## 7. 사용자 응답
가이드 전문을 채팅에 요약 제시(스텝 제목+핵심 값), 파일 경로 안내. 사용자가 질문을 함께 줬다면 그 질문에 먼저 답한다.

## Q&A (후속 질문)
컨텍스트에 있는 프레임·자막으로 먼저 답한다. 재실행 금지. 새 시각 정보가 필요할 때만 zoom.py --timestamps. video.mp4가 evict됐다는 에러가 나오면 analyze.py 재실행이 필요함을 안내.

## 실패 시
- 다운로드 실패(로그인·지역): 평문 보고, 재시도 금지
- 모든 스크립트의 flags/WARNING은 사용자 보고에 그대로 반영 (조용히 삼키지 않는다)
````

- [ ] **Step 3: README.md 작성** — 설치(개인용 최소): 요구사항(python 3.11+, ffmpeg, yt-dlp, 선택: `pip install faster-whisper`), `~/.config/yta/.env`에 GROQ_API_KEY, 사용법 3줄(`/tuto <url>`), 캐시 위치와 `--cleanup`. 스펙·플랜 링크.

- [ ] **Step 4: 플러그인 로드 확인 (L1)**

Run: Claude Code 재시작 후 `/tuto` 자동완성 노출 확인 (또는 `claude --debug`로 plugin 로드 로그 확인)
Expected: tuto 스킬 인식

- [ ] **Step 5: 커밋**

```bash
git add .claude-plugin/plugin.json skills/tuto/SKILL.md README.md
git commit -m "feat: SKILL.md 오케스트레이션 계약 — 루브릭·검증 패스·표본 감사 (P2/P3/P4/P8)"
```

---

### Task 11: L3 통합 검증 — 실영상 실행

**Files:** 없음 (실행·관측만. 발견된 버그는 이 태스크에서 수정 커밋)

**Interfaces:**
- Consumes: 전체 파이프라인

- [ ] **Step 1: 짧은 실영상 선정** — 자막 있는 5분 내외 한국어 튜토리얼 1편 + 영어 1편 (사용자에게 평소 보는 채널의 URL 요청 권장; 없으면 임의 선정)

- [ ] **Step 2: 패스 1 실행 관측**

Run: `python skills/tuto/scripts/analyze.py "<url>"`
확인 체크리스트 (전부 stdout에서 직접 관측):
- STATUS 줄에 transcript source가 `captions`이고 segments > 0
- dupes_removed > 0 (자동자막이면 반드시 발생)
- ACTIVITY_PEAKS 존재, FRAME 줄 12개 이상
- SponsorBlock 구간이 있다면 그 구간 안 FRAME이 없는지 대조

- [ ] **Step 3: 패스 2 실행 관측**

Run: `python skills/tuto/scripts/zoom.py <video_id> --ranges "<임의 30초 구간>@1024"`
확인: FRAME 출력, 1024px 파일 생성, 재실행 시 기존 파일 재사용(멱등)

- [ ] **Step 4: 무자막 경로 관측** — 자막 없는 영상 1편으로 `analyze.py` 재실행. source가 groq(키 있음) 또는 local/none으로 폴백되고 flags에 사유가 남는지 확인

- [ ] **Step 5: 버그 수정 커밋** (발견 시 개별 커밋) 후 결과 요약 커밋

```bash
git add -A
git commit -m "test: L3 통합 검증 — 실영상 패스1/패스2/폴백 관측 완료"
```

- [ ] **Step 6: L4는 사용자와 함께** — `/tuto <실영상>` 전체 흐름 1회. guide.md에 (a) 타임스탬프 스텝 (b) 인용된 설정값 (c) ⚠️/감사 스탬프 실재 확인. 이후 골든셋 구축(스펙 §8.3)은 사용자 주도로 별도 세션.

---

## Self-Review 결과 (계획 확정 전 점검)

1. **스펙 커버리지**: §3 구조(T1·T10) / §4 계약(T2–T9) / §5 P1·P2(T4·T8·T10) P3(T9·T10) P4(T10) P5(T6) P6(T5) P7(T3·T8) P8(T10) P9(T8) P10(T2) / §6(T3·T4) / §7 Q&A(T10) / §8.1(T10 §5절) §8.2(T3 desc_timestamps + T10 §6절, 고정 댓글은 v1 제외 명시) §8.3–8.4(T11 Step 6, 사용자 주도) / §9(각 스크립트 flags·STATUS) / §10(T1–T9 단위, T11 L3/L4). 갭 없음.
2. **플레이스홀더**: 전 태스크 실코드 포함. "적절히 처리" 류 표현 없음.
3. **타입 일관성**: `FRAME <path> t=<MM:SS>` 계약(T7 produce, T8·T9 consume), transcript.json 스키마(T5 정의, T6 완성, T10 참조), signals.json 구조(T3 정의, T4 확장, T8 consume), `ts_tag` 파일명(T1→T7→T9) 일치 확인.
