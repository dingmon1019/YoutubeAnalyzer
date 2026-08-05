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


def test_allocate_zero_duration_returns_empty():
    assert analyze.allocate_map_budget(0.0, SIG) == []


def test_allocate_short_video_respects_invariants():
    ts = sorted(analyze.allocate_map_budget(10.0, SIG))
    assert all(0 <= t <= 10.0 for t in ts)
    n = min(40, max(12, round(10.0 / 60 * 1.2)))
    min_gap = max(8.0, 10.0 / n / 2)
    assert all(b - a >= min_gap * 0.99 for a, b in zip(ts, ts[1:]))
    assert len(ts) >= 1  # at least the start anchor survives


def test_allocate_normal_duration_unchanged():
    ts = analyze.allocate_map_budget(1800.0, SIG)
    assert len(ts) == 36
    assert any(abs(t - 1.0) < 0.5 for t in ts) and any(abs(t - 1798.0) < 1 for t in ts)


# 실제 L3 관측(PlMpk-If9jA, 352초)과 동형의 후보 밀도 재현용 — SIG(900/1800초 기준 픽스처)는
# 이 길이에서 sponsorblock/챕터 배치상 후보가 자연히 12 미만으로 소진돼 전제조건이 안 맞는다.
# 활동 피크가 촘촘하면(예: 7초 간격) extra 요청이 활동 신호만으로 채워져 그리드까지 안 간다.
RICH_SIG = {
    "chapters": [], "heatmap": [], "sponsorblock": [],
    "activity": {"curve": [], "peaks": list(range(5, 352, 7))},
}

# PlMpk-If9jA 실측 활동 피크(0:15~4:27 구간에 편중, 7개뿐) — 신호가 성긴 실제 케이스 재현.
# 이 픽스처에서는 활동 신호만으론 12개를 못 채워 그리드가 개입하고, extra 보강도 오직 그리드
# 후보(범위 전체를 target 기준으로 재생성)로만 가능하다 — "그리드도 target에 맞춰 촘촘해져야
# 한다"는 것 자체가 검증 대상이다 (n 고정 그리드였을 때는 extra=1을 줘도 12->12로 안 자랐다).
CLUSTERED_SIG = {
    "chapters": [], "heatmap": [], "sponsorblock": [],
    "activity": {"curve": [], "peaks": [15, 87, 140, 151, 178, 231, 267]},
}


def test_sub_langs_for_widens_regional_code_to_base():
    """실측(YKSpANU8jPE): info['language']='en-US'인데 automatic_captions 키는 'en'/'en-orig'
    뿐이라, exact-match인 --sub-langs가 'en-US,en-US-orig'만 요청하면 조용히 0건 매치되어
    자막 사슬 전체가 local whisper로 새버렸다 — captions(en)이어야 할 STATUS가 local()로 나옴."""
    langs = analyze._sub_langs_for("en-US").split(",")
    assert "en" in langs
    assert "en-orig" in langs


def test_sub_langs_for_plain_code_unchanged_shape():
    assert set(analyze._sub_langs_for("ko").split(",")) == {"ko", "ko-orig"}


def test_sub_langs_for_missing_language_falls_back():
    assert analyze._sub_langs_for(None) == "ko,en"
    assert analyze._sub_langs_for("") == "ko,en"


def test_allocate_extra_grows_pool_when_activity_signal_is_rich():
    base = analyze.allocate_map_budget(352.0, RICH_SIG)
    grown = analyze.allocate_map_budget(352.0, RICH_SIG, extra=1)
    assert len(grown) == len(base) + 1
    assert set(base) <= set(grown)


def test_allocate_extra_grows_pool_via_grid_when_signal_is_sparse():
    """그리드가 n 고정이면(수정 전) 활동피크가 몰린 실제 영상에서 extra가 후보를 못 늘려
    12->12로 정체했다 — PASS1 실측(PlMpk-If9jA)에서 map_frames가 11로 보고된 근본 원인."""
    base = analyze.allocate_map_budget(352.0, CLUSTERED_SIG)
    assert len(base) == 12
    grown = analyze.allocate_map_budget(352.0, CLUSTERED_SIG, extra=1)
    assert len(grown) > len(base)


def test_extract_map_frames_backfills_when_dedup_drops_below_floor(monkeypatch, tmp_path):
    """실제 관측(L3, PASS1 실행 — PlMpk-If9jA): allocate_map_budget의 floor(짧은 영상=12)가
    dedup으로 깎였을 때(t0550이 t0508과 근접중복이라 dropped) 그대로 11장으로 보고되던 버그.
    CLUSTERED_SIG는 그 영상의 실측 활동피크 그대로라 그리드 보강 경로까지 실제로 탄다."""
    duration = 352.0
    target = len(analyze.allocate_map_budget(duration, CLUSTERED_SIG))
    assert target == 12  # 이 케이스의 전제 조건(짧은 영상 floor) — 깨지면 테스트 자체를 재검토

    def fake_extract(video, timestamps, res, out_dir):
        return [Path(f"t{t:.2f}") for t in timestamps]

    def fake_dedup(paths, threshold=2.0):
        # 시간순으로 정렬된 리스트의 두 번째 프레임을 항상 근접중복으로 취급해
        # "정확히 1장 드롭"을 재현 가능하게 시뮬레이션한다 (실제 t0550 케이스와 동형).
        if len(paths) < 2:
            return paths, 0
        kept = [paths[0]] + paths[2:]
        return kept, len(paths) - len(kept)

    monkeypatch.setattr(analyze.frames, "extract_frames", fake_extract)
    monkeypatch.setattr(analyze.frames, "dedup_frames", fake_dedup)

    kept, dropped = analyze.extract_map_frames(Path("video.mp4"), duration, CLUSTERED_SIG, tmp_path)
    assert len(kept) >= target


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
