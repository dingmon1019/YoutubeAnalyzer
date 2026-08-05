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
