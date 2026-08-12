import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import evidence

SCRIPT = Path(__file__).parent.parent / "skills" / "tuto" / "scripts" / "evidence.py"


def _info():
    return {"id": "abc12345678", "title": "Test Video", "duration": 300.0,
            "uploader": "Ch", "webpage_url": "https://youtu.be/abc12345678"}


def _sig():
    return {"heatmap": [{"start": 10.0, "end": 12.0, "value": 1.0}],
            "chapters": [{"start": 0.0, "title": "Intro"}],
            "desc_timestamps": [], "sponsorblock": [],
            "activity": {"curve": [0.0, 1.0], "peaks": [11]},
            "flags": ["heatmap_absent"]}


def _tr():
    return {"source": "captions", "lang": "ko", "dupes_removed": 3, "flags": [],
            "segments": [{"start": 0.0, "text": "안녕하세요"},
                         {"start": 5.0, "text": "시작합니다"}]}


def _skel():
    return evidence.build_skeleton(_info(), _sig(), _tr(), [], "https://youtu.be/abc12345678")


def _run(args):
    return subprocess.run([sys.executable, str(SCRIPT)] + args,
                          capture_output=True, text=True, encoding="utf-8")


# ── 골격 ───────────────────────────────────────────────────────────────────

def test_skeleton_has_required_top_level_keys():
    ev = _skel()
    for key in ("schema_version", "video", "video_type", "provenance",
                "segments", "visual_evidence", "claims", "gaps", "flags"):
        assert key in ev, f"missing {key}"
    assert ev["schema_version"] == evidence.SCHEMA_VERSION


def test_skeleton_video_block():
    ev = _skel()
    assert ev["video"]["id"] == "abc12345678"
    assert ev["video"]["title"] == "Test Video"
    assert ev["video"]["duration"] == 300.0
    assert ev["video"]["url"] == "https://youtu.be/abc12345678"
    assert ev["video"]["channel"] == "Ch"


def test_skeleton_segments_get_end_from_next_start():
    segs = _skel()["segments"]
    assert len(segs) == 2
    assert segs[0]["start"] == 0.0 and segs[0]["end"] == 5.0
    assert segs[0]["transcript"] == "안녕하세요"
    assert segs[1]["end"] == 300.0          # 마지막은 영상 길이로 닫는다


def test_skeleton_llm_slots_start_empty():
    ev = _skel()
    assert ev["visual_evidence"] == []
    assert ev["claims"] == []
    assert ev["video_type"]["primary"] == "unknown"


def test_skeleton_provenance_records_transcript_and_signals():
    p = _skel()["provenance"]
    assert p["transcript"]["source"] == "captions"
    assert p["transcript"]["lang"] == "ko"
    assert p["transcript"]["segments"] == 2
    assert p["transcript"]["dupes_removed"] == 3
    assert p["signals"]["chapters"] == 1
    assert p["signals"]["activity_peaks"] == 1
    assert "heatmap_absent" in p["signals"]["flags"]


def test_skeleton_frames_carry_timestamp_and_resolution(tmp_path):
    f = tmp_path / "t0132_1024.jpg"
    f.write_bytes(b"x")
    frames = evidence.build_skeleton(_info(), _sig(), _tr(), [f], "u")["provenance"]["frames"]["map"]
    assert len(frames) == 1
    assert frames[0]["t"] == 92.0           # t0132 -> 1:32
    assert frames[0]["res"] == 1024
    assert frames[0]["file"] == "t0132_1024.jpg"


def test_frame_meta_handles_deci_and_crop_and_hour_long_names():
    """파일명 규약 3종: 데시초 접미사, 크롭 접미사, 1시간 초과 태그."""
    assert evidence._frame_meta("t0312d5_512.jpg")["t"] == 192.0
    crop = evidence._frame_meta("t0618d4_1024c10_200_400_120.jpg")
    assert crop["t"] == 378.0 and crop["res"] == 1024 and crop["crop"] is True
    assert evidence._frame_meta("t10203_512.jpg")["t"] == 3723.0   # 1:02:03


def test_frame_meta_keeps_filename_on_unknown_pattern():
    m = evidence._frame_meta("weird-name.png")
    assert m["file"] == "weird-name.png"
    assert m["res"] is None


# ── 병합 ───────────────────────────────────────────────────────────────────

def test_merge_adds_visual_evidence_and_assigns_ids():
    ev = evidence.merge(_skel(), {"visual_evidence": [
        {"type": "slide", "value": "16.3x", "timestamp": 132.0,
         "frame": "t0212_1024.jpg", "confidence": "high"}]})
    assert len(ev["visual_evidence"]) == 1
    assert ev["visual_evidence"][0]["id"] == "v1"


def test_merge_is_append_not_replace():
    ev = _skel()
    ev = evidence.merge(ev, {"visual_evidence": [
        {"type": "slide", "value": "a", "timestamp": 1.0, "frame": "f", "confidence": "high"}]})
    ev = evidence.merge(ev, {"visual_evidence": [
        {"type": "chart", "value": "b", "timestamp": 2.0, "frame": "g", "confidence": "low"}]})
    assert [v["id"] for v in ev["visual_evidence"]] == ["v1", "v2"]


def test_merge_claims_and_video_type():
    ev = evidence.merge(_skel(), {
        "video_type": {"primary": "presentation", "confidence": "high", "basis": "slides"},
        "claims": [{"claim": "성능이 16.3배 향상", "timestamp": 132.0,
                    "evidence": [{"source": "transcript", "ref": "0"}],
                    "verification": {"status": "unaudited"}}]})
    assert ev["video_type"]["primary"] == "presentation"
    assert ev["claims"][0]["id"] == "c1"


def test_merge_defaults_claim_verification_to_unaudited():
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "transcript", "ref": "0"}]}]})
    assert ev["claims"][0]["verification"]["status"] == "unaudited"


def test_merge_video_type_preserves_hint():
    ev = evidence.merge(_skel(), {"video_type": {"primary": "lecture", "confidence": "medium"}})
    assert "hint" in ev["video_type"]


def test_apply_verdicts_updates_status_and_flags_orphans():
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "transcript", "ref": "0"}]}]})
    ev = evidence.apply_verdicts(ev, [
        {"claim_id": "c1", "status": "verified", "auditor": "sonnet"},
        {"claim_id": "c9", "status": "disputed"}])
    assert ev["claims"][0]["verification"]["status"] == "verified"
    assert any("verdict_orphan: c9" in f for f in ev["flags"])


# ── 검증 ───────────────────────────────────────────────────────────────────

def test_validate_passes_on_clean_skeleton():
    assert evidence.validate(_skel()) == []


def test_validate_rejects_unknown_evidence_type():
    ev = evidence.merge(_skel(), {"visual_evidence": [
        {"type": "hologram", "value": "x", "timestamp": 1.0, "frame": "f",
         "confidence": "high"}]})
    assert any("hologram" in e for e in evidence.validate(ev))


def test_validate_rejects_numeric_confidence():
    ev = evidence.merge(_skel(), {"visual_evidence": [
        {"type": "slide", "value": "x", "timestamp": 1.0, "frame": "f", "confidence": 0.87}]})
    assert any("confidence" in e for e in evidence.validate(ev))


def test_validate_rejects_visual_evidence_without_frame():
    ev = evidence.merge(_skel(), {"visual_evidence": [
        {"type": "slide", "value": "x", "timestamp": 1.0, "frame": "", "confidence": "high"}]})
    assert any("frame" in e for e in evidence.validate(ev))


def test_validate_rejects_claim_referencing_missing_visual_evidence():
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "frame", "ref": "v99"}]}]})
    assert any("v99" in e for e in evidence.validate(ev))


def test_validate_rejects_source_both():
    """'both'를 허용하면 화면 근거가 없는데도 있다고 주장하는 게 통과한다."""
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "both", "ref": "v1"}]}]})
    assert any("both" in e for e in evidence.validate(ev))


def test_validate_rejects_empty_ref():
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "transcript", "ref": ""}]}]})
    assert any("ref" in e for e in evidence.validate(ev))


def test_validate_rejects_claim_without_evidence():
    ev = evidence.merge(_skel(), {"claims": [{"claim": "x", "timestamp": 1.0, "evidence": []}]})
    assert any("evidence" in e for e in evidence.validate(ev))


def test_validate_rejects_unknown_verification_status():
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "transcript", "ref": "0"}],
         "verification": {"status": "probably-true"}}]})
    assert any("probably-true" in e for e in evidence.validate(ev))


def test_validate_accepts_split_transcript_and_frame_evidence():
    """양쪽 근거는 두 항목으로 나눠 적으면 통과한다."""
    ev = evidence.merge(_skel(), {
        "visual_evidence": [{"type": "chart", "value": "16.3x", "timestamp": 132.0,
                             "frame": "t0212_1024.jpg", "confidence": "high"}],
        "claims": [{"claim": "16.3배", "timestamp": 132.0,
                    "evidence": [{"source": "frame", "ref": "v1"},
                                 {"source": "transcript", "ref": "0"}],
                    "conflict": {"transcript": "16배", "screen": "16.3x"}}]})
    assert evidence.validate(ev) == []
    assert ev["claims"][0]["conflict"]["screen"] == "16.3x"


# ── 분류 힌트 ──────────────────────────────────────────────────────────────

def test_classify_hint_dense_chapters_suggests_lecture_or_presentation():
    sig = _sig()
    sig["chapters"] = [{"start": float(i * 60), "title": f"c{i}"} for i in range(11)]
    tr = _tr()
    tr["segments"] = [{"start": float(i), "text": "말" * 20} for i in range(600)]
    h = evidence.classify_hint(sig, tr, 1200.0)
    assert "presentation" in h["candidates"] or "lecture" in h["candidates"]
    assert h["basis"]


def test_classify_hint_no_transcript_suggests_screen_recording():
    tr = {"source": "none", "lang": "", "segments": [], "dupes_removed": 0, "flags": []}
    assert "screen-recording" in evidence.classify_hint(_sig(), tr, 300.0)["candidates"]


def test_classify_hint_never_returns_value_outside_enum():
    h = evidence.classify_hint(_sig(), _tr(), 300.0)
    assert all(c in evidence.VIDEO_TYPES for c in h["candidates"])


def test_classify_hint_handles_zero_duration():
    assert evidence.classify_hint(_sig(), _tr(), 0.0)["candidates"]


# ── CLI ────────────────────────────────────────────────────────────────────

def test_cli_errors_when_evidence_missing(tmp_path):
    p = _run([str(tmp_path), "--validate"])
    assert p.returncode == 2
    assert "analyze.py" in p.stderr


def test_cli_validate_exit_zero_on_clean(tmp_path):
    evidence.save(tmp_path, _skel())
    assert _run([str(tmp_path), "--validate"]).returncode == 0


def test_cli_validate_exit_two_and_prints_errors(tmp_path):
    ev = evidence.merge(_skel(), {"visual_evidence": [
        {"type": "hologram", "value": "x", "timestamp": 1.0, "frame": "f",
         "confidence": "high"}]})
    evidence.save(tmp_path, ev)
    p = _run([str(tmp_path), "--validate"])
    assert p.returncode == 2
    assert "hologram" in (p.stdout + p.stderr)


def test_cli_merge_applies_patch(tmp_path):
    evidence.save(tmp_path, _skel())
    patch = tmp_path / "patch.json"
    patch.write_text(json.dumps({"visual_evidence": [
        {"type": "chart", "value": "16.3x", "timestamp": 132.0,
         "frame": "t0212_1024.jpg", "confidence": "high"}]}), encoding="utf-8")
    p = _run([str(tmp_path), "--merge", str(patch)])
    assert p.returncode == 0, p.stderr
    assert evidence.load(tmp_path)["visual_evidence"][0]["value"] == "16.3x"


def test_cli_merge_rejects_invalid_patch_with_exit_two(tmp_path):
    evidence.save(tmp_path, _skel())
    patch = tmp_path / "bad.json"
    patch.write_text(json.dumps({"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "frame", "ref": "v42"}]}]}),
        encoding="utf-8")
    p = _run([str(tmp_path), "--merge", str(patch)])
    assert p.returncode == 2
    assert "v42" in p.stderr


def test_cli_summary_prints_counts(tmp_path):
    evidence.save(tmp_path, _skel())
    p = _run([str(tmp_path), "--summary"])
    assert p.returncode == 0
    assert "segments=2" in p.stdout


def test_save_and_load_roundtrip(tmp_path):
    p = evidence.save(tmp_path, _skel())
    assert p.exists()
    assert evidence.load(tmp_path)["video"]["id"] == "abc12345678"
