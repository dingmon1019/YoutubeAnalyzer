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
    ranges = [{"start": 250.0, "end": 320.0, "res": 512}]
    assert zoom._clamp_ranges(ranges, duration=0.0) == ranges


def test_clamp_timestamps_drops_past_duration(capsys):
    plan = [(5.0, 512), (500.0, 512)]
    out = zoom._clamp_timestamps(plan, duration=300.0)
    assert out == [(5.0, 512)]
    assert "beyond video duration" in capsys.readouterr().out


def test_dedup_plan_removes_exact_duplicate_timestamp_res_pairs():
    plan = [(5.0, 512), (5.0, 512), (6.0, 512), (5.0, 1024)]
    out = zoom._dedup_plan(plan)
    assert out == [(5.0, 512), (5.0, 1024), (6.0, 512)]


def test_zoom_main_clamps_range_past_duration_without_crashing(synth_clip, tmp_path, monkeypatch, capsys):
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
    cd = tmp_path / "abc12345678"
    cd.mkdir()
    (cd / "video.mp4").write_bytes(synth_clip.read_bytes())
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.sys, "argv", ["zoom.py", "abc12345678", "--timestamps", "0:01,0:02,0:03"])

    code = zoom.main()

    out = capsys.readouterr().out
    assert code == 0
    assert "3 kept, 0 dup-dropped" in out


def test_ranges_with_timestamps_argument_still_dedups(tmp_path, monkeypatch, capsys):
    """회귀 테스트: --ranges와 --timestamps를 동시에 제공하면 --ranges가 우선되므로
    (if/elif 순서), pinpoint 플래그가 False여야 하고 dedup이 실행돼야 한다."""
    cd = tmp_path / "test123"
    cd.mkdir()
    (cd / "video.mp4").write_bytes(b'' * 1000)
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    call_record = []
    
    def mock_extract_frames(video, ts, res, out_dir):
        return [type('Path', (), {'name': f't{i:04d}_{res}.jpg'})() for i in range(len(ts))]
    
    def mock_dedup_frames(paths, threshold=2.0):
        call_record.append('dedup_called')
        return paths[:1], len(paths) - 1
    
    monkeypatch.setattr(zoom.frames, "extract_frames", mock_extract_frames)
    monkeypatch.setattr(zoom.frames, "dedup_frames", mock_dedup_frames)
    monkeypatch.setattr(zoom.sys, "argv", ["zoom.py", "test123", "--ranges", "0:01-0:05", "--timestamps", "0:02"])
    
    code = zoom.main()
    
    out = capsys.readouterr().out
    assert code == 0
    assert 'dedup_called' in call_record
    assert 'dup-dropped' in out
