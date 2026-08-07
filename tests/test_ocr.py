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
