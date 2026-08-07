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
