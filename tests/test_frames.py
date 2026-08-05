import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import frames


def test_extract_frames_names_and_count(synth_clip, tmp_path):
    out = frames.extract_frames(synth_clip, [1.0, 8.0], 512, tmp_path)
    assert len(out) == 2
    assert out[0].name == "t0001_512.jpg" and out[0].exists()
    assert out[1].name == "t0008_512.jpg"


def test_dedup_drops_static(synth_clip, tmp_path):
    # 1s,2s,3s = 전부 파랑 정지 → 2장 드롭. 8s = 빨강 → 유지
    out = frames.extract_frames(synth_clip, [1.0, 2.0, 3.0, 8.0], 512, tmp_path)
    kept, dropped = frames.dedup_frames(out)
    assert dropped == 2
    assert [p.name for p in kept] == ["t0001_512.jpg", "t0008_512.jpg"]


def test_thumb_cache_avoids_recomputation(monkeypatch, tmp_path):
    """리뷰 발견(Finding F4): _thumb()가 매 dedup_frames 호출마다 동일 경로를 재썸네일해
    (실측 2.36초/프레임) extract_map_frames의 백필 재시도 라운드에서 낭비가 컸다 — 프로세스
    내 경로별 메모이즈로 같은 경로를 다시 dedup_frames에 넣어도 새 ffmpeg 호출이 없어야
    한다."""
    calls = {"n": 0}

    def fake_run(cmd, **kw):
        calls["n"] += 1
        return subprocess.CompletedProcess(cmd, 0, stdout=b"\x01" * 256, stderr=b"")

    monkeypatch.setattr(frames.subprocess, "run", fake_run)
    frames._thumb_cache.clear()
    paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
    for p in paths:
        p.write_bytes(b"fake")

    frames.dedup_frames(paths)
    assert calls["n"] == 2                    # 최초 라운드: 프레임당 1회
    frames.dedup_frames(paths)
    assert calls["n"] == 2                    # 동일 경로 재방문 — 새 ffmpeg 호출 0회


def test_extract_frames_skips_out_of_range_timestamp(synth_clip, tmp_path):
    """리뷰 발견(Finding F5): 타임스탬프 하나가 clip 길이를 한참 넘으면 ffmpeg 실패가
    RuntimeError로 배치 전체를 중단시켜 이미 성공한 프레임까지 다 날아갔다 — 나머지
    정상 타임스탬프는 살아남아야 한다."""
    out = frames.extract_frames(synth_clip, [1.0, 9999.0], 512, tmp_path)
    assert [p.name for p in out] == ["t0001_512.jpg"]


def test_extract_frames_subsecond_timestamps_produce_distinct_files(synth_clip, tmp_path):
    """리뷰 발견(Finding F9): 5.0초/5.5초 같은 초당 다수 프레임 요청은 파일명이 정확히
    분리돼야 한다 (5.0 -> t0005, 5.5 -> t0005d5 — 데시초 접미사). 정확한 파일명까지
    고정해야 "우연히 다른 이름"(예: 반올림으로 5.5가 t0006이 되는 경우)과 구별된다."""
    out = frames.extract_frames(synth_clip, [5.0, 5.5], 512, tmp_path)
    assert [p.name for p in out] == ["t0005_512.jpg", "t0005d5_512.jpg"]


def test_report_renders_subsecond_tag_as_whole_second(capsys, tmp_path):
    p1 = tmp_path / "t0005_512.jpg"
    p2 = tmp_path / "t0005d5_512.jpg"
    p1.write_bytes(b"x")
    p2.write_bytes(b"x")
    frames.report([p1, p2])
    lines = [l for l in capsys.readouterr().out.splitlines() if l.startswith("FRAME")]
    assert len(lines) == 2
    # 정확히 "t=00:05"로 끝나야 한다 — 데시초 접미사가 안 지워지면 "t=00:05:d5"처럼 뒤에
    # 더 붙어, 느슨한 substring 검사("t=00:05" in line)로는 이 버그를 못 잡는다.
    assert all(l.endswith("t=00:05") for l in lines)
