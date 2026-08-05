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
