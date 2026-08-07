import sys
import subprocess
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


def test_ranges_with_timestamps_argument_still_dedups(tmp_path, monkeypatch, capsys):
    """회귀 테스트: --ranges와 --timestamps를 동시에 제공하면 --ranges가 우선되므로
    (if/elif 순서), pinpoint 플래그가 False여야 하고 dedup이 실행돼야 한다."""
    cd = tmp_path / "test123"
    cd.mkdir()
    (cd / "video.mp4").write_bytes(b"\0" * 1000)
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


def test_zoom_report_emits_ocrtxt_after_frames(synth_clip, tmp_path, monkeypatch, capsys):
    """zoom 보고서 계약: FRAME 라인 뒤에 OCRTXT 라인 — 판독 텍스트가 판정자에게 전달된다."""
    cd = tmp_path / "abc12345678"
    cd.mkdir()
    (cd / "video.mp4").write_bytes(synth_clip.read_bytes())
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.ocr, "extract_batch",
                        lambda paths: {p: "파랑 화면" for p in paths})
    monkeypatch.setattr(zoom.sys, "argv", ["zoom.py", "abc12345678", "--timestamps", "0:01"])
    assert zoom.main() == 0
    out = capsys.readouterr().out
    assert out.index("FRAME ") < out.index("OCRTXT t=00:01: 파랑 화면")


def test_crop_mode_crops_existing_frame_without_video(synth_clip, tmp_path, monkeypatch, capsys):
    """크롭 모드: 기존 프레임에서 ffmpeg crop — video.mp4가 없어도(eviction 후) 동작해야 한다."""
    cd = tmp_path / "abc12345678"
    (cd / "frames").mkdir(parents=True)
    src = cd / "frames" / "t0618_1024.jpg"
    subprocess.run(["ffmpeg", "-y", "-ss", "1", "-i", str(synth_clip),
                    "-frames:v", "1", "-vf", "scale=1024:-2", str(src)],
                   capture_output=True, check=True)
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.sys, "argv",
                        ["zoom.py", "abc12345678", "--crop", "t0618_1024.jpg@100,50,300,200"])
    assert zoom.main() == 0
    out = capsys.readouterr().out
    assert "t0618_1024c100_50_300_200.jpg" in out and "FRAME" in out


def test_crop_mode_missing_source_fails_loud(tmp_path, monkeypatch, capsys):
    cd = tmp_path / "abc12345678"
    (cd / "frames").mkdir(parents=True)
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.sys, "argv",
                        ["zoom.py", "abc12345678", "--crop", "없는파일.jpg@0,0,10,10"])
    assert zoom.main() == 1
    assert "ERROR" in capsys.readouterr().err


def test_crop_mode_multi_spec_success(synth_clip, tmp_path, monkeypatch, capsys):
    """다중 크롭 스펙: 쉼표로 구분된 여러 파일을 한 번에 크롭한다."""
    cd = tmp_path / "abc12345678"
    (cd / "frames").mkdir(parents=True)
    # 첫 번째 프레임
    src1 = cd / "frames" / "t0618_1024.jpg"
    subprocess.run(["ffmpeg", "-y", "-ss", "1", "-i", str(synth_clip),
                    "-frames:v", "1", "-vf", "scale=1024:-2", str(src1)],
                   capture_output=True, check=True)
    # 두 번째 프레임
    src2 = cd / "frames" / "t1200_512.jpg"
    subprocess.run(["ffmpeg", "-y", "-ss", "3", "-i", str(synth_clip),
                    "-frames:v", "1", "-vf", "scale=512:-2", str(src2)],
                   capture_output=True, check=True)
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.sys, "argv",
                        ["zoom.py", "abc12345678", "--crop", "t0618_1024.jpg@100,50,300,200,t1200_512.jpg@10,10,40,40"])
    assert zoom.main() == 0
    out = capsys.readouterr().out
    assert "2 cropped" in out
    assert "t0618_1024c100_50_300_200.jpg" in out
    assert "t1200_512c10_10_40_40.jpg" in out


def test_crop_mode_malformed_input_fails_loud(tmp_path, monkeypatch, capsys):
    """형식 오류: 잘못된 --crop 형식(comma 개수 오류 등)은 exit 1 + stderr ERROR."""
    cd = tmp_path / "abc12345678"
    (cd / "frames").mkdir(parents=True)
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.sys, "argv",
                        ["zoom.py", "abc12345678", "--crop", "t0618_1024.jpg@abc"])
    assert zoom.main() == 1
    assert "ERROR" in capsys.readouterr().err
