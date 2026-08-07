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


def test_load_config_strips_bom(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("GROQ_API_KEY=abc\n", encoding="utf-8-sig")
    monkeypatch.setattr(common, "CONFIG_FILE", f)
    assert common.load_config().get("GROQ_API_KEY") == "abc"


def test_utf8_stdout_forces_utf8_on_pipe():
    """Windows 파이프에서 stdout이 로케일(cp949)로 인코딩되던 결함의 회귀 테스트 —
    PYTHONUTF8/PYTHONIOENCODING 없이 서브프로세스로 실행해 실제 파이프 환경을 재현한다."""
    import os
    import subprocess
    scripts = Path(__file__).parent.parent / "skills" / "tuto" / "scripts"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    code = (
        f"import sys; sys.path.insert(0, r'{scripts}'); "
        "import common; common.utf8_stdout(); print('한—글')"
    )
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env)
    assert p.returncode == 0, p.stderr
    assert p.stdout.decode("utf-8").strip() == "한—글"


def test_utf8_stdout_ignores_streams_without_reconfigure(monkeypatch):
    """capsys/StringIO처럼 reconfigure가 없는 스트림에서도 예외 없이 통과해야 한다."""
    import io
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    common.utf8_stdout()


def test_frame_label_parses_tag_variants():
    """frames.report의 태그 파싱을 공용 헬퍼로 승격.
    데시초 접미사(d5)·크롭 접미사(c...)는 라벨에서 제거되고 초 단위 MM:SS만 남는다."""
    assert common.frame_label(Path("t0312_512.jpg")) == "03:12"
    assert common.frame_label(Path("t0312d5_1024.jpg")) == "03:12"
    assert common.frame_label(Path("t10312_512.jpg")) == "1:03:12"
    assert common.frame_label(Path("t0618d4_1024c10_200_400_120.jpg")) == "06:18"
