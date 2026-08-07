# tuto 품질증가 라운드 2 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 토큰 중립 상한(분석 1회 달러가중 ≤117만) 아래에서 품질 증가 — 누락 검출 감사 신설, OCR-우선 판독(3단 사다리), 크롭 재확대, 골든셋 지표.

**Architecture:** 파이프라인 구조 불변. 신규 공유 leaf 모듈 `ocr.py`(3단 사다리 검출+추출)와 zoom 크롭 모드를 추가하고, SKILL.md의 판정 루브릭·검증 규칙·감사 절차를 재배분형으로 개정한다. 채택은 게이트(G2 OCR 재현율, 누락 오류주입, E2E 비용 상한)가 심판한다. 스펙: `docs/superpowers/specs/2026-08-06-tuto-quality-round2-design.md`.

**Tech Stack:** Python 표준 라이브러리, ffmpeg, Windows 내장 OCR(`Windows.Media.Ocr`, powershell.exe 5.1 WinRT), Tesseract(폴백), pytest.

## Global Constraints

- 플랫폼: Windows 11 / 파이썬 명령은 **`python`**. 테스트: 저장소 루트에서 `python -m pytest tests -q` (현 기준선 93 passed).
- 절대 조건 2개: **품질 비저하**(벤치마크 값 95/95 유지) + **토큰 중립 상한**(분석 1회 달러가중 ≤ 117만, message.id dedup 방법론).
- 공유 모듈은 `common.py`와 **신규 `ocr.py`(main 없는 leaf, common과 stdlib만 임포트)** 로 한정 — 그 외 스크립트 간 임포트 금지. 외부 Python 패키지 추가 금지(OCR은 OS API·외부 바이너리 호출만).
- OCR은 **로컬 실행만** — 프레임·텍스트를 외부 API로 보내지 않는다.
- Windows 내장 OCR 호출은 **`powershell.exe`(5.1)** 로 한다 — pwsh(7)는 WinRT 프로젝션을 로드하지 못한다.
- 커밋: `fix:`/`feat:`/`docs:` + 한국어 한 줄, 말미 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- fail-loud: 게이트 미달·기능 비활성은 조용히 넘기지 않고 flags/NOTE/보고로 드러낸다.
- 벤치마크 캐시: `C:\Users\hwangjs\.yta\cache\zP3i_7xZW7Q\` (video.mp4·frames·guide-baseline.md 존재. video가 LRU로 지워졌으면 analyze가 재다운로드).

---

### Task 1: 공유 OCR 모듈 — 3단 사다리 검출 + 추출 (스펙 Q2 전반부)

**Files:**
- Create: `skills/tuto/scripts/ocr.py`
- Create: `skills/tuto/scripts/ocr_win.ps1`
- Modify: `skills/tuto/scripts/common.py` (frame_label 헬퍼 추가), `skills/tuto/scripts/frames.py:82-87` (report가 헬퍼 사용)
- Test: `tests/test_ocr.py` (신규), `tests/test_frames.py` (기존 report 테스트 회귀 확인만)

**Interfaces:**
- Consumes: `common.run(cmd, timeout)`, `common.frame_label(path) -> str` (이 태스크에서 신설)
- Produces: `ocr.detect_engine() -> str` ("winocr" | "tesseract" | "") / `ocr.extract_text(image_path) -> str` (비활성·실패·저신뢰면 "") / `ocr.extract_batch(paths) -> dict` / `ocr.report(paths) -> None` (OCRTXT 라인 출력). Task 2가 이 넷을 그대로 쓴다.

- [ ] **Step 1: common.frame_label 헬퍼 — 실패하는 테스트** — `tests/test_common.py` 말미:

```python
def test_frame_label_parses_tag_variants():
    """frames.report의 태그 파싱을 공용 헬퍼로 승격 — ocr.py(OCRTXT 라인)와 공유하기 위함.
    데시초 접미사(d5)·크롭 접미사(c...)는 라벨에서 제거되고 초 단위 MM:SS만 남는다."""
    assert common.frame_label(Path("t0312_512.jpg")) == "03:12"
    assert common.frame_label(Path("t0312d5_1024.jpg")) == "03:12"
    assert common.frame_label(Path("t10312_512.jpg")) == "1:03:12"
    assert common.frame_label(Path("t0618d4c10_200_400_120_1024.jpg")) == "06:18"
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_common.py -q` / Expected: FAIL (`frame_label` 부재)

- [ ] **Step 3: 구현** — `common.py` 말미:

```python
def frame_label(path) -> str:
    """프레임 파일명(t0312_512.jpg / t0312d5_1024.jpg / t0618d4c...jpg)에서 t=MM:SS 라벨을
    복원한다. frames.report와 ocr.report가 공유 — 파싱 규칙이 두 곳에서 어긋나지 않게 한다."""
    tag = Path(path).name.split("_")[0][1:]     # t0312d5 → 0312d5
    tag = tag.split("d")[0].split("c")[0]       # 데시초·크롭 접미사 제거
    if len(tag) <= 4:
        return tag[:-2] + ":" + tag[-2:]
    return tag[:-4] + ":" + tag[-4:-2] + ":" + tag[-2:]
```

`frames.py`의 `report()` 본문을 헬퍼 호출로 교체:

```python
def report(paths: list) -> None:
    for p in paths:
        print(f"FRAME {p} t={common.frame_label(p)}")
```

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/test_common.py tests/test_frames.py -q` / Expected: 전부 PASS

- [ ] **Step 5: ocr_win.ps1 작성** — WinRT 프로젝션은 powershell.exe(5.1) 전용. `-Probe`는 한국어 팩 지원만 검사(exit 0/3):

```powershell
param([string]$ImagePath, [string]$Lang = "ko", [switch]$Probe)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$lang = New-Object Windows.Globalization.Language $Lang
if (-not [Windows.Media.Ocr.OcrEngine]::IsLanguageSupported($lang)) { exit 3 }
if ($Probe) { exit 0 }
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
  Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
                 $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) {
  $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(); $task.Result
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path $ImagePath).Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$result.Text
```

- [ ] **Step 6: ocr.py 실패하는 테스트** — `tests/test_ocr.py` 신규 (검출 사다리는 mock, 실 OCR은 skipif):

```python
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import common
import ocr


def _reset(monkeypatch):
    monkeypatch.setattr(ocr, "_engine_cache", None)


def test_detect_prefers_winocr_when_probe_ok(monkeypatch):
    """사다리 0순위: powershell 프로브가 exit 0이면 winocr — tesseract 유무와 무관."""
    _reset(monkeypatch)
    monkeypatch.setattr(ocr.platform, "system", lambda: "Windows")
    monkeypatch.setattr(ocr.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
    monkeypatch.setattr(ocr.shutil, "which", lambda _: r"C:\tesseract.exe")
    assert ocr.detect_engine() == "winocr"


def test_detect_falls_to_tesseract_when_probe_fails(monkeypatch):
    """0순위 프로브 exit 3(ko팩 없음)이면 tesseract로 강등 — kor 언어 목록 확인 포함."""
    _reset(monkeypatch)
    monkeypatch.setattr(ocr.platform, "system", lambda: "Windows")

    def fake_run(cmd, **k):
        if "powershell.exe" in str(cmd[0]):
            return subprocess.CompletedProcess(cmd, 3, "", "")
        return subprocess.CompletedProcess(cmd, 0, "eng\nkor\nosd\n", "")

    monkeypatch.setattr(ocr.subprocess, "run", fake_run)
    monkeypatch.setattr(ocr.shutil, "which", lambda _: r"C:\tesseract.exe")
    assert ocr.detect_engine() == "tesseract"


def test_detect_disabled_when_nothing_available(monkeypatch):
    """둘 다 없으면 '' — 조용한 성공 금지(호출부가 flags에 ocr_absent를 띄운다)."""
    _reset(monkeypatch)
    monkeypatch.setattr(ocr.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ocr.shutil, "which", lambda _: None)
    assert ocr.detect_engine() == ""


def test_extract_text_caps_at_300_chars(monkeypatch):
    """OCRTXT 상한 300자 — 초과분은 '…' 표시로 절단."""
    _reset(monkeypatch)
    monkeypatch.setattr(ocr, "detect_engine", lambda: "winocr")
    monkeypatch.setattr(ocr, "_run_winocr", lambda p: "가" * 400)
    out = ocr.extract_text(Path("t0001_512.jpg"))
    assert len(out) == 301 and out.endswith("…")


def test_extract_text_empty_when_disabled(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setattr(ocr, "detect_engine", lambda: "")
    assert ocr.extract_text(Path("t0001_512.jpg")) == ""


def test_tesseract_low_confidence_dropped(monkeypatch):
    """tesseract 평균 conf < 50이면 저신뢰 — 빈 문자열(라인 생략용)."""
    _reset(monkeypatch)
    tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
           "5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t30.0\t흐림\n"
           "5\t1\t1\t1\t1\t2\t0\t0\t10\t10\t40.0\t글자\n")
    monkeypatch.setattr(ocr.common, "run",
                        lambda cmd, timeout=60: subprocess.CompletedProcess(cmd, 0, tsv, ""))
    assert ocr._run_tesseract(Path("x.jpg")) == ""


def test_report_prints_ocrtxt_lines_and_skips_empty(monkeypatch, capsys):
    _reset(monkeypatch)
    monkeypatch.setattr(ocr, "extract_batch",
                        lambda paths: {paths[0]: "메뉴: 청약신청", paths[1]: ""})
    ocr.report([Path("t0312_512.jpg"), Path("t0500_512.jpg")])
    out = capsys.readouterr().out
    assert "OCRTXT t=03:12: 메뉴: 청약신청" in out
    assert "t=05:00" not in out
```

- [ ] **Step 7: 실패 확인** — Run: `python -m pytest tests/test_ocr.py -q` / Expected: FAIL (모듈 부재)

- [ ] **Step 8: ocr.py 구현**

```python
"""OCR 판독 3단 사다리: Windows 내장(0MB) → Tesseract+kor(~100MB) → 비활성. 스펙 R2 Q2.
main 없는 공유 leaf — common과 stdlib만 임포트한다. 프레임·텍스트는 로컬에서만 처리."""
import os
import platform
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import common

MAX_CHARS = 300
TESS_MIN_CONF = 50.0          # tesseract TSV conf 평균이 이 밑이면 저신뢰 — 라인 생략 (스펙 Q2)
MAX_WORKERS = max(1, min(8, (os.cpu_count() or 4) - 1))
_PS_SCRIPT = Path(__file__).parent / "ocr_win.ps1"
_engine_cache = None          # None=미검출, ""=비활성, "winocr"|"tesseract"


def detect_engine() -> str:
    """검출 결과는 프로세스 내 캐시 — powershell 프로브(~1초)를 반복하지 않는다."""
    global _engine_cache
    if _engine_cache is not None:
        return _engine_cache
    eng = ""
    if platform.system() == "Windows":
        try:
            p = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(_PS_SCRIPT), "-Probe"],
                capture_output=True, text=True, timeout=30)
            if p.returncode == 0:
                eng = "winocr"
        except (OSError, subprocess.TimeoutExpired):
            pass
    if not eng and shutil.which("tesseract"):
        try:
            p = subprocess.run(["tesseract", "--list-langs"],
                               capture_output=True, text=True, timeout=30)
            if "kor" in (p.stdout + p.stderr):
                eng = "tesseract"
        except (OSError, subprocess.TimeoutExpired):
            pass
    _engine_cache = eng
    return eng


def _run_winocr(path: Path) -> str:
    try:
        p = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(_PS_SCRIPT), "-ImagePath", str(path), "-Lang", "ko"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _run_tesseract(path: Path) -> str:
    try:
        p = common.run(["tesseract", str(path), "stdout", "-l", "kor", "--psm", "6", "tsv"],
                       timeout=60)
    except RuntimeError:
        return ""
    words, confs = [], []
    for line in p.stdout.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) >= 12 and cols[0] == "5" and cols[11].strip():
            confs.append(float(cols[10]))
            words.append(cols[11].strip())
    if not words or (sum(confs) / len(confs)) < TESS_MIN_CONF:
        return ""
    return " ".join(words)


def extract_text(path) -> str:
    eng = detect_engine()
    if not eng:
        return ""
    text = _run_winocr(Path(path)) if eng == "winocr" else _run_tesseract(Path(path))
    text = " ".join(text.split())
    return text[:MAX_CHARS] + "…" if len(text) > MAX_CHARS else text


def extract_batch(paths: list) -> dict:
    if not paths:
        return {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        return dict(zip(paths, ex.map(extract_text, paths)))


def report(paths: list) -> None:
    """FRAME 라인들 뒤에 붙는 OCRTXT 라인 출력 — 빈 결과(실패·저신뢰·비활성)는 생략."""
    texts = extract_batch(paths)
    for p in paths:
        t = texts.get(p, "")
        if t:
            print(f"OCRTXT t={common.frame_label(p)}: {t}")
```

- [ ] **Step 9: 통과 확인** — Run: `python -m pytest tests/test_ocr.py -q` / Expected: 전부 PASS. 이어서 실기 확인(L3, 이 머신은 Windows 11+한국어): `python -c "import sys; sys.path.insert(0,'skills/tuto/scripts'); import ocr; print(repr(ocr.detect_engine())); print(ocr.extract_text(r'C:\Users\hwangjs\.yta\cache\zP3i_7xZW7Q\frames\t1406d2_1024.jpg')[:120])"` — 엔진명과 날짜 텍스트 일부가 나오는지 관측해 보고서에 기록 (실패해도 태스크는 mock 테스트로 성립 — 실기 결과는 G2 게이트 입력).

- [ ] **Step 10: 전체 테스트 + 커밋**

Run: `python -m pytest tests -q` / Expected: 기존 93 + 신규 8 전부 PASS

```bash
git add skills/tuto/scripts/ocr.py skills/tuto/scripts/ocr_win.ps1 skills/tuto/scripts/common.py skills/tuto/scripts/frames.py tests/test_ocr.py tests/test_common.py
git commit -m "feat: OCR 3단 사다리 모듈 — Windows 내장(0MB)→Tesseract→비활성, OCRTXT 300자 상한"
```

---

### Task 2: OCRTXT 파이프라인 통합 + ocr_absent 플래그 (스펙 Q2 후반부)

**Files:**
- Modify: `skills/tuto/scripts/analyze.py` (run_pass1 — frames.report 뒤 + STATUS flags), `skills/tuto/scripts/zoom.py` (main — frames.report 뒤), `skills/tuto/scripts/setup.py` (--check NOTE)
- Test: `tests/test_analyze.py`, `tests/test_zoom.py` (추가)

**Interfaces:**
- Consumes: `ocr.detect_engine() -> str`, `ocr.report(paths) -> None` (Task 1)
- Produces: 보고서 계약 — `== FRAMES ==` 블록이 `FRAME ...` 라인들 뒤에 `OCRTXT t=MM:SS: <텍스트>` 라인들을 갖는다. STATUS flags에 엔진 부재 시 `ocr_absent` 포함. Task 4의 SKILL.md 문구가 이 계약을 참조한다.

- [ ] **Step 1: 실패하는 테스트** — `tests/test_analyze.py` 말미:

```python
def test_status_flags_include_ocr_absent_when_no_engine(monkeypatch, capsys):
    """OCR 비활성은 조용히 넘기지 않는다 — STATUS flags에 ocr_absent 명시 (스펙 Q2)."""
    monkeypatch.setattr(analyze.ocr, "detect_engine", lambda: "")
    assert analyze._ocr_flags() == ["ocr_absent"]
    monkeypatch.setattr(analyze.ocr, "detect_engine", lambda: "winocr")
    assert analyze._ocr_flags() == []
```

`tests/test_zoom.py` 말미:

```python
def test_zoom_report_emits_ocrtxt_after_frames(synth_clip, tmp_path, monkeypatch, capsys):
    """zoom 보고서 계약: FRAME 라인 뒤에 OCRTXT 라인 — 판독 텍스트가 판정자에게 전달된다."""
    cd = tmp_path / "abc12345678"
    cd.mkdir()
    (cd / "video.mp4").write_bytes(synth_clip.read_bytes())
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.ocr, "extract_batch",
                        lambda paths: {p: "파랑 화면" for p in paths})
    monkeypatch.setattr(zoom.sys, "argv", ["zoom.py", "abc12345678", "--timestamps", "0:01"])
    assert zoom.main() == 0
    out = capsys.readouterr().out
    assert out.index("FRAME ") < out.index("OCRTXT t=00:01: 파랑 화면")
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_analyze.py tests/test_zoom.py -q` / Expected: 신규 2개 FAIL

- [ ] **Step 3: 구현** — `analyze.py`: `import ocr` 추가, 헬퍼와 두 곳 수정:

```python
def _ocr_flags() -> list:
    return [] if ocr.detect_engine() else ["ocr_absent"]
```

STATUS 라인의 `flags={(sig['flags'] + tr['flags']) or 'none'}` 를
`flags={(sig['flags'] + tr['flags'] + _ocr_flags()) or 'none'}` 로 교체.
`frames.report(kept)` 바로 다음 줄에 `ocr.report(kept)` 추가.

`zoom.py`: `import ocr` 추가, main의 `frames.report(kept_all)` 다음 줄에 `ocr.report(kept_all)` 추가.

`setup.py`: `--check` 경로에서 (exit 0이어도) 엔진 부재 시 stderr NOTE 한 줄:

```python
    import ocr
    if not ocr.detect_engine():
        print("NOTE: OCR 엔진 없음 — Windows OCR ko팩 또는 tesseract(+kor) 설치 시 "
              "잔글씨 판독(OCRTXT)이 활성화됩니다", file=sys.stderr)
```

(setup.py는 ocr를 임포트한다 — ocr는 공유 leaf라 Global Constraints 허용 범위.)

- [ ] **Step 4: 전체 테스트 + 커밋**

Run: `python -m pytest tests -q` / Expected: 전부 PASS

```bash
git add skills/tuto/scripts/analyze.py skills/tuto/scripts/zoom.py skills/tuto/scripts/setup.py tests/test_analyze.py tests/test_zoom.py
git commit -m "feat: OCRTXT 보고서 통합 — analyze/zoom 프레임 뒤 판독 텍스트, ocr_absent 플래그"
```

---

### Task 3: zoom 크롭 모드 (스펙 Q3)

**Files:**
- Modify: `skills/tuto/scripts/zoom.py` (인자 + 크롭 경로)
- Test: `tests/test_zoom.py` (추가)

**Interfaces:**
- Consumes: `common.run`, `common.frame_label`, `frames.report`, `ocr.report` (기존)
- Produces: CLI 계약 — `zoom.py <id> --crop "<frames/파일명>@x,y,w,h"` (쉼표로 다중). 출력 파일명 `<원스템>c<x>_<y>_<w>_<h>.jpg`, FRAME+OCRTXT 라인 보고. 원본 파일 부재 시 stderr 평문 에러 + exit 1. video.mp4 불필요(eviction 후에도 동작).

- [ ] **Step 1: 실패하는 테스트** — `tests/test_zoom.py` 말미:

```python
def test_crop_mode_crops_existing_frame_without_video(synth_clip, tmp_path, monkeypatch, capsys):
    """크롭 모드: 기존 프레임에서 ffmpeg crop — video.mp4가 없어도(eviction 후) 동작해야 한다."""
    cd = tmp_path / "abc12345678"
    (cd / "frames").mkdir(parents=True)
    src = cd / "frames" / "t0618_1024.jpg"
    subprocess.run(["ffmpeg", "-y", "-ss", "1", "-i", str(synth_clip),
                    "-frames:v", "1", "-vf", "scale=1024:-2", str(src)],
                   capture_output=True, check=True)
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.sys, "argv",
                        ["zoom.py", "abc12345678", "--crop", "t0618_1024.jpg@100,50,300,200"])
    assert zoom.main() == 0
    out = capsys.readouterr().out
    assert "t0618_1024c100_50_300_200.jpg" in out and "FRAME" in out


def test_crop_mode_missing_source_fails_loud(tmp_path, monkeypatch, capsys):
    cd = tmp_path / "abc12345678"
    (cd / "frames").mkdir(parents=True)
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.sys, "argv",
                        ["zoom.py", "abc12345678", "--crop", "없는파일.jpg@0,0,10,10"])
    assert zoom.main() == 1
    assert "ERROR" in capsys.readouterr().err
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_zoom.py -q` / Expected: 신규 2개 FAIL (`--crop` 미지원)

- [ ] **Step 3: 구현** — `zoom.py` main: `ap.add_argument("--crop", help='기존 프레임 크롭: "<frames/파일명>@x,y,w,h" 쉼표구분 다중')` 추가. 인자 분기(`--ranges`/`--timestamps`보다 먼저 처리, 상호 배타 아님이지만 crop 지정 시 crop만 수행):

```python
    if args.crop:
        # 재확대를 영상 재추출 대신 기존 프레임 크롭으로 (스펙 R2 Q3) — 재디코드가 없어
        # 빠르고 더 선명하며, video.mp4가 evict된 뒤에도 동작한다.
        out_paths = []
        for spec in args.crop.split(","):
            name, _, geom = spec.strip().partition("@")
            src = cd / "frames" / name
            if not src.exists():
                print(f"ERROR: 크롭 원본 없음: {src}", file=sys.stderr)
                return 1
            x, y, w, h = (int(v) for v in geom.split(","))
            dst = src.with_name(f"{src.stem}c{x}_{y}_{w}_{h}.jpg")
            if not dst.exists():
                common.run(["ffmpeg", "-y", "-i", src, "-vf",
                            f"crop={w}:{h}:{x}:{y}", "-q:v", "3", dst])
            out_paths.append(dst)
        print(f"zoom: {len(out_paths)} cropped")
        frames.report(out_paths)
        ocr.report(out_paths)
        return 0
```

- [ ] **Step 4: 전체 테스트 + 커밋**

Run: `python -m pytest tests -q` / Expected: 전부 PASS

```bash
git add skills/tuto/scripts/zoom.py tests/test_zoom.py
git commit -m "feat: zoom --crop — 재확대를 기존 프레임 크롭으로 (재디코드 없음, eviction 무관)"
```

---

### Task 4: SKILL.md 개정 — 루브릭·검증·감사 재배분 (스펙 Q1·Q2·Q3 문서)

**Files:**
- Modify: `skills/tuto/SKILL.md`

**Interfaces:**
- Consumes: Task 1-3의 보고서·CLI 계약 (OCRTXT 라인, `--crop` 사용법)
- Produces: 감사 실행 계약 — Task 6 오류주입·E2E가 이 절차문 그대로 수행한다.

- [ ] **Step 1: §1 보고서 안내에 OCRTXT 한 줄 추가** — "이어서 `== FRAMES ==` 아래 모든 FRAME 경로를 병렬로 Read한다." 문장 뒤에:

> FRAME 라인 뒤의 `OCRTXT t=MM:SS: …` 라인은 해당 프레임의 로컬 OCR 판독 텍스트다 —
> 값 판독의 보조 증거로 쓰되, 서열은 **화면 > OCRTXT > 자막**이다 (OCR도 오독한다).
> STATUS flags에 `ocr_absent`가 있으면 이 라인은 없다.

- [ ] **Step 2: §2 판정 루브릭 5번(해상도) 교체** — 기존 "해상도: 설정값·코드·메뉴 텍스트를 읽어야 하는 구간만 @1024, 나머지는 512." 를:

> 5. 해상도: 설정값·코드·메뉴 텍스트 구간이라도 **지도 512 프레임의 OCRTXT로 해당 값이
>    이미 또렷이 판독되면 @1024를 배정하지 않는다**(토큰 절감 — 스펙 R2 Q2). OCRTXT가
>    없거나(`ocr_absent`) 값이 안 읽히면 기존대로 @1024.

- [ ] **Step 3: §4 검증 규칙 1(재확대) 교체** — 기존 `python "<SKILL_DIR>/scripts/zoom.py" <id> --timestamps "12:34@1024"` 안내를:

> 1. 프레임에서 또렷이 읽히지 않는 값은 쓰지 않는다. **재확대는 기존 확대 프레임의 크롭
>    우선**: `python "<SKILL_DIR>/scripts/zoom.py" <id> --crop "t1234d5_1024.jpg@x,y,w,h"`
>    (좌표는 읽으려는 영역). 해당 시점의 1024 프레임이 없을 때만
>    `--timestamps "12:34@1024"`로 재추출한다. **크롭 재질의는 영상당 5회 이내.**

- [ ] **Step 4: §5 감사 재배분** — 기존 첫 문단("…중 무작위로 10개(10개 미만이면 전부)를 뽑는다")을:

> 가이드의 검증형 주장(설정값·버튼명·순서) 중 **6개**를 뽑되(6개 미만이면 전부), **서식·상태
> 변화 주장(볼드/색상/토글/활성화)을 최소 1건 포함**한다 — 화면녹화 튜토리얼에서 가장 잘
> 누락되는 범주다. **가이드 본문은 주지 않고** 주장 하나와 근거 프레임만 독립된 Agent
> 서브에이전트에 보낸다.

로 교체(이후 감사 에이전트 모델·에스컬레이션 문장은 유지). §5 말미 스탬프 앞에 커버리지 감사 절차 신설:

> **커버리지 감사(누락 검출, 1건):** 별도 Sonnet Agent에 자막 전문·챕터·DESC_TIMESTAMPS와
> **가이드의 스텝 제목 목록만** 보낸다(본문 비공개):
>
> > "아래 소스에서 시청자가 따라해야 할 '기대 스텝 체크리스트'를 먼저 만들어라. 그런 다음
> > 가이드 스텝 목록과 대조해 체크리스트에는 있으나 가이드에 없는 항목만
> > `- [MM:SS] <내용> — 근거: <자막 인용>` 형식으로 반환하라. 없으면 'none'."
>
> 반환된 누락 후보는 프레임·자막으로 직접 확인해 **명백한 누락이면 가이드에 스텝을 보강
> (1회 한정)**하고, 불확실하면 "누락 후보" 절에 기재한다. 재분석 루프는 돌지 않는다.
> STATUS flags에 자막 없음(no transcript)이 있으면 커버리지 감사는 스킵하고 스탬프에
> 명시한다 — 체크리스트 원천이 없다.

스탬프 형식 교체:

> `📋 표본 감사: 6개 주장 중 6 일치 — Sonnet 6건 판정 + 상위 모델 재검 0건 / 커버리지: 기대 스텝 12개 중 누락 후보 1건 (검증 범위: 설정값·버튼명·순서·서식변화·커버리지)`

- [ ] **Step 5: 정합 확인 (L1)** — "감사", "1024", "재확대", "OCRTXT"로 문서 전체를 검색해 남은 문구가 새 계약과 모순되지 않는지 읽어서 확인. §3.3 예산 문구("1024px 확대는 총 20장 이내")는 유지(상한이므로 무모순).

- [ ] **Step 6: 커밋**

```bash
git add skills/tuto/SKILL.md
git commit -m "feat: SKILL.md 라운드2 — OCR-우선 루브릭·크롭 재확대·감사 6+커버리지 재배분"
```

---

### Task 5: G2 OCR 게이트 실측 (스펙 §4 게이트 2 — 실행 태스크)

**Files:** 코드 없음 — 실행 세션 수행, 결과는 보고와 스펙 이력에 기록.

**Interfaces:**
- Consumes: Task 1-2 (ocr.py 실기), 벤치마크 캐시 frames/
- Produces: **1024 축소 루브릭의 발효/철회 판정** (Task 6 E2E의 zoom-plan에 반영)

- [ ] **Step 1: 512 대조 프레임 추출** — 1024 프레임 13장과 같은 시점을 512로 (dedup 없이):

```bash
python skills/tuto/scripts/frames.py "C:\Users\hwangjs\.yta\cache\zP3i_7xZW7Q\video.mp4" --timestamps "237.3,238.4,294.4,310.6,328.3,339.1,353.2,354.2,362.2,377.3,378,389,846.2,891,902.2" --res 512 --out "C:\Users\hwangjs\AppData\Local\Temp\claude_g2_512" --no-dedup
```

- [ ] **Step 2: 두 세트 OCR 실행** — 파이썬 원라이너로 1024 원본 13장과 512 대조본 각각 `ocr.extract_text` 실행, 결과 텍스트를 나란히 기록.

- [ ] **Step 3: 값 재현율 판정** — 라운드1 감사 통과 값 체크리스트(24개)에 대해 **512+OCRTXT 텍스트에서 판독 가능한지** 채점 (표기 변형 허용 — 쉼표·공백·단위):
  19세 / 2026.08.06 / 7년 / 120% / 10,562,642 / 7,039,524 / 9,802,115 / 10만원 / 추첨 / 100%·110%·120%(순위 3값) / 150,000,000 / 529,000 / 516,000 / 605,000 / 397,000 / 929,000 / 954,000 / 2026.08.12 / 08.14 / 09:00~17:30 / 08.21 / 16:00 / 청약신청(메뉴명) / Step.01 주택선택
  판정: **≥23/24 (95%)** 이면 1024 축소 루브릭 발효 유지. 미달이면 SKILL.md §2 루브릭 5번을 원문으로 되돌리는 커밋(OCRTXT는 동봉 유지) + 스펙 §Q2에 실측치 추기.

- [ ] **Step 4: 결과 기록** — 재현율 수치·엔진명(winocr/tesseract)·미판독 값 목록을 보고서와 렛저에 기록. 스펙 수정이 있으면 커밋.

---

### Task 6: 누락 오류주입 + E2E 재분석 + 비용 상한 (스펙 §4 게이트 1·3 — 실행 태스크)

**Files:** 코드 없음 — 실행 세션 수행.

**Interfaces:**
- Consumes: Task 1-5 전부, 벤치마크 `guide-baseline.md`(95개 값 기준), 라운드1 측정 방법론
- Produces: 라운드2 완료/미달 판정

- [ ] **Step 1: 누락 오류주입 시험** — 벤치마크 가이드의 스텝 제목 목록에서 **"스텝 6: 공급 일정 확인"을 고의 삭제**한 목록 + 자막 전문·챕터·DESC_TIMESTAMPS로 Task 4의 커버리지 감사 프롬프트를 Sonnet Agent에 실행. Expected: 누락 후보에 공급 일정(14:05 부근)이 검출됨. 검출 실패 시 커버리지 감사 프롬프트를 1회 개선 후 재시험, 그래도 실패면 fail-loud 보고.

- [ ] **Step 2: E2E 재분석** — 라운드1 Task 7과 동일 절차: `frames/` 비우고(guide-baseline.md 보존) analyze→zoom(동일 플랜, 단 **G2 발효 시 1024 구간을 512로 낮춘 개정 플랜**을 스텝 판정으로 재산출)→가이드 재작성→**신규 감사(6건+커버리지)**. Expected: (a) guide-baseline.md의 `(t=)` 인용 값 전부 동일, (b) 감사 6/6 + 커버리지 실행 완료, (c) 시간 기록.

- [ ] **Step 3: 비용 집계** — 세션 jsonl message.id dedup 방법론(라운드1 usage 스크립트 재사용, 서브에이전트 모델 단가 가중: sonnet 1/5·haiku 1/15)으로 이 E2E의 달러가중 실효 토큰 산출. 판정: **≤ 117만**. 미달 시 수치와 원인 분해를 보고하고 중단(레버 조정은 사용자 논의).

- [ ] **Step 4: 렛저·보고 기록** — 게이트 3종 결과표.

---

### Task 7: 골든셋 평가 프로토콜 문서 (스펙 Q4)

**Files:**
- Create: `docs/eval/golden-set-protocol.md`

**Interfaces:**
- Consumes: 스펙 Q4의 지표 정의
- Produces: 골든셋 실측(사용자 URL 제공 후 별도 실행)이 따를 프로토콜

- [ ] **Step 1: 문서 작성** — 아래 내용을 그대로 담는다 (요약이 아니라 전문):

```markdown
# tuto 골든셋 평가 프로토콜 (v1)

## 구성
사용자가 직접 따라해 본 튜토리얼 3~5편. 각 편: (1) tuto 초안 가이드 생성 →
(2) 사용자 교정(누락 스텝 추가·오류 값 수정) → (3) 교정본을 레퍼런스로 확정
(`~/.yta/golden/<video_id>/reference.md`, 초안은 `draft-<날짜>.md`로 보존).

## 지표 (per-video 진단 — n≤5이므로 통계적 일반화 주장 금지)
### 스텝 재현율 (R1-Recall)
- 분모: 레퍼런스의 스텝 수. 분자: 초안 스텝과 의미 매칭된 레퍼런스 스텝 수.
- 매칭: LLM 판정("같은 행동을 지시하는가"), many-to-one 허용(초안 한 스텝이
  레퍼런스 두 스텝을 덮으면 둘 다 매칭), 타임스탬프 ±30초 내만 인정.
- LLM 매칭 결과는 **사용자 대조 1회 이상** 검증 후 확정 (LLM-judge 단독 금지).
### 값 정확도 (Value-F1)
- 대상: 레퍼런스 스텝의 설정값·버튼명·수치 (스텝당 0..n개).
- 정규화 후 토큰 F1: 쉼표·공백 제거, 전각→반각, "만원/만 원" 통일, %·원 단위 접미
  분리, 한글 숫자(천/만/억)는 아라비아로 전개. 정규화 규칙은 이 문서가 원본이며
  케이스 발견 시 여기에 추가한다.
### 보고 형식
| video | 스텝(참조/초안/매칭) | R1-Recall | 값(참조/일치/F1) | 특이 |
비고란에 장르·자막 유무·ocr_absent 여부를 기록한다.

## 회귀 사용
라운드 완료 시마다 동일 골든셋으로 재측정해 per-video 증감을 기록한다.
지표 하락이 있으면 해당 라운드는 품질 비저하 게이트 위반으로 취급한다.
```

- [ ] **Step 2: 커밋**

```bash
git add docs/eval/golden-set-protocol.md
git commit -m "docs: 골든셋 평가 프로토콜 v1 — R1-Recall·Value-F1·per-video 진단"
```

---

### Task 8: 릴리스 + 메모리 갱신

**Files:**
- Modify: `.claude-plugin/plugin.json:3` (`"version": "0.1.1"` → `"0.1.2"`)
- Modify: 메모리 `yta-watch-benchmark.md`(라운드2 실측 추기), `yta-post-merge-followups.md`(라운드2 상태 갱신)

- [ ] **Step 1: 게이트 전부 통과 확인** — Task 5 판정 기록 + Task 6 게이트 3종 + `python -m pytest tests -q` 최종 PASS.

- [ ] **Step 2: 버전 범프 + 커밋**

```bash
git add .claude-plugin/plugin.json
git commit -m "chore: v0.1.2 — 품질증가 라운드2 (OCR 사다리·크롭 재확대·감사 재배분·골든셋 프로토콜)"
```

- [ ] **Step 3: 플러그인 갱신** — `claude plugin update tuto@yta` (0.1.2 반영 확인).

- [ ] **Step 4: 메모리 갱신** — 벤치마크 파일에 라운드2 수치(G2 재현율·E2E 비용·시간), followups에 남은 이연(계층 분할, 평가 러너 코드화, PaddleOCR 각주) 정리.

---

## Self-Review 결과

- 스펙 커버리지: Q1→Task 4·6, Q2→Task 1·2·4·5, Q3→Task 3·4, Q4→Task 7, 게이트 1→Task 1-3 테스트+Task 8, 게이트 2→Task 5, 게이트 3→Task 6, 게이트 4→Task 7(프로토콜)+사용자 URL 제공 후 실측(계획 범위 밖임을 명시). 누락 없음.
- 플레이스홀더: 없음 — ocr_win.ps1·ocr.py·크롭 분기·SKILL.md 문구·G2 값 체크리스트까지 실물 수록.
- 타입 일관성: `ocr.detect_engine()->str("winocr"|"tesseract"|"")`·`extract_text->str`·`extract_batch->dict`·`report(paths)`·`common.frame_label(path)->str`가 정의(Task 1)와 사용처(Task 2·3) 일치. G2의 512 추출 타임스탬프 15개는 1024 실물 13장+예비 2장(354.2, 378)을 포함한다.
