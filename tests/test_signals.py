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
    assert [f for f in sig["flags"] if not f.startswith("activity_absent")] == []
    assert len(sig["chapters"]) == 3 and len(sig["heatmap"]) == 3


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
