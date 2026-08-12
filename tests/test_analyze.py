import json
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


def test_sub_langs_for_picks_ko_from_subtitles_when_language_missing():
    """리뷰 발견(Finding F2): info['language']가 비어 있으면(일부 영상은 이 필드 자체가
    없다) 기존엔 무조건 "ko,en"을 요청해 두 트랙이 다 있는 한국어 영상에서도 영어
    자동번역이 섞여 들어올 수 있었다 — 실제 트랙 목록을 먼저 봐야 한다."""
    info = {"subtitles": {"ko": [{"ext": "vtt"}]}}
    assert analyze._sub_langs_for(None, info) == "ko,ko-orig"


def test_sub_langs_for_prefers_en_when_ko_absent_from_subtitles():
    info = {"subtitles": {"en": [{"ext": "vtt"}], "fr": [{"ext": "vtt"}]}}
    assert analyze._sub_langs_for(None, info) == "en,en-orig"


def test_sub_langs_for_falls_back_to_automatic_captions_when_subtitles_empty():
    info = {"subtitles": {}, "automatic_captions": {"ko": [{"ext": "vtt"}], "fr": [{"ext": "vtt"}]}}
    assert analyze._sub_langs_for(None, info) == "ko,ko-orig"


def test_sub_langs_for_skips_hyphenated_keys_and_picks_first_remaining():
    info = {"subtitles": {"fr-orig": [{"ext": "vtt"}], "de": [{"ext": "vtt"}], "fr": [{"ext": "vtt"}]}}
    assert analyze._sub_langs_for(None, info) == "de,de-orig"


def test_sub_langs_for_no_info_still_falls_back():
    assert analyze._sub_langs_for(None, None) == "ko,en"


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


def test_extract_map_frames_keeps_best_round_when_later_round_is_worse(monkeypatch, tmp_path):
    """리뷰 발견(Finding 1): 백필 라운드가 항상 더 나은 결과라는 보장은 없다 — 그리드가
    target마다 재생성되므로 상위집합이 아니다(실측: EMPTY_SIG에서 extra=1 시 superset=False
    확인됨). 그리드가 더 촘촘해질수록 인접 후보끼리 시각적으로 더 비슷해지기 쉬워, 나중
    라운드가 오히려 dedup에서 더 많이 깎일 수 있다. best-so-far를 추적하지 않으면
    라운드1(11장)보다 못한 라운드2(9장)가 최종값으로 나가버린다."""
    duration = 352.0
    target = len(analyze.allocate_map_budget(duration, CLUSTERED_SIG))
    assert target == 12  # 이 케이스의 전제 조건 — 깨지면 테스트 자체를 재검토

    def fake_extract(video, timestamps, res, out_dir):
        return [Path(f"t{t:.2f}") for t in timestamps]

    calls = {"n": 0}

    def fake_dedup(paths, threshold=2.0):
        calls["n"] += 1
        if calls["n"] == 1:
            kept = paths[:11]           # 라운드1: 12 -> 11 (실측 t0550 케이스와 동형)
        else:
            kept = paths[:9]            # 이후 라운드: 후보가 늘었는데도 오히려 9로 퇴보
        return kept, len(paths) - len(kept)

    monkeypatch.setattr(analyze.frames, "extract_frames", fake_extract)
    monkeypatch.setattr(analyze.frames, "dedup_frames", fake_dedup)

    kept, dropped = analyze.extract_map_frames(Path("video.mp4"), duration, CLUSTERED_SIG, tmp_path)
    assert len(kept) == 11  # 라운드1(더 나은 결과)이 유지돼야 함 — 라운드2의 9로 퇴보 금지


def test_allocate_extra_never_exceeds_spec_ceiling():
    """리뷰 발견(Finding 2): target = n + extra에 40 상한을 다시 걸지 않으면, n이 이미
    40인 긴 영상에서 backfill이 41 -> 50 -> 75 ...로 발산해 스펙(§3.3)의 지도 예산 상한
    min(40, ...)을 조용히 깬다 (실측: extra=1000 -> len=75)."""
    dense = {
        "chapters": [], "heatmap": [], "sponsorblock": [],
        "activity": {"curve": [], "peaks": list(range(5, 2000, 3))},
    }
    assert len(analyze.allocate_map_budget(2000.0, dense)) == 40  # 전제조건: n=40(상한)
    for extra in (0, 1, 10, 100, 1000):
        assert len(analyze.allocate_map_budget(2000.0, dense, extra=extra)) <= 40


def test_extract_map_frames_caps_target_at_40_for_long_video(monkeypatch, tmp_path):
    """리뷰 발견(Finding 2): n이 이미 스펙 상한(40)인 긴 영상에서 dedup이 매 라운드
    계속 깎아내도(정적인 영상 시뮬레이션: 매번 5장만 생존) target이 40을 넘는 요청을
    하면 안 되고, 루프도 유한 회 안에 종료돼야 한다(더 늘 후보가 없으면 즉시 멈춤)."""
    duration = 2000.0
    dense = {
        "chapters": [], "heatmap": [], "sponsorblock": [],
        "activity": {"curve": [], "peaks": list(range(5, 2000, 3))},
    }
    assert len(analyze.allocate_map_budget(duration, dense)) == 40  # 전제조건

    requested_counts = []

    def fake_extract(video, timestamps, res, out_dir):
        requested_counts.append(len(timestamps))
        return [Path(f"t{t:.2f}") for t in timestamps]

    def fake_dedup(paths, threshold=2.0):
        kept = paths[:5]            # 정적인 긴 영상: 매 라운드 5장만 생존
        return kept, len(paths) - len(kept)

    monkeypatch.setattr(analyze.frames, "extract_frames", fake_extract)
    monkeypatch.setattr(analyze.frames, "dedup_frames", fake_dedup)

    kept, dropped = analyze.extract_map_frames(Path("video.mp4"), duration, dense, tmp_path)
    assert all(c <= 40 for c in requested_counts)   # 어떤 라운드도 40장 초과 요청 안 함
    assert len(kept) == 5                            # best-so-far — 상한에 막혀 더는 못 늘어남


def _stub_pass1_deps(monkeypatch, transcript_text):
    """run_pass1의 외부 I/O 경계(다운로드·신호·자막·지도 프레임·LRU)를 전부 대체해,
    순수 오케스트레이션 로직(WARNING 출력 등)만 네트워크/ffmpeg 없이 검증 가능하게 한다."""
    monkeypatch.setattr(analyze, "download", lambda url, cd: {"duration": 600, "id": "vid"})
    monkeypatch.setattr(analyze.sig_mod, "build_signals", lambda info, vid, path: {
        "chapters": [], "heatmap": [], "sponsorblock": [], "desc_timestamps": [],
        "activity": {"curve": [], "peaks": []}, "flags": [],
    })
    segs = [{"start": 0, "end": 1, "text": transcript_text}] if transcript_text else []
    monkeypatch.setattr(analyze.transcribe, "get_transcript", lambda cd, mode: {
        "source": "captions", "lang": "ko", "segments": segs, "flags": [], "dupes_removed": 0,
    })
    monkeypatch.setattr(analyze, "extract_map_frames", lambda *a, **kw: ([], 0))
    monkeypatch.setattr(analyze, "lru_evict", lambda: [])


def test_run_pass1_warns_on_large_transcript(tmp_path, monkeypatch, capsys):
    """리뷰 발견(Finding F3): 토큰 예산(§3.3, 패스1 자막 ~15k) 약속이 코드에서 강제되지
    않는다. v1은 자동 압축하지 않되(fail-loud), 최소한 큰 자막에 대해 경고는 해야 한다."""
    monkeypatch.setattr(analyze.common, "CACHE_ROOT", tmp_path)
    _stub_pass1_deps(monkeypatch, "x" * 31000)
    analyze.run_pass1("https://youtu.be/dQw4w9WgXcQ")
    out = capsys.readouterr().out
    assert "WARNING: transcript large" in out


def test_run_pass1_no_warning_when_transcript_small(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(analyze.common, "CACHE_ROOT", tmp_path)
    _stub_pass1_deps(monkeypatch, "x" * 100)
    analyze.run_pass1("https://youtu.be/dQw4w9WgXcQ")
    out = capsys.readouterr().out
    assert "WARNING: transcript large" not in out


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


def test_signals_reused_when_fresh(tmp_path, monkeypatch):
    """signals.json이 video.mp4보다 새로우면 활동곡선(전체 영상 디코드) 재계산 없이
    재사용해야 한다 — 캐시 히트 재실행 102초의 원인 제거."""
    import os
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    sigf = tmp_path / "signals.json"
    sigf.write_text('{"activity": {"curve": [], "peaks": []}, "flags": ["reused"]}', encoding="utf-8")
    os.utime(video, (1000, 1000))
    os.utime(sigf, (2000, 2000))

    def boom(*a, **k):
        raise AssertionError("build_signals가 호출되면 안 된다")

    monkeypatch.setattr(analyze.sig_mod, "build_signals", boom)
    sig = analyze._load_or_build_signals(tmp_path, {}, "vid")
    assert sig["flags"] == ["reused"]


def test_signals_rebuilt_when_video_newer(tmp_path, monkeypatch):
    """video.mp4가 더 새로우면(eviction 후 재다운로드) 재계산하고 파일을 갱신해야 한다."""
    import json
    import os
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    sigf = tmp_path / "signals.json"
    sigf.write_text('{"activity": {"curve": [], "peaks": []}, "flags": ["stale"]}', encoding="utf-8")
    os.utime(sigf, (1000, 1000))
    os.utime(video, (2000, 2000))

    fresh = {"activity": {"curve": [], "peaks": []}, "flags": ["fresh"]}
    monkeypatch.setattr(analyze.sig_mod, "build_signals", lambda *a: fresh)
    sig = analyze._load_or_build_signals(tmp_path, {}, "vid")
    assert sig["flags"] == ["fresh"]
    assert json.loads(sigf.read_text(encoding="utf-8"))["flags"] == ["fresh"]


def test_signals_rebuilt_when_corrupt(tmp_path, monkeypatch):
    """mtime이 새로워도 파손·비정형 JSON이면 재계산한다."""
    import os
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    sigf = tmp_path / "signals.json"
    sigf.write_text("{broken", encoding="utf-8")
    os.utime(video, (1000, 1000))
    os.utime(sigf, (2000, 2000))

    fresh = {"activity": {"curve": [], "peaks": []}, "flags": []}
    monkeypatch.setattr(analyze.sig_mod, "build_signals", lambda *a: fresh)
    assert analyze._load_or_build_signals(tmp_path, {}, "vid") == fresh


def test_run_pass1_writes_evidence_skeleton(monkeypatch, tmp_path, capsys):
    """패스1이 끝나면 evidence.json 골격이 캐시에 남고 == EVIDENCE == 줄로 경로를 알린다.

    무거운 단계(다운로드·자막·프레임 추출)는 전부 대역으로 바꾸고, 이 테스트가 보는 것은
    '골격이 실제로 저장되는가'와 '보고서가 경로를 알리는가' 두 가지뿐이다."""
    cd = tmp_path / "cache" / "abc12345678"
    cd.mkdir(parents=True)
    info = {"id": "abc12345678", "title": "T", "duration": 120.0, "uploader": "C"}
    sig = {"heatmap": [], "chapters": [], "desc_timestamps": [], "sponsorblock": [],
           "activity": {"curve": [], "peaks": []}, "flags": []}
    tr = {"source": "captions", "lang": "ko", "dupes_removed": 0, "flags": [],
          "segments": [{"start": 0.0, "text": "hi"}]}

    monkeypatch.setattr(analyze.common, "cache_dir", lambda vid: cd)
    monkeypatch.setattr(analyze, "download", lambda url, c: info)
    monkeypatch.setattr(analyze, "_load_or_build_signals", lambda c, i, v: sig)
    monkeypatch.setattr(analyze.transcribe, "get_transcript", lambda c, mode="auto": tr)
    monkeypatch.setattr(analyze, "extract_map_frames", lambda *a, **k: ([], 0))
    monkeypatch.setattr(analyze, "lru_evict", lambda: [])

    rc = analyze.run_pass1("https://youtu.be/abc12345678")
    assert rc == 0

    ev_file = cd / "evidence.json"
    assert ev_file.exists(), "evidence.json이 저장되지 않았다"
    ev = json.loads(ev_file.read_text(encoding="utf-8"))
    assert ev["schema_version"] == "0.2"
    assert ev["video"]["id"] == "abc12345678"
    assert ev["segments"][0]["transcript"] == "hi"

    out = capsys.readouterr().out
    assert "== EVIDENCE ==" in out
    assert "EVIDENCE_FILE" in out
    assert "TYPE_HINT" in out
