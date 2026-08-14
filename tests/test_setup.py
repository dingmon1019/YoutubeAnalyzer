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


def test_check_prints_note_when_ytdlp_stale(monkeypatch, tmp_path, capsys):
    """리뷰 발견(Finding F6): --check는 status=="ready"면 무조건 조용히 exit 0 — yt-dlp가
    낡았어도(ytdlp_stale=True) 아무 신호가 없었다. exit 0은 유지하되(설치 자체는 끝난
    상태이므로), stderr에 갱신 권고 NOTE를 남겨야 한다."""
    monkeypatch.setattr(yta_setup.common, "CONFIG_FILE", tmp_path / ".env")
    monkeypatch.setattr(yta_setup, "check_env", lambda: {
        "status": "ready", "missing": [], "ytdlp_version": "2025.01.01",
        "ytdlp_stale": True, "js_runtime": "node", "has_groq_key": False, "has_faster_whisper": False,
        "config_file": str(tmp_path / ".env"),
    })
    monkeypatch.setattr(yta_setup.sys, "argv", ["setup.py", "--check"])

    code = yta_setup.main()

    err = capsys.readouterr().err
    assert "stale" in err
    assert code == 0


def test_check_silent_when_ytdlp_fresh(monkeypatch, tmp_path, capsys):
    """음성 회귀 가드: stale이 아니면 여전히 아무것도 출력하지 않아야 한다(SKILL.md
    프리플라이트 계약 — exit 0은 "조용히 진행"이 기본)."""
    monkeypatch.setattr(yta_setup.common, "CONFIG_FILE", tmp_path / ".env")
    monkeypatch.setattr(yta_setup, "check_env", lambda: {
        "status": "ready", "missing": [], "ytdlp_version": "2026.03.01",
        "ytdlp_stale": False, "js_runtime": "node", "has_groq_key": False, "has_faster_whisper": False,
        "config_file": str(tmp_path / ".env"),
    })
    monkeypatch.setattr(yta_setup.sys, "argv", ["setup.py", "--check"])

    code = yta_setup.main()

    out, err = capsys.readouterr()
    assert out == "" and err == ""
    assert code == 0


def test_scaffold_creates_env(monkeypatch, tmp_path):
    env = tmp_path / "cfg" / ".env"
    monkeypatch.setattr(yta_setup.common, "CONFIG_FILE", env)
    yta_setup.scaffold_config()
    text = env.read_text(encoding="utf-8")
    assert "GROQ_API_KEY=" in text and "CACHE_MAX_VIDEOS=10" in text
    yta_setup.scaffold_config()  # 멱등 — 기존 파일 덮어쓰지 않음
    assert env.read_text(encoding="utf-8") == text


def test_check_env_reports_js_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(yta_setup.common, "CONFIG_FILE", tmp_path / ".env")
    monkeypatch.setattr(yta_setup.common, "detect_js_runtime", lambda: "node")
    r = yta_setup.check_env()
    assert r["js_runtime"] == "node"


def test_check_prints_note_when_no_js_runtime(monkeypatch, tmp_path, capsys):
    """실측(2026-08-14): JS 런타임 부재로 다운로드가 403 즉사했는데 --check는 exit 0으로
    통과시켰다. stale NOTE 선례(F6)와 같은 계약으로 — exit 0 유지 + stderr 경고."""
    monkeypatch.setattr(yta_setup.common, "CONFIG_FILE", tmp_path / ".env")
    monkeypatch.setattr(yta_setup, "check_env", lambda: {
        "status": "ready", "missing": [], "ytdlp_version": "2026.07.04",
        "ytdlp_stale": False, "js_runtime": "", "has_groq_key": False,
        "has_faster_whisper": False, "config_file": str(tmp_path / ".env"),
    })
    monkeypatch.setattr(yta_setup.sys, "argv", ["setup.py", "--check"])
    code = yta_setup.main()
    err = capsys.readouterr().err
    assert "JS runtime" in err and "403" in err
    assert code == 0


def test_check_silent_when_js_runtime_present(monkeypatch, tmp_path, capsys):
    """음성 회귀 가드: 런타임이 있으면 여전히 완전 침묵 + exit 0."""
    monkeypatch.setattr(yta_setup.common, "CONFIG_FILE", tmp_path / ".env")
    monkeypatch.setattr(yta_setup, "check_env", lambda: {
        "status": "ready", "missing": [], "ytdlp_version": "2026.07.04",
        "ytdlp_stale": False, "js_runtime": "deno", "has_groq_key": False,
        "has_faster_whisper": False, "config_file": str(tmp_path / ".env"),
    })
    monkeypatch.setattr(yta_setup.sys, "argv", ["setup.py", "--check"])
    code = yta_setup.main()
    out, err = capsys.readouterr()
    assert out == "" and err == "" and code == 0
