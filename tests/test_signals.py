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


def test_build_signals_flags_when_absent(monkeypatch):
    monkeypatch.setattr(signals, "fetch_sponsorblock", lambda vid: [])
    sig = signals.build_signals({}, "abc12345678", None)
    assert "heatmap_absent" in sig["flags"]
    assert "chapters_absent" in sig["flags"]
    assert sig["activity"] == {"curve": [], "peaks": []}
    assert set(sig) == {"heatmap", "chapters", "desc_timestamps", "sponsorblock", "activity", "flags"}


def test_build_signals_sponsorblock_error_flag(monkeypatch):
    def boom(vid):
        raise RuntimeError("network down")
    monkeypatch.setattr(signals, "fetch_sponsorblock", boom)
    sig = signals.build_signals(INFO, "abc12345678", None)
    assert any(f.startswith("sponsorblock_error") for f in sig["flags"])
    assert sig["sponsorblock"] == []


def test_build_signals_happy_path(monkeypatch):
    monkeypatch.setattr(signals, "fetch_sponsorblock", lambda vid: [{"start": 1.0, "end": 2.0, "category": "sponsor"}])
    sig = signals.build_signals(INFO, "abc12345678", None)
    assert sig["flags"] == []
    assert len(sig["chapters"]) == 3 and len(sig["heatmap"]) == 3
