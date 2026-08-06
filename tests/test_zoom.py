import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import zoom


def test_parse_ranges():
    r = zoom.parse_ranges("3:10-3:50@1024,12:11-12:40")
    assert r[0] == {"start": 190.0, "end": 230.0, "res": 1024}
    assert r[1]["res"] == 512


def test_plan_caps_2fps_and_20_per_range():
    ts = zoom.plan_timestamps([{"start": 0.0, "end": 5.0, "res": 512}])
    assert len(ts) == 10                       # 5초 × 2fps
    ts = zoom.plan_timestamps([{"start": 0.0, "end": 60.0, "res": 512}])
    assert len(ts) == 20                       # 구간 캡


def test_plan_global_cap_60():
    ranges = [{"start": i * 100.0, "end": i * 100.0 + 60.0, "res": 512} for i in range(5)]
    ts = zoom.plan_timestamps(ranges)          # 5구간 × 20 = 100 → 60으로 감축
    assert len(ts) <= 60
    starts = {r["start"] for r in ranges}
    covered = {min(starts, key=lambda s: abs(s - t)) for t, _ in ts}
    assert covered == starts                   # 감축돼도 모든 구간 커버 (P3)


def test_single_timestamps_mode():
    ts = zoom.parse_single("12:34@1024,0:05")
    assert ts == [(754.0, 1024), (5.0, 512)]


def test_clamp_ranges_drops_range_starting_past_duration(capsys):
    """리뷰 발견(Finding F5): 범위 시작이 이미 영상 길이를 넘으면 ffmpeg가 배치 전체를
    RuntimeError로 죽이는 대신, 그 구간만 드롭하고 사람이 보게 note를 남겨야 한다."""
    ranges = [{"start": 500.0, "end": 520.0, "res": 512}]
    out = zoom._clamp_ranges(ranges, duration=300.0)
    assert out == []
    assert "dropped" in capsys.readouterr().out


def test_clamp_ranges_clamps_end_past_duration(capsys):
    ranges = [{"start": 250.0, "end": 320.0, "res": 512}]
    out = zoom._clamp_ranges(ranges, duration=300.0)
    assert out == [{"start": 250.0, "end": 300.0, "res": 512}]
    assert "clamped" in capsys.readouterr().out


def test_clamp_ranges_noop_when_duration_unknown():
    """ffprobe 실패 등으로 duration을 모르면(<=0) 손대지 않고 그대로 통과시킨다."""
    ranges = [{"start": 250.0, "end": 320.0, "res": 512}]
    assert zoom._clamp_ranges(ranges, duration=0.0) == ranges


def test_clamp_timestamps_drops_past_duration(capsys):
    plan = [(5.0, 512), (500.0, 512)]
    out = zoom._clamp_timestamps(plan, duration=300.0)
    assert out == [(5.0, 512)]
    assert "beyond video duration" in capsys.readouterr().out


def test_dedup_plan_removes_exact_duplicate_timestamp_res_pairs():
    """리뷰 발견(Finding F9): 재확대·Q&A로 정확히 같은 (t, res) 쌍이 두 번 계획되면
    twin 파일이 dedup에서 "중복"으로 잘못 집계돼 FRAME 카운트가 부정확해진다 — 추출
    전에 정확한 float 동등성으로 한 번만 남겨야 한다."""
    plan = [(5.0, 512), (5.0, 512), (6.0, 512), (5.0, 1024)]
    out = zoom._dedup_plan(plan)
    assert out == [(5.0, 512), (5.0, 1024), (6.0, 512)]


def test_zoom_main_clamps_range_past_duration_without_crashing(synth_clip, tmp_path, monkeypatch, capsys):
    """F5 결선 검증: 실제 ffprobe로 clip(11초) 길이를 측정해, 이를 넘는 --ranges 요청이
    죽지 않고 clamp돼야 한다 (프레임 추출 자체는 목으로 대체해 빠르게 유지)."""
    cd = tmp_path / "abc12345678"
    cd.mkdir()
    (cd / "video.mp4").write_bytes(synth_clip.read_bytes())
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.frames, "extract_frames", lambda video, ts, res, out_dir: [])
    monkeypatch.setattr(zoom.frames, "dedup_frames", lambda paths, threshold=2.0: ([], 0))
    monkeypatch.setattr(zoom.sys, "argv", ["zoom.py", "abc12345678", "--ranges", "0:01-0:30"])

    code = zoom.main()

    assert code == 0
    assert "clamped" in capsys.readouterr().out


def test_timestamps_mode_skips_dedup(synth_clip, tmp_path, monkeypatch, capsys):
    """파킹 1순위 결함의 회귀 테스트: 핀포인트(--timestamps)는 명시 요청 시점이므로
    시각적 근접중복이라도 드롭하면 안 된다 — 1s/2s/3s(전부 파랑 정지)를 요청해도
    3장 모두 유지돼야 한다. (--ranges 모드의 dedup은 test_dedup_drops_static이 보증)"""
    cd = tmp_path / "abc12345678"
    cd.mkdir()
    (cd / "video.mp4").write_bytes(synth_clip.read_bytes())
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.sys, "argv", ["zoom.py", "abc12345678", "--timestamps", "0:01,0:02,0:03"])

    code = zoom.main()

    out = capsys.readouterr().out
    assert code == 0
    assert "3 kept, 0 dup-dropped" in out
