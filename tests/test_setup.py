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
