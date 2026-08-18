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
        "zoom_frames": ["t0212_1024.jpg"],
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
    patch.write_text(json.dumps({
        "zoom_frames": ["t0212_1024.jpg"],
        "visual_evidence": [
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


# ── 원자성: 검증 실패 시 저장하지 않는다 ──────────────────────────────────

def test_cli_merge_does_not_persist_invalid_patch(tmp_path):
    """거부된 patch가 저장되면 스키마 게이트가 무의미해진다.

    E2E 실측에서 발견: merge→save→validate 순서라 exit 2를 받고도 evidence.json에
    잘못된 claim/visual_evidence가 남았다. 검증을 통과한 것만 저장해야 한다."""
    evidence.save(tmp_path, _skel())
    patch = tmp_path / "bad.json"
    patch.write_text(json.dumps({
        "visual_evidence": [{"type": "slide", "value": "x", "timestamp": 1.0,
                             "frame": "f.jpg", "confidence": 0.92}],
        "claims": [{"claim": "없는 근거", "timestamp": 1.0,
                    "evidence": [{"source": "frame", "ref": "v99"}]}]}),
        encoding="utf-8")

    p = _run([str(tmp_path), "--merge", str(patch)])
    assert p.returncode == 2

    after = evidence.load(tmp_path)
    assert after["claims"] == [], "거부된 claim이 저장됐다"
    assert after["visual_evidence"] == [], "거부된 visual_evidence가 저장됐다"


def test_cli_merge_persists_valid_patch(tmp_path):
    """정상 patch는 그대로 저장된다 (원자성 수정이 정상 경로를 막지 않는지)."""
    evidence.save(tmp_path, _skel())
    patch = tmp_path / "ok.json"
    patch.write_text(json.dumps({
        "zoom_frames": ["t0212_1024.jpg"],
        "visual_evidence": [
            {"type": "chart", "value": "16.3x", "timestamp": 132.0,
             "frame": "t0212_1024.jpg", "confidence": "high"}]}), encoding="utf-8")

    assert _run([str(tmp_path), "--merge", str(patch)]).returncode == 0
    assert len(evidence.load(tmp_path)["visual_evidence"]) == 1


def test_cli_verdicts_does_not_persist_invalid_status(tmp_path):
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "transcript", "ref": "0"}]}]})
    evidence.save(tmp_path, ev)
    vf = tmp_path / "v.json"
    vf.write_text(json.dumps([{"claim_id": "c1", "status": "probably-true"}]), encoding="utf-8")

    p = _run([str(tmp_path), "--verdicts", str(vf)])
    assert p.returncode == 2
    assert evidence.load(tmp_path)["claims"][0]["verification"]["status"] == "unaudited"


# ── v0.3: knowledge_items ──────────────────────────────────────────────────

def test_knowledge_items_start_empty_and_get_k_ids():
    assert _skel()["knowledge_items"] == []
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "command", "content": "pip install -U yt-dlp", "timestamp": 10.0,
         "evidence": [{"source": "transcript", "ref": "0"}]}]})
    assert ev["knowledge_items"][0]["id"] == "k1"


def test_knowledge_items_merge_is_append():
    ev = _skel()
    for t in ("concept", "warning"):
        ev = evidence.merge(ev, {"knowledge_items": [
            {"type": t, "content": "x", "timestamp": 1.0,
             "evidence": [{"source": "transcript", "ref": "0"}]}]})
    assert [k["id"] for k in ev["knowledge_items"]] == ["k1", "k2"]


def test_validate_rejects_unknown_knowledge_type():
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "vibe", "content": "x", "timestamp": 1.0,
         "evidence": [{"source": "transcript", "ref": "0"}]}]})
    assert any("vibe" in e for e in evidence.validate(ev))


def test_validate_rejects_knowledge_item_without_evidence():
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "concept", "content": "x", "timestamp": 1.0, "evidence": []}]})
    assert any("evidence" in e for e in evidence.validate(ev))


def test_validate_rejects_knowledge_item_with_empty_content():
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "concept", "content": "   ", "timestamp": 1.0,
         "evidence": [{"source": "transcript", "ref": "0"}]}]})
    assert any("content" in e for e in evidence.validate(ev))


def test_summary_line_includes_knowledge_count():
    assert "knowledge=0" in evidence.summary_line(_skel())


# ── v0.3: provenance 참조 무결성 ───────────────────────────────────────────

def test_validate_rejects_frame_not_in_provenance(tmp_path):
    """LLM이 없는 프레임 파일명을 지어내면 거부한다."""
    f = tmp_path / "t0132_1024.jpg"
    f.write_bytes(b"x")
    ev = evidence.build_skeleton(_info(), _sig(), _tr(), [f], "u")
    ev = evidence.merge(ev, {"visual_evidence": [
        {"type": "slide", "value": "x", "timestamp": 1.0,
         "frame": "t9999_1024.jpg", "confidence": "high"}]})
    assert any("t9999_1024.jpg" in e for e in evidence.validate(ev))


def test_validate_accepts_frame_present_in_provenance(tmp_path):
    f = tmp_path / "t0132_1024.jpg"
    f.write_bytes(b"x")
    ev = evidence.build_skeleton(_info(), _sig(), _tr(), [f], "u")
    ev = evidence.merge(ev, {"visual_evidence": [
        {"type": "slide", "value": "x", "timestamp": 92.0,
         "frame": "t0132_1024.jpg", "confidence": "high"}]})
    assert evidence.validate(ev) == []


def test_validate_accepts_zoom_frame_added_by_same_patch():
    """빌더가 확대로 새로 뽑은 프레임은 zoom_frames로 함께 신고하면 통과한다."""
    ev = evidence.merge(_skel(), {
        "zoom_frames": ["t0212_1024.jpg"],
        "visual_evidence": [{"type": "chart", "value": "16.3x", "timestamp": 132.0,
                             "frame": "t0212_1024.jpg", "confidence": "high"}]})
    assert evidence.validate(ev) == []


def test_validate_rejects_transcript_ref_out_of_range():
    """세그먼트가 2개인데 ref=99면 근거가 실재하지 않는다."""
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "transcript", "ref": "99"}]}]})
    assert any("99" in e for e in evidence.validate(ev))


def test_validate_rejects_non_numeric_transcript_ref():
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "transcript", "ref": "중간쯤"}]}]})
    assert any("transcript" in e for e in evidence.validate(ev))


def test_validate_applies_same_ref_rules_to_knowledge_items():
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "command", "content": "x", "timestamp": 1.0,
         "evidence": [{"source": "frame", "ref": "v42"}]}]})
    assert any("v42" in e for e in evidence.validate(ev))


# ── v0.3: zoom 프레임 등록 (E2E에서 발견한 결함) ──────────────────────────

def test_register_frames_parses_zoom_output():
    """zoom.py 출력(FRAME <path> t=MM:SS)을 그대로 먹여 등록할 수 있어야 한다.

    E2E 실측에서 발견: §3이 뽑은 확대 프레임을 evidence에 등록하는 경로가 없어서,
    빌더가 그 프레임을 근거로 쓰면 '실재하지 않는 프레임'으로 거부됐다. 파이프라인이
    이미 아는 사실을 LLM에게 재신고시키는 계약은 깨진다 — 오케스트레이터가 등록한다."""
    out = ("zoom: 2 kept, 0 dup-dropped, ranges=2:47@1024\n"
           r"FRAME C:\cache\vid\frames\t0247_1024.jpg t=02:47" "\n"
           r"FRAME C:\cache\vid\frames\t0311_1024.jpg t=03:11" "\n")
    assert evidence.parse_frame_lines(out) == ["t0247_1024.jpg", "t0311_1024.jpg"]


def test_register_frames_accepts_plain_list():
    assert evidence.parse_frame_lines("t0100_512.jpg\nt0200_1024.jpg\n") == [
        "t0100_512.jpg", "t0200_1024.jpg"]


def test_register_frames_is_idempotent():
    ev = _skel()
    ev = evidence.register_frames(ev, ["t0247_1024.jpg", "t0247_1024.jpg"])
    ev = evidence.register_frames(ev, ["t0247_1024.jpg"])
    zoom = ev["provenance"]["frames"]["zoom"]
    assert [f["file"] for f in zoom] == ["t0247_1024.jpg"]


def test_registered_zoom_frame_passes_validation():
    ev = evidence.register_frames(_skel(), ["t0247_1024.jpg"])
    ev = evidence.merge(ev, {"visual_evidence": [
        {"type": "slide", "value": "x", "timestamp": 167.0,
         "frame": "t0247_1024.jpg", "confidence": "high"}]})
    assert evidence.validate(ev) == []


def test_cli_add_frames_registers_from_file(tmp_path):
    evidence.save(tmp_path, _skel())
    f = tmp_path / "zoomout.txt"
    f.write_text(r"FRAME C:\c\frames\t0530_1024.jpg t=05:30", encoding="utf-8")
    p = _run([str(tmp_path), "--add-frames", str(f)])
    assert p.returncode == 0, p.stderr
    assert evidence.load(tmp_path)["provenance"]["frames"]["zoom"][0]["file"] == "t0530_1024.jpg"


# ── v0.3: 형식이 어긋난 patch도 스택 트레이스 없이 거부 ────────────────────

def test_merge_tolerates_string_gaps_and_validate_rejects(tmp_path):
    """E2E 실측: 빌더가 gaps를 문자열 배열로 써서 merge가 ValueError로 죽었다(exit 1).

    잘못된 patch는 **스택 트레이스가 아니라 INVALID + exit 2**로 나와야 한다 —
    SKILL.md가 'exit 2면 INVALID 줄을 빌더에게 돌려준다'는 계약에 의존하기 때문이다."""
    ev = evidence.merge(_skel(), {"gaps": ["프레임 공백 설명 문자열"]})
    errs = evidence.validate(ev)
    assert any("gaps" in e for e in errs)


def test_cli_rejects_malformed_gaps_with_exit_two(tmp_path):
    evidence.save(tmp_path, _skel())
    patch = tmp_path / "p.json"
    patch.write_text(json.dumps({"gaps": ["문자열 gap"]}), encoding="utf-8")
    p = _run([str(tmp_path), "--merge", str(patch)])
    assert p.returncode == 2, f"exit={p.returncode}\n{p.stderr}"
    assert "Traceback" not in p.stderr
    assert "INVALID" in p.stderr


def test_validate_rejects_non_dict_claims_and_visual_evidence():
    ev = _skel()
    ev["claims"].append("문자열 주장")
    ev["visual_evidence"].append(["리스트"])
    errs = evidence.validate(ev)
    assert any("claims" in e for e in errs)
    assert any("visual_evidence" in e for e in errs)


# ── v0.3.1: knowledge_items 감사 ───────────────────────────────────────────

def test_knowledge_items_default_to_unaudited():
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "setting", "content": "Add Python 3.9 to PATH를 체크한다", "timestamp": 203.0,
         "evidence": [{"source": "transcript", "ref": "0"}]}]})
    assert ev["knowledge_items"][0]["verification"]["status"] == "unaudited"


def test_verdict_applies_to_knowledge_item_by_id():
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "setting", "content": "x", "timestamp": 1.0,
         "evidence": [{"source": "transcript", "ref": "0"}]}]})
    ev = evidence.apply_verdicts(ev, [
        {"id": "k1", "status": "verified", "auditor": "sonnet", "note": "프레임 대조"}])
    assert ev["knowledge_items"][0]["verification"]["status"] == "verified"


def test_verdict_can_dispute_knowledge_item():
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "command", "content": "pip install wrong-pkg", "timestamp": 1.0,
         "evidence": [{"source": "transcript", "ref": "0"}]}]})
    ev = evidence.apply_verdicts(ev, [{"id": "k1", "status": "disputed"}])
    assert ev["knowledge_items"][0]["verification"]["status"] == "disputed"


def test_verdict_legacy_claim_id_still_works():
    """기존 verdicts.json은 claim_id 키를 쓴다 — 깨지 않는다."""
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "transcript", "ref": "0"}]}]})
    ev = evidence.apply_verdicts(ev, [{"claim_id": "c1", "status": "verified"}])
    assert ev["claims"][0]["verification"]["status"] == "verified"


def test_verdict_for_missing_knowledge_item_flags_orphan():
    ev = evidence.apply_verdicts(_skel(), [{"id": "k99", "status": "verified"}])
    assert any("verdict_orphan: k99" in f for f in ev["flags"])


def test_validate_rejects_bad_knowledge_verification_status():
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "setting", "content": "x", "timestamp": 1.0,
         "evidence": [{"source": "transcript", "ref": "0"}],
         "verification": {"status": "probably"}}]})
    assert any("probably" in e for e in evidence.validate(ev))


def test_audit_candidates_prioritises_actionable_types():
    """실행에 영향을 주는 type이 먼저 온다 — command/setting/action이 concept보다 위험하다."""
    ev = _skel()
    for t, c in [("concept", "개념"), ("command", "pip install x"),
                 ("example", "예시"), ("setting", "PATH 체크"), ("criterion", "성공 기준")]:
        ev = evidence.merge(ev, {"knowledge_items": [
            {"type": t, "content": c, "timestamp": 1.0,
             "evidence": [{"source": "transcript", "ref": "0"}]}]})
    ev = evidence.merge(ev, {"claims": [
        {"claim": "주장", "timestamp": 1.0, "evidence": [{"source": "transcript", "ref": "0"}]}]})

    picked = evidence.audit_candidates(ev, limit=3)
    types = [p["type"] for p in picked]
    assert types[0] in ("command", "setting", "criterion")
    assert "concept" not in types, "우선순위 낮은 type이 상위 3건에 들어갔다"
    assert all("id" in p and "content" in p and "evidence" in p for p in picked)


def test_audit_candidates_includes_claims_when_knowledge_is_sparse():
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": f"주장{i}", "timestamp": 1.0,
         "evidence": [{"source": "transcript", "ref": "0"}]} for i in range(3)]})
    picked = evidence.audit_candidates(ev, limit=6)
    assert len(picked) == 3
    assert all(p["kind"] == "claim" for p in picked)


def test_audit_candidates_skips_already_audited():
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "command", "content": "x", "timestamp": 1.0,
         "evidence": [{"source": "transcript", "ref": "0"}]}]})
    ev = evidence.apply_verdicts(ev, [{"id": "k1", "status": "verified"}])
    assert evidence.audit_candidates(ev, limit=6) == []


# ── v0.3.1: coverage audit 입력 (evidence 기준) ────────────────────────────

def _ev_with(items, claims=()):
    ev = _skel()
    if items:
        ev = evidence.merge(ev, {"knowledge_items": [
            {"type": t, "content": c, "timestamp": 1.0,
             "evidence": [{"source": "transcript", "ref": "0"}]} for t, c in items]})
    if claims:
        ev = evidence.merge(ev, {"claims": [
            {"claim": c, "timestamp": 1.0, "evidence": [{"source": "transcript", "ref": "0"}]}
            for c in claims]})
    return ev


def test_knowledge_digest_lists_type_and_content():
    ev = _ev_with([("concept", "대기열은 비팔로워 전용"), ("command", "pip install -U yt-dlp")])
    d = evidence.knowledge_digest(ev)
    assert "[command] pip install -U yt-dlp" in d
    assert "[concept] 대기열은 비팔로워 전용" in d


def test_knowledge_digest_includes_claims():
    d = evidence.knowledge_digest(_ev_with([], claims=["조회수가 16.3배 차이난다"]))
    assert any(x.startswith("[claim]") and "16.3" in x for x in d)


def test_knowledge_digest_is_what_coverage_audit_compares(tmp_path):
    """커버리지 감사의 심판 대상은 video.md 제목이 아니라 evidence의 실제 지식이다.

    사용자 지적: adaptive video.md는 '## Phase 1' 같은 제목만으로 내부에 무엇이
    들어갔는지 알 수 없다. 제목이 같아도 evidence 내용이 다르면 누락이 잡혀야 한다."""
    have = _ev_with([("concept", "개념 A"), ("command", "명령 B")])
    want = _ev_with([("concept", "개념 A"), ("command", "명령 B"), ("criterion", "기준 C")])

    d_have, d_want = evidence.knowledge_digest(have), evidence.knowledge_digest(want)
    missing = [x for x in d_want if x not in d_have]
    assert missing == ["[criterion] 기준 C"], f"누락 검출 실패: {missing}"


def test_knowledge_digest_empty_on_bare_skeleton():
    assert evidence.knowledge_digest(_skel()) == []


def test_cli_audit_candidates_prints_ids(tmp_path):
    ev = _ev_with([("command", "pip install x"), ("concept", "개념")])
    evidence.save(tmp_path, ev)
    p = _run([str(tmp_path), "--audit-candidates", "2"])
    assert p.returncode == 0, p.stderr
    assert "command" in p.stdout and "k1" in p.stdout


def test_cli_digest_prints_lines(tmp_path):
    evidence.save(tmp_path, _ev_with([("setting", "PATH 체크")]))
    p = _run([str(tmp_path), "--digest"])
    assert p.returncode == 0
    assert "[setting] PATH 체크" in p.stdout


# ── v0.3.2: 시각 관측 (visual coverage) ────────────────────────────────────

def _ev_with_frames(kn=()):
    """map 프레임 1장 + zoom 프레임 2장이 등록된 evidence."""
    ev = evidence.build_skeleton(_info(), _sig(), _tr(), ["t0001_512.jpg"], "u")
    ev = evidence.register_frames(ev, ["t0323_1024.jpg", "t0518_1024.jpg"])
    if kn:
        ev = evidence.merge(ev, {"knowledge_items": [
            {"type": t, "content": c, "timestamp": ts,
             "evidence": [{"source": "transcript", "ref": "0"}]} for t, c, ts in kn]})
    return ev


def _obs(kind, ts, frame="t0323_1024.jpg", text="something visible"):
    return {"timestamp": ts, "kind": kind, "observation": text, "frame": frame}


def test_validate_observations_accepts_well_formed():
    ev = _ev_with_frames()
    assert evidence.validate_observations([_obs("setting", 203.0)], ev) == []


def test_validate_observations_rejects_unknown_kind():
    ev = _ev_with_frames()
    errs = evidence.validate_observations([_obs("vibes", 1.0)], ev)
    assert any("vibes" in e for e in errs)


def test_validate_observations_rejects_frame_not_in_provenance():
    ev = _ev_with_frames()
    errs = evidence.validate_observations([_obs("command", 1.0, frame="t9999_1024.jpg")], ev)
    assert any("t9999_1024.jpg" in e for e in errs)


def test_validate_observations_rejects_missing_timestamp():
    ev = _ev_with_frames()
    errs = evidence.validate_observations([{"kind": "command", "observation": "x",
                                            "frame": "t0323_1024.jpg"}], ev)
    assert any("timestamp" in e for e in errs)


def test_validate_observations_rejects_empty_observation():
    ev = _ev_with_frames()
    errs = evidence.validate_observations([_obs("command", 1.0, text="  ")], ev)
    assert any("observation" in e for e in errs)


def test_validate_observations_rejects_non_dict():
    assert any("객체" in e for e in evidence.validate_observations(["문자열"], _ev_with_frames()))


def test_observation_kinds_reuse_knowledge_types():
    for t in evidence.KNOWLEDGE_TYPES:
        assert t in evidence.OBSERVATION_KINDS
    assert "numeric" in evidence.OBSERVATION_KINDS


# ── v0.3.2 핵심: 화면에만 있던 정보의 누락 검출 ────────────────────────────

def test_uncovered_observation_when_evidence_missed_a_screen_only_command():
    """이번 작업의 핵심 시험.

    화면에는 터미널 명령이 보이는데(관측) evidence에는 그 시점 command가 전혀 없다
    → 커버리지 후보. 자막에 안 나온 정보라 transcript 기반 감사로는 존재조차 모른다."""
    ev = _ev_with_frames(kn=[("concept", "개념 설명", 200.0),
                             ("setting", "설정 하나", 205.0)])
    obs = [_obs("command", 318.0, frame="t0518_1024.jpg",
                text="terminal command visible")]
    unc = evidence.uncovered_observations(ev, obs)
    assert len(unc) == 1 and unc[0]["kind"] == "command"


def test_observation_is_covered_when_same_kind_is_nearby():
    ev = _ev_with_frames(kn=[("command", "pip install -U yt-dlp", 320.0)])
    assert evidence.uncovered_observations(ev, [_obs("command", 318.0)]) == []


def test_kind_mismatch_alone_is_not_a_candidate():
    """kind가 달라도 근처에 evidence가 있으면 후보가 아니다 — **실측으로 정한 규칙**이다.

    판독 에이전트와 빌더는 같은 화면을 다르게 분류한다. t1-XAN6AyOs 실측에서 t=492s에
    evidence 항목이 10건 있는데 아무것도 comparison 타입이 아니라는 이유로 후보가 됐다
    (판독은 "비교 카드", 빌더는 "claim"). kind 일치를 요구하면 오탐 11건 중 8건."""
    ev = _ev_with_frames(kn=[("concept", "개념", 320.0)])
    assert evidence.uncovered_observations(ev, [_obs("command", 318.0)]) == []


def test_window_default_is_twenty_seconds():
    """30초 이상이면 무관한 인접 항목이 진짜 누락을 덮는다 (ablation 실측)."""
    ev = _ev_with_frames(kn=[("procedure", "다른 절차", 257.0)])
    obs = [_obs("command", 285.0)]
    assert len(evidence.uncovered_observations(ev, obs)) == 1        # 기본 20s → 검출
    assert evidence.uncovered_observations(ev, obs, window=45.0) == []  # 45s → 미탐


def test_observation_outside_window_is_candidate():
    ev = _ev_with_frames(kn=[("command", "x", 10.0)])
    assert len(evidence.uncovered_observations(ev, [_obs("command", 300.0)])) == 1


def test_numeric_observation_is_loosely_matched():
    """numeric/other는 kind 특정이 안 되므로 근처에 아무 항목이나 있으면 covered."""
    ev = _ev_with_frames(kn=[("result", "결과", 200.0)])
    assert evidence.uncovered_observations(ev, [_obs("numeric", 205.0)]) == []


def test_coverage_input_contains_digest_observations_and_prefilter():
    ev = _ev_with_frames(kn=[("concept", "개념 A", 10.0)])
    text = evidence.coverage_input(ev, [_obs("command", 318.0)])
    assert "EVIDENCE DIGEST" in text
    assert "[concept] 개념 A" in text
    assert "VISUAL OBSERVATIONS" in text
    assert "사전 필터" in text
    assert "terminal" in text or "something visible" in text


def test_cli_coverage_input_validates_and_prints(tmp_path):
    ev = _ev_with_frames(kn=[("concept", "개념", 10.0)])
    evidence.save(tmp_path, ev)
    f = tmp_path / "visual-coverage.json"
    f.write_text(json.dumps({"observations": [_obs("command", 318.0)]}), encoding="utf-8")
    p = _run([str(tmp_path), "--coverage-input", str(f)])
    assert p.returncode == 0, p.stderr
    assert "VISUAL OBSERVATIONS" in p.stdout


def test_cli_coverage_input_rejects_bad_observation(tmp_path):
    evidence.save(tmp_path, _ev_with_frames())
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"observations": [_obs("nope", 1.0)]}), encoding="utf-8")
    p = _run([str(tmp_path), "--coverage-input", str(f)])
    assert p.returncode == 2
    assert "nope" in p.stderr


def test_cross_check_detects_hash_misread():
    """실측 사례: 같은 커밋 해시가 3f4a625와 3f4a0625로 갈렸다 — 편집거리 1 유사쌍을 잡는다."""
    ev = {"visual_evidence": [
        {"id": "v1", "value": "3f4a625 Examples for 4.4", "timestamp": 1.0},
        {"id": "v2", "value": "pick 3f4a0625 Examples for 4.4", "timestamp": 2.0},
    ]}
    flags = evidence.cross_check_values(ev)
    assert len(flags) == 1
    assert set(flags[0]["values"]) == {"3f4a625", "3f4a0625"}
    assert set(flags[0]["ids"]) == {"v1", "v2"}


def test_cross_check_ignores_identical_and_unrelated():
    """같은 값의 반복은 정상이고, 전혀 다른 값끼리는 묶지 않는다 (오탐 방지)."""
    ev = {"visual_evidence": [
        {"id": "v1", "value": "50d1d83 base", "timestamp": 1.0},
        {"id": "v2", "value": "50d1d83 base again", "timestamp": 2.0},
        {"id": "v3", "value": "abcdef1 other", "timestamp": 3.0},
    ]}
    assert evidence.cross_check_values(ev) == []


def test_cross_check_detects_numeric_misread():
    """수치도 같은 규칙으로 잡는다 — 84K vs 83K 류."""
    ev = {"visual_evidence": [
        {"id": "v1", "value": "views 90991", "timestamp": 1.0},
        {"id": "v2", "value": "total 90091", "timestamp": 2.0},
    ]}
    flags = evidence.cross_check_values(ev)
    assert len(flags) == 1
    assert flags[0]["kind"] == "numeric"


def test_audit_candidates_promotes_cross_check_flags():
    """교차 대조에 걸린 항목은 표본 감사 최상위로 올라간다 — 표본 선정 개선이 목적이다."""
    ev = {
        "visual_evidence": [
            {"id": "v1", "value": "3f4a625 x", "timestamp": 1.0},
            {"id": "v2", "value": "3f4a0625 x", "timestamp": 2.0},
        ],
        "claims": [],
        "knowledge_items": [
            {"id": "k1", "type": "command", "content": "git rebase -i", "timestamp": 5.0,
             "evidence": [{"source": "frame", "ref": "v9"}]},
            {"id": "k2", "type": "example", "content": "해시 예시", "timestamp": 2.0,
             "evidence": [{"source": "frame", "ref": "v2"}]},
        ],
    }
    got = evidence.audit_candidates(ev, limit=2)
    assert got[0]["id"] == "k2", "교차 대조 flag가 붙은 항목이 command보다 먼저 와야 한다"


def test_cross_check_does_not_double_report_pure_digits():
    """순수 숫자는 numeric 한 번만 — hex 정규식이 숫자도 먹어 같은 쌍이 두 줄로 나오던 결함."""
    ev = {"visual_evidence": [
        {"id": "v1", "value": "uploaded 20260818", "timestamp": 1.0},
        {"id": "v2", "value": "uploaded 20260819", "timestamp": 2.0},
    ]}
    flags = evidence.cross_check_values(ev)
    assert len(flags) == 1
    assert flags[0]["kind"] == "numeric"


def test_cross_check_still_detects_real_hash():
    """a-f를 포함한 진짜 해시는 계속 hash로 잡힌다 (위 수정의 음성 회귀 가드)."""
    ev = {"visual_evidence": [
        {"id": "v1", "value": "commit 3f4a625", "timestamp": 1.0},
        {"id": "v2", "value": "commit 3f4a0625", "timestamp": 2.0},
    ]}
    flags = evidence.cross_check_values(ev)
    assert len(flags) == 1 and flags[0]["kind"] == "hash"


def test_cross_check_skips_items_without_id():
    """id 없는 항목은 건너뛴다 — audit_candidates가 항상 호출하므로 크래시하면 안 된다."""
    ev = {"visual_evidence": [
        {"value": "commit 3f4a625", "timestamp": 1.0},
        {"id": "v2", "value": "commit 3f4a0625", "timestamp": 2.0},
    ]}
    assert evidence.cross_check_values(ev) == []


def test_cross_check_promotion_is_capped_at_one():
    """표본 3건 체제에서 오탐이 슬롯을 과점하지 않도록 승격은 1건까지만이다."""
    ev = {
        "visual_evidence": [
            {"id": "v1", "value": "count 100"}, {"id": "v2", "value": "count 200"},
            {"id": "v3", "value": "total 3f4a625"}, {"id": "v4", "value": "total 3f4a0625"},
        ],
        "claims": [],
        "knowledge_items": [
            {"id": "k1", "type": "command", "content": "npm install -g x", "timestamp": 1.0,
             "evidence": [{"source": "frame", "ref": "v9"}]},
            {"id": "k2", "type": "example", "content": "예시 A", "timestamp": 2.0,
             "evidence": [{"source": "frame", "ref": "v1"}]},
            {"id": "k3", "type": "example", "content": "예시 B", "timestamp": 3.0,
             "evidence": [{"source": "frame", "ref": "v3"}]},
        ],
    }
    got = [c["id"] for c in evidence.audit_candidates(ev, limit=3)]
    assert got[0] in ("k2", "k3"), "flag된 항목 1건은 최상위로 승격된다"
    assert "k1" in got[:2], "나머지 슬롯은 행동 영향도 순서(command)가 차지해야 한다"


def test_audit_candidates_default_limit_is_three():
    """라운드5 이월: 구 정밀 파이프라인이 3건으로 고정했었고 solo에서도 낡은 기본값 6이 되살아나면 안 되므로 기본값이 6이면 인자 없는 호출이 조용히 6으로 회귀한다."""
    import inspect
    assert inspect.signature(evidence.audit_candidates).parameters["limit"].default == 3


def _render_fixture():
    return {
        "video": {"id": "x", "title": "테스트 영상", "url": "https://youtu.be/x",
                  "duration": 687.0, "channel": "채널"},
        "video_type": {"primary": "tutorial", "confidence": "high", "basis": "화면 실연"},
        "visual_evidence": [
            {"id": "v1", "type": "ui", "value": "16.3x", "timestamp": 132.0,
             "frame": "t0212_1024.jpg", "confidence": "high"}],
        "claims": [
            {"id": "c1", "claim": "속도가 빨라진다", "timestamp": 132.0,
             "evidence": [{"source": "frame", "ref": "v1"}, {"source": "transcript", "ref": "12"}],
             "conflict": {"transcript": "16배", "screen": "16.3x"},
             "verification": {"status": "unaudited"}}],
        "knowledge_items": [
            {"id": "k1", "type": "command", "content": "pip install -U yt-dlp",
             "timestamp": 88.0, "evidence": [{"source": "frame", "ref": "v1"}],
             "verification": {"status": "unaudited"}},
            {"id": "k2", "type": "concept", "content": "자막 전용 개념", "timestamp": 10.0,
             "evidence": [{"source": "transcript", "ref": "3"}],
             "verification": {"status": "unaudited"}}],
        "gaps": [{"start": 350.0, "end": 469.0, "reason": "지도 공백"}],
        "flags": [],
    }


def test_render_contains_required_elements():
    """게이트 기준 4: 근거 인용·화면/자막 구분·conflict 병기·누락 후보·정직성 문구."""
    md = evidence.render_video_md(_render_fixture(), cross_flags=1, coverage_added=2)
    assert "# 테스트 영상" in md
    assert "(t=01:28)" in md and "(t=02:12)" in md          # fmt_ts 인용
    assert "화면 확인" in md and "자막 근거만" in md          # 근거 구분
    assert "16배" in md and "16.3x" in md                    # conflict 병기
    assert "05:50" in md and "07:49" in md and "지도 공백" in md   # gaps
    assert "표본 감사 미실시" in md
    assert "교차 대조" in md and "1" in md                   # 스탬프에 flag 수


def test_render_groups_knowledge_by_priority():
    """command가 concept보다 먼저 — AUDIT_PRIORITY 순 그룹."""
    md = evidence.render_video_md(_render_fixture())
    assert md.index("pip install") < md.index("자막 전용 개념")


def test_render_cli_writes_file(tmp_path):
    ev = _render_fixture()
    (tmp_path / "evidence.json").write_text(
        __import__("json").dumps(ev, ensure_ascii=False), encoding="utf-8")
    import sys as _sys
    evidence.save(tmp_path, ev)
    rc = None
    _argv = ["evidence.py", str(tmp_path), "--render", "--cross-flags", "1"]
    old = _sys.argv; _sys.argv = _argv
    try:
        rc = evidence.main()
    finally:
        _sys.argv = old
    assert rc == 0
    out = (tmp_path / "video.md").read_text(encoding="utf-8")
    assert "# 테스트 영상" in out


def test_render_survives_null_timestamps():
    """--render는 저장된 evidence에 단독 실행된다 — null timestamp가 traceback을 내면
    fail-loud 관례(사용자 노출 traceback 금지) 위반이다."""
    ev = _render_fixture()
    ev["knowledge_items"][0]["timestamp"] = None
    ev["gaps"][0]["start"] = None
    ev["video"]["duration"] = "abc"
    md = evidence.render_video_md(ev)
    assert "(t=00:00)" in md          # null → 0으로 강등, 크래시 없음
    assert "# 테스트 영상" in md


# ── --from-lines 컴팩트 patch 확장기 ────────────────────────────────────────

_LINES = (
    "T\ttutorial\thigh\t화면 실연\n"
    "V\tui\t132.0\tt0212_1024.jpg\thigh\t16.3x 표시\n"
    "K\tcommand\t88.0\tv1;t12\tpip install -U yt-dlp\n"
    "C\t132.0\tv1;t12\t속도가 빨라진다\tconflict=16배=>16.3x\n"
    "G\t350.0\t469.0\t지도 공백\n"
)


def test_expand_lines_builds_full_patch():
    p = evidence.expand_lines(_LINES)
    assert p["video_type"] == {"primary": "tutorial", "confidence": "high", "basis": "화면 실연"}
    ve = p["visual_evidence"][0]
    assert ve["id"] == "v1" and ve["timestamp"] == 132.0 and ve["frame"] == "t0212_1024.jpg"
    k = p["knowledge_items"][0]
    assert k["evidence"] == [{"source": "frame", "ref": "v1"}, {"source": "transcript", "ref": "12"}]
    c = p["claims"][0]
    assert c["conflict"] == {"transcript": "16배", "screen": "16.3x"}
    assert c["verification"] == {"status": "unaudited"}
    assert p["gaps"] == [{"start": 350.0, "end": 469.0, "reason": "지도 공백"}]


def test_expand_lines_rejects_unknown_record():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        evidence.expand_lines("X\t뭔가\n")


def test_expand_lines_merge_equivalence(tmp_path):
    """확장 결과가 손으로 쓴 JSON patch와 동일한 merge 결과를 내야 한다 (기준점 2)."""
    import json as _json
    base = {"schema_version": "0.3", "video": {"id": "x", "duration": 687.0},
            "video_type": {}, "provenance": {"frames": {"map": [
                {"file": "t0212_1024.jpg", "t": 132.0}], "zoom": []}, "transcript": {}},
            "segments": [{"start": float(i), "text": f"s{i}"} for i in range(20)],
            "visual_evidence": [], "claims": [], "knowledge_items": [], "gaps": [], "flags": []}
    evidence.save(tmp_path, _json.loads(_json.dumps(base)))
    merged_a = evidence.merge(_json.loads(_json.dumps(base)), evidence.expand_lines(_LINES))
    json_patch = {
        "video_type": {"primary": "tutorial", "confidence": "high", "basis": "화면 실연"},
        "visual_evidence": [{"id": "v1", "type": "ui", "value": "16.3x 표시",
                             "timestamp": 132.0, "frame": "t0212_1024.jpg", "confidence": "high"}],
        "knowledge_items": [{"type": "command", "content": "pip install -U yt-dlp", "timestamp": 88.0,
                             "evidence": [{"source": "frame", "ref": "v1"},
                                          {"source": "transcript", "ref": "12"}]}],
        "claims": [{"claim": "속도가 빨라진다", "timestamp": 132.0,
                    "evidence": [{"source": "frame", "ref": "v1"},
                                 {"source": "transcript", "ref": "12"}],
                    "conflict": {"transcript": "16배", "screen": "16.3x"},
                    "verification": {"status": "unaudited"}}],
        "gaps": [{"start": 350.0, "end": 469.0, "reason": "지도 공백"}]}
    merged_b = evidence.merge(_json.loads(_json.dumps(base)), json_patch)
    for key in ("visual_evidence", "claims", "knowledge_items", "gaps"):
        assert merged_a[key] == merged_b[key], key


def test_expand_lines_offsets_ids_on_reinvocation():
    """재호출 시 기존 v-id와 충돌하면 안 된다 — refs도 함께 재매핑된다."""
    lines = "V\tui\t10.0\tf.jpg\thigh\t값A\nK\tcommand\t10.0\tv1\t명령"
    p = evidence.expand_lines(lines, id_offset=3)
    assert p["visual_evidence"][0]["id"] == "v4"
    assert p["knowledge_items"][0]["evidence"] == [{"source": "frame", "ref": "v4"}]


def test_validate_rejects_duplicate_visual_ids():
    ev = {"schema_version": "0.3", "video": {}, "video_type": {},
          "provenance": {"frames": {"map": [], "zoom": []}, "transcript": {}},
          "segments": [], "claims": [], "knowledge_items": [], "gaps": [], "flags": [],
          "visual_evidence": [
              {"id": "v1", "value": "a", "timestamp": 1.0},
              {"id": "v1", "value": "b", "timestamp": 2.0}]}
    errs = evidence.validate(ev)
    assert any("중복" in e for e in errs)


def test_expand_lines_unknown_record_includes_line_number():
    """행 번호 없는 에러는 'INVALID 보고 1회 수정' 왕복을 성립시키지 못한다."""
    import pytest as _pytest
    with _pytest.raises(ValueError, match=r"2행"):
        evidence.expand_lines("V\tui\t1.0\tf.jpg\thigh\tok\nX\t뭔가")


def test_expand_lines_multi_v_sequential_ids_with_nonempty_base(tmp_path):
    """다건 V 순차 부여 + 비어 있지 않은 base 병합 — Critical 1이 터지던 정확한 지점."""
    import json as _json
    base = {"schema_version": "0.3", "video": {"id": "x", "duration": 10.0}, "video_type": {},
            "provenance": {"frames": {"map": [{"file": "f.jpg", "t": 1.0}], "zoom": []},
                           "transcript": {}},
            "segments": [{"start": 0.0, "text": "s"}],
            "visual_evidence": [{"id": "v1", "value": "기존", "timestamp": 1.0, "frame": "f.jpg"}],
            "claims": [], "knowledge_items": [], "gaps": [], "flags": []}
    lines = ("V\tui\t2.0\tf.jpg\thigh\t새값1\n"
             "V\tui\t3.0\tf.jpg\thigh\t새값2\n"
             "K\tcommand\t2.0\tv1;v2\t두 프레임 참조 명령")
    p = evidence.expand_lines(lines, id_offset=1)
    merged = evidence.merge(_json.loads(_json.dumps(base)), p)
    ids = [v["id"] for v in merged["visual_evidence"]]
    assert ids == ["v1", "v2", "v3"] and len(set(ids)) == 3
    assert merged["knowledge_items"][0]["evidence"][0]["ref"] == "v2"
    assert evidence.validate(merged) == [] or not any("중복" in e for e in evidence.validate(merged))
