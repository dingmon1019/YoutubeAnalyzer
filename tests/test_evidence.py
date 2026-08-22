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


def test_render_includes_transcript_source():
    """렌더 문서에 자막 출처가 있어야 자막 전용 주장의 신뢰 수준을 판단할 수 있다."""
    ev = {"video": {"title": "t", "duration": 10.0}, "video_type": {},
          "provenance": {"transcript": {"source": "captions", "lang": "ko"}},
          "visual_evidence": [], "claims": [], "knowledge_items": [], "gaps": [], "flags": []}
    md = evidence.render_video_md(ev, note="커버리지 감사 생략 — 자막 없음")
    assert "자막 출처" in md and "captions" in md
    assert "커버리지 감사 생략" in md


# ── 챕터별 절 구성 (라운드 "분량 비례 예산" Task 2) ─────────────────────────

EV_WITH_TWO_ITEMS = {
    "video": {"id": "y", "title": "챕터 테스트 영상", "url": "https://youtu.be/y",
              "duration": 200.0, "channel": "채널"},
    "video_type": {"primary": "tutorial", "confidence": "high", "basis": "화면 실연"},
    "visual_evidence": [],
    "claims": [],
    "knowledge_items": [
        {"id": "k1", "type": "command", "content": "pip install foo", "timestamp": 70.0,
         "evidence": [], "verification": {"status": "unaudited"}},
        {"id": "k2", "type": "action", "content": "실행 버튼 클릭", "timestamp": 130.0,
         "evidence": [], "verification": {"status": "unaudited"}},
    ],
    "gaps": [],
    "flags": [],
}


class TestRenderChapters:
    CHAPTERS = [
        {"start_time": 0, "end_time": 60, "title": "인트로"},
        {"start_time": 60, "end_time": 120, "title": "설치"},
        {"start_time": 120, "end_time": 180, "title": "실행"},
    ]

    def test_chapter_sections(self):
        # K(ts=70)는 "설치" 절에, K(ts=130)는 "실행" 절에 들어간다
        md = evidence.render_video_md(EV_WITH_TWO_ITEMS, chapters=self.CHAPTERS)
        assert "### [01:00] 설치" in md and "### [02:00] 실행" in md
        assert md.index("설치") < md.index("실행")  # 시간순 절 배열
        assert "인트로" not in md  # 빈 챕터("인트로", 0~60)는 절을 만들지 않는다

    def test_item_outside_chapters_goes_to_misc(self):
        # ts=999(범위 밖)·ts=None 항목은 "### 기타" 절로
        ev = json.loads(json.dumps(EV_WITH_TWO_ITEMS))
        ev["knowledge_items"].append(
            {"id": "k3", "type": "concept", "content": "범위 밖 지식", "timestamp": 999.0,
             "evidence": [], "verification": {"status": "unaudited"}})
        ev["knowledge_items"].append(
            {"id": "k4", "type": "concept", "content": "타임스탬프 없는 지식", "timestamp": None,
             "evidence": [], "verification": {"status": "unaudited"}})
        md = evidence.render_video_md(ev, chapters=self.CHAPTERS)
        assert "### 기타" in md
        assert md.index("### 기타") > md.index("실행")  # 기타 절은 마지막
        misc_pos = md.index("### 기타")
        assert md.index("범위 밖 지식") > misc_pos
        assert md.index("타임스탬프 없는 지식") > misc_pos

    def test_no_chapters_keeps_flat_rendering(self):
        # chapters=None이면 기존 유형별 렌더링 그대로 — 기존 테스트가 무변경 PASS인 것도 이 계약의 일부
        md = evidence.render_video_md(EV_WITH_TWO_ITEMS)
        assert "## 핵심 지식" in md and "### [" not in md

    def test_chapter_item_carries_type_label(self):
        # 챕터 모드에선 유형 절이 사라지므로 항목 줄에 유형 태그를 단다
        md = evidence.render_video_md(EV_WITH_TWO_ITEMS, chapters=self.CHAPTERS)
        assert "- [" in md  # 예: "- [명령어] pip install ..."

    def test_chapter_items_sorted_by_timestamp_ascending(self):
        """리뷰 F4② 발견: 챕터 절 내부 항목이 삽입 순서로 나와 04:15→04:40→04:28처럼
        뒤섞이는 버그가 있었다 — timestamp 오름차순으로 정렬돼야 한다."""
        ev = json.loads(json.dumps(EV_WITH_TWO_ITEMS))
        ev["knowledge_items"] = [
            {"id": "k1", "type": "command", "content": "A항목", "timestamp": 255.0,
             "evidence": [], "verification": {"status": "unaudited"}},
            {"id": "k2", "type": "command", "content": "B항목", "timestamp": 280.0,
             "evidence": [], "verification": {"status": "unaudited"}},
            {"id": "k3", "type": "command", "content": "C항목", "timestamp": 268.0,
             "evidence": [], "verification": {"status": "unaudited"}},
        ]
        chapters = self.CHAPTERS + [{"start_time": 180, "end_time": 300, "title": "구간"}]
        md = evidence.render_video_md(ev, chapters=chapters)
        assert md.index("A항목") < md.index("C항목") < md.index("B항목")

    def test_non_dict_chapter_element_is_skipped_not_fatal(self):
        """리뷰 F4① 가드: chapters 원소 중 dict가 아닌 것이 섞여도(예: info.json 오염)
        그 원소만 건너뛰고 나머지 유효한 챕터로 렌더를 완주한다."""
        bad_chapters = [None, *self.CHAPTERS]
        md = evidence.render_video_md(EV_WITH_TWO_ITEMS, chapters=bad_chapters)
        assert "### [01:00] 설치" in md and "### [02:00] 실행" in md

    def test_short_video_still_gets_chapter_layout(self):
        """컨트롤러 재정(F3): 챕터 레이아웃 개선은 영상 길이와 무관한 의도된 동작이다 —
        짧은 영상(300초 수준, 챕터 3개)도 chapters가 주어지면 예외 없이 챕터 절로
        렌더되고 검증 스탬프·"표본 감사 미실시"가 보존된다."""
        ev = json.loads(json.dumps(EV_WITH_TWO_ITEMS))
        ev["video"]["duration"] = 300.0
        md = evidence.render_video_md(ev, chapters=self.CHAPTERS)
        assert "### [01:00] 설치" in md and "### [02:00] 실행" in md
        assert "표본 감사 미실시" in md


def test_render_cli_reads_chapters_from_info_json(tmp_path):
    """--render는 <cache_dir>/info.json의 chapters 키를 읽어 절을 구성한다."""
    evidence.save(tmp_path, EV_WITH_TWO_ITEMS)
    (tmp_path / "info.json").write_text(json.dumps({
        "chapters": [
            {"start_time": 0, "end_time": 60, "title": "인트로"},
            {"start_time": 60, "end_time": 120, "title": "설치"},
            {"start_time": 120, "end_time": 180, "title": "실행"},
        ]}, ensure_ascii=False), encoding="utf-8")
    p = _run([str(tmp_path), "--render"])
    assert p.returncode == 0
    out = (tmp_path / "video.md").read_text(encoding="utf-8")
    assert "### [01:00] 설치" in out and "### [02:00] 실행" in out


def test_render_cli_falls_back_to_flat_on_malformed_info_json(tmp_path):
    """info.json이 파손되어도 stderr에 NOTE를 남기고 평면 렌더링으로 완주한다(fail-loud 완화형)."""
    evidence.save(tmp_path, EV_WITH_TWO_ITEMS)
    (tmp_path / "info.json").write_text("{이것은 json이 아니다", encoding="utf-8")
    p = _run([str(tmp_path), "--render"])
    assert p.returncode == 0
    assert "NOTE" in p.stderr
    out = (tmp_path / "video.md").read_text(encoding="utf-8")
    assert "## 핵심 지식" in out and "### [" not in out


def _frames_ev(ts, duration):
    """프레임 t 리스트 + 영상 길이로 evidence 골격을 만든다.

    gap_zoom_plan(Task 6)은 더 이상 ev["gaps"]를 입력으로 읽지 않는다 — 공백은
    provenance.frames(map+zoom) 타임스탬프에서 결정론으로 계산된다(_frame_gap_source).
    기존 테스트들은 gaps 딕셔너리를 직접 넣었지만, 이제는 그 gaps 딕셔너리와 동치인
    공백을 만드는 프레임 배치로 재현해야 한다."""
    return {
        "video": {"duration": duration},
        "provenance": {"frames": {"map": [{"t": t} for t in ts], "zoom": []}},
    }


def _pad_past_gate(ts, duration):
    """최종 리뷰 F1(20분 게이트) 도입 이후 보조 헬퍼.

    아래 TestGapZoomPlan/TestGapZoomPlanActivity의 산술 테스트는 전부
    GAP_BACKFILL_MIN_DURATION(1200초=20분) 미만의 duration을 쓴다 — 게이트가 없던
    시절에는 문제없었지만, 이제는 전부 빈 리스트로 막혀버린다. 테스트가 검증하려는
    공백 구조(위치·크기)는 그대로 두고, ts의 마지막 지점 뒤에 80초 간격(임계
    GAP_BACKFILL_THRESHOLD=90초 미만이라 새 공백을 만들지 않는다) 프레임을 게이트
    초과까지 이어붙여 총 길이만 20분을 넘긴다."""
    ts = list(ts)
    if not ts or duration > max(ts):
        ts.append(duration)  # 원래 경계(마지막 프레임 또는 duration)를 프레임으로 고정
    boundary = max(ts)
    tail = []
    t = boundary
    while t <= evidence.GAP_BACKFILL_MIN_DURATION:
        t += 80.0
        tail.append(t)
    new_duration = tail[-1] if tail else duration
    return ts + tail, new_duration


def _frames_ev_long(ts, duration):
    """_frames_ev + _pad_past_gate — 20분 게이트를 통과하면서 원래 공백 구조는 보존한다."""
    all_ts, new_duration = _pad_past_gate(ts, duration)
    return _frames_ev(all_ts, new_duration)


class TestGapZoomPlan:
    def test_short_gap_one_midpoint(self):
        # 프레임 t=60·t=160 + duration=160 → 공백 60~160(100초) → 중점 1개 = 01:50
        # (20분 게이트를 통과시키려 160 뒤에 조밀한 꼬리를 붙인다 — _frames_ev_long)
        specs = evidence.gap_zoom_plan(_frames_ev_long([60.0, 160.0], 160.0))
        assert specs == ["01:50@1024"]

    def test_long_gap_two_points(self):
        # 프레임 없음 + duration=300 → 공백 0~300(300초) → 1/3·2/3 = 01:40, 03:20
        specs = evidence.gap_zoom_plan(_frames_ev_long([], 300.0))
        assert specs == ["01:40@1024", "03:20@1024"]

    def test_cap_prefers_long_gaps(self):
        # 조밀 버퍼(10초, 임계 90 이하라 공백 아님)와 공백(91~110초, 임계 90 초과)을
        # 번갈아 배치해 20개 공백을 만든다 → 상한 16으로 잘리되 긴 공백부터
        # (Task 7: 임계 60→90 상향으로 구간 크기를 70~89초에서 91~110초로 조정 —
        # 옛 70~89초는 새 임계(>90)에서 전부 공백 판정을 받지 못해 테스트가 깨진다)
        # 20개 구간 누적 길이가 이미 20분을 훌쩍 넘어 _pad_past_gate의 꼬리는
        # 붙지 않는다(20분 게이트는 자동으로 통과) — max_frames만 명시적으로 오버라이드해
        # 상한 16 자체는 여전히 선택 가능함을 확인한다(F2: 기본값은 12로 내려갔다).
        ts, cur = [], 0.0
        for i in range(20):
            cur += 10.0
            ts.append(cur)
            cur += 91.0 + i
            ts.append(cur)
        specs = evidence.gap_zoom_plan(_frames_ev_long(ts, cur), max_frames=16)
        assert len(specs) == 16

    def test_default_cap_is_twelve(self):
        """F2: max_frames 기본값이 16→12로 내려갔다 — 20개 공백이 있어도 인자 없이
        호출하면 12개로 잘린다(이전 리뷰의 "16→11" 주장은 오염된 캐시 기준이었고,
        실제 레버는 임계가 아니라 이 상한이라는 정정의 회귀 가드)."""
        ts, cur = [], 0.0
        for i in range(20):
            cur += 10.0
            ts.append(cur)
            cur += 91.0 + i
            ts.append(cur)
        specs = evidence.gap_zoom_plan(_frames_ev_long(ts, cur))
        assert len(specs) == 12

    def test_no_gaps_empty(self):
        # 신규 ②: 프레임이 조밀(전 간격 30초 ≤ 임계 90초)하면 공백이 없다
        specs = evidence.gap_zoom_plan(_frames_ev_long([30.0, 60.0, 90.0], 120.0))
        assert specs == []

    def test_boundary_gap_exactly_threshold_is_not_a_gap(self):
        # Task 7: 정확히 GAP_BACKFILL_THRESHOLD(90)초 간격은 공백이 아니다 — 비교가
        # 엄격 부등호(>)라 경계값 자체는 포함되지 않는다.
        ev = _frames_ev_long([90.0], 90.0)
        assert evidence._frame_gap_source(ev) == []
        assert evidence.gap_zoom_plan(ev) == []

    def test_boundary_gap_just_over_threshold_is_a_gap(self):
        # Task 7: 임계+1초(91초) 간격은 공백이다.
        ev = _frames_ev_long([91.0], 91.0)
        assert evidence._frame_gap_source(ev) == [{"start": 0.0, "end": 91.0}]
        assert evidence.gap_zoom_plan(ev) == ["00:45@1024"]

    def test_triggers_even_when_llm_gaps_empty(self):
        # 신규 ①(회귀 가드): LLM이 gaps를 0건 기록했어도(evidence.py의 이번 결함이 정확히
        # 이 상황) 프레임이 성기면 공백이 여전히 결정론적으로 계산된다.
        ev = _frames_ev_long([60.0, 160.0], 160.0)
        ev["gaps"] = []
        assert evidence.gap_zoom_plan(ev) == ["01:50@1024"]

    def test_duration_reversal_uses_frame_boundary_not_duration(self):
        """리뷰 F2 회귀 가드: video.duration이 마지막 프레임 t보다 작게 기록된 역전
        입력에서도 pts를 내림차순으로 끝내지 않는다 — duration은 마지막 프레임 t보다
        클 때만 끝점으로 붙는다. 여기서는 duration을 아예 버리고 프레임 경계(300)가
        끝점이 되어 공백 (60, 300) 하나만 나온다.

        (20분 게이트도 함께 통과시켜야 해서 원본 수치 60/300/160을 그대로 쓰지
        못한다 — duration을 1201로, 그리고 진짜 최댓값 프레임을 300 뒤에 조밀한
        꼬리로 1201보다 더 뒤까지 이어붙여 "duration(1201) < 실제 마지막 프레임"
        역전 관계를 유지한 채로 총 길이만 20분을 넘긴다. (60, 300) 공백 자체는
        건드리지 않는다.)"""
        # 300 뒤에 80초 간격(임계 90 미만이라 새 공백을 만들지 않는다) 꼬리를 이어붙여
        # 실제 마지막 프레임을 1201보다 뒤로 밀어낸다 — duration(1201)이 여전히
        # "마지막 프레임보다 작게 기록된 역전값"이 되도록. _pad_past_gate는 duration을
        # 먼저 프레임으로 꽂아버려(경계=1201) 300~1201 사이에 빈 꼬리를 남기므로 여기서는
        # 쓸 수 없다 — 300에서 직접 조밀한 꼬리를 만든다.
        tail, t = [], 300.0
        while t <= 1201.0:
            t += 80.0
            tail.append(t)
        ev = _frames_ev([60.0, 300.0] + tail, 1201.0)
        assert evidence._frame_gap_source(ev) == [{"start": 60.0, "end": 300.0}]
        # 240초 공백(≥180) → 1/3·2/3 지점 = 140(02:20), 220(03:40).
        # 요지: duration(1201) 근접 지점이 아니라 프레임 경계(300) 기준으로 계산되고,
        # 출력의 모든 지점이 실제 공백 (60, 300) 이내다.
        specs = evidence.gap_zoom_plan(ev)
        assert specs == ["02:20@1024", "03:40@1024"]
        for spec in specs:
            mm, ss = spec.split("@")[0].split(":")
            assert int(mm) * 60 + int(ss) <= 300.0

    def test_non_dict_frame_elements_are_skipped(self):
        """F3(사전 미선언 append-only 위반 복구): aa04656에서 공백 산출원이
        ev["gaps"]에서 provenance.frames로 교체되며, 옛 test_non_dict_gap_skipped
        (비dict 원소가 섞여도 크래시 없이 스킵)가 무테스트로 방치됐다. 프레임 기반
        입력에 맞춘 등가 테스트로 복원한다 — map/zoom 리스트에 비dict 원소나 t가
        비수치인 dict 원소가 섞여도 크래시 없이 스킵하고, 유효 프레임만으로 공백을
        계산한다."""
        ev = {
            "video": {"duration": 1300.0},
            "provenance": {"frames": {
                "map": [
                    "산문 노트",             # 비dict 원소
                    123,                      # 비dict 원소
                    {"t": 60.0},
                    {"t": "모름"},            # t가 비수치
                    {"no_t_key": True},       # t 키 없음
                    {"t": 1300.0},
                ],
                "zoom": [None, ["also", "not", "a", "dict"]],  # 비dict 원소
            }},
        }
        # 유효 프레임은 t=60.0·1300.0뿐 → 공백 60~1300(1240초, 20분 게이트도 통과)
        assert evidence._frame_gap_source(ev) == [{"start": 60.0, "end": 1300.0}]
        assert evidence.gap_zoom_plan(ev) != []

    def test_short_video_gate_blocks_backfill_regardless_of_gap_size(self):
        """F1: SKILL.md 7.5절 산문("영상 20분 초과 시에만")만으로는 신뢰할 수 없다 —
        최종 리뷰 실측에서 11분급(687초) 영상 형상도 --gap-plan이 1~4개 지점을
        출력했다. duration<=GAP_BACKFILL_MIN_DURATION(1200초=20분)이면 공백이
        아무리 커도(여기서는 프레임이 하나도 없어 공백이 영상 전체 687초) 코드가
        무조건 빈 리스트를 반환한다."""
        ev = _frames_ev([], 687.0)
        assert evidence._frame_gap_source(ev) == []
        assert evidence.gap_zoom_plan(ev) == []

    def test_just_over_twenty_minutes_passes_gate(self):
        """duration이 게이트(1200초)를 1초라도 넘기면(1201초) 정상적으로 공백을
        산출한다 — 게이트 경계값 자체 회귀 가드."""
        ev = _frames_ev([], 1201.0)
        specs = evidence.gap_zoom_plan(ev)
        assert specs != []

    def test_non_numeric_duration_returns_empty_list(self):
        """F1: duration이 비수치(손상된 메타데이터)면 20분 게이트를 판정할 수 없다 —
        float() 변환 실패를 크래시로 흘리지 않고 빈 리스트로 안전하게 처리한다
        (비용 불변 원칙: 판정 불가 시 기본값은 "보강 없음")."""
        ev = _frames_ev([60.0, 5000.0], "알수없음")
        assert evidence._frame_gap_source(ev) == []
        assert evidence.gap_zoom_plan(ev) == []


class TestGapZoomPlanActivity:
    def _curve(self, length, peaks):
        c = [0.0] * length
        for sec, val in peaks.items():
            c[sec] = val
        return c

    def test_peak_beats_midpoint(self):
        # 프레임 t=60·t=160 + duration=160 → 공백 60~160, 피크 @150(값 90) → 02:30
        ev = _frames_ev_long([60.0, 160.0], 160.0)
        curve = self._curve(200, {150: 90.0, 110: 10.0})
        assert evidence.gap_zoom_plan(ev, activity_curve=curve) == ["02:30@1024"]

    def test_long_gap_two_peaks_with_separation(self):
        # 프레임 없음 + duration=300 → 공백 0~300, 피크 @100(90)·@110(80)·@250(70)
        # → 110은 100과 45초 미만이라 250 선택
        ev = _frames_ev_long([], 300.0)
        curve = self._curve(400, {100: 90.0, 110: 80.0, 250: 70.0})
        specs = evidence.gap_zoom_plan(ev, activity_curve=curve)
        assert sorted(specs) == ["01:40@1024", "04:10@1024"]

    def test_zero_curve_falls_back_to_midpoint(self):
        ev = _frames_ev_long([60.0, 160.0], 160.0)
        assert evidence.gap_zoom_plan(ev, activity_curve=[0.0] * 200) == ["01:50@1024"]

    def test_none_curve_keeps_legacy(self):
        ev = _frames_ev_long([], 300.0)
        assert evidence.gap_zoom_plan(ev, activity_curve=None) == ["01:40@1024", "03:20@1024"]

    def test_margin_excludes_gap_edges(self):
        # 경계 3초 이내 피크는 제외 — 공백 60~160, 피크 @61(99)은 무시하고 @120(50) 선택
        ev = _frames_ev_long([60.0, 160.0], 160.0)
        curve = self._curve(200, {61: 99.0, 120: 50.0})
        assert evidence.gap_zoom_plan(ev, activity_curve=curve) == ["02:00@1024"]

    def test_fractional_gap_margin_uses_ceil_floor(self):
        """리뷰 F1: 공백 경계가 소수초(100.5~200.5)면 int(s)+3은 실제 여유가 3초 미만인
        지점을 통과시킨다. @103(99)은 시작에서 2.5초(103-100.5)뿐이라 마진 미달로
        제외되어야 하고, @150(50)이 선택돼야 한다.
        버퍼 프레임 t=60.0을 추가로 넣어 0~100.5 구간이(0~60.0, 60.0~100.5 모두 ≤60초)
        별도 공백으로 잡히지 않게 하고, 목표 공백은 100.5~200.5 하나만 남긴다."""
        ev = _frames_ev_long([60.0, 100.5, 200.5], 200.5)
        curve = self._curve(250, {103: 99.0, 150: 50.0})
        assert evidence.gap_zoom_plan(ev, activity_curve=curve) == ["02:30@1024"]


def test_gap_plan_falls_back_on_encoding_corrupt_signals_json(tmp_path):
    """리뷰 F2: signals.json이 UTF-8로 디코드 불가능(UnicodeDecodeError)해도 크래시
    없이 레거시 중점/삼분점 폴백으로 조용히 진행한다 — exit 0, stderr 비어 있음."""
    evidence.save(tmp_path, _frames_ev_long([60.0, 160.0], 160.0))
    (tmp_path / "signals.json").write_bytes(b"\xff\xfe\x00\x01broken-not-utf8")
    p = _run([str(tmp_path), "--gap-plan"])
    assert p.returncode == 0
    assert p.stderr == ""
    assert p.stdout.strip() == "01:50@1024"


def test_gap_plan_alone_is_fail_soft_when_evidence_missing(tmp_path):
    """--gap-plan만 단독 요청됐을 때 evidence.json 부재는 fail-soft(NOTE + exit 0)로
    처리한다 — 보강은 선택 단계라 파이프라인을 끊지 않는다."""
    p = _run([str(tmp_path), "--gap-plan"])
    assert p.returncode == 0
    assert "NOTE" in p.stderr


def test_gap_plan_with_other_action_hits_hard_gate_when_evidence_missing(tmp_path):
    """--gap-plan이 --render 등 다른 액션과 한 호출에 섞이면 evidence.json 부재를
    조용히 넘기지 않는다 — 그렇지 않으면 --render가 통보 없이 스킵된 채 exit 0으로
    끝나 파이프라인이 성공으로 오판하는 조용한 실패가 된다. 이 경우는 기존
    하드게이트(evidence.json 부재 시 비정상 종료)와 동일하게 흘러가야 한다."""
    p = _run([str(tmp_path), "--gap-plan", "--render"])
    assert p.returncode == 2
    assert "ERROR" in p.stderr


# ── 관용 검증 이식 (dense 브랜치 8346d04·8678bbd 이식, F-헤더·복수파일은 범위 밖) ──
#
# 사용자 정책 재정 인용(dense 브랜치): "완전성 > 문자 정밀도 — 약간의 오타는 허용,
# 전량거부·재시도 루프가 비용의 주범." 낱줄 하나의 형식 오류가 배치 전체를 죽이면
# 안 된다. K·C(실제 지식을 나르는 항목)만 20% 드롭율 게이트를 두고, V/T/G는 항상
# 관용한다(드롭 카운트만 남긴다). F-헤더·복수 파일 연접은 dense 전용이라 이번
# 이식 범위 밖이다 — 기존 단일 파일 --from-lines 호출·6필드 V 포맷은 무변경이
# 계약이다.

def test_expand_lines_drops_malformed_v_and_counts():
    text = ("V\tui\t1.0\tf1.jpg\thigh\t좋은값\n"
            "V\tui\t2.0\tf2.jpg\thigh\n"       # value 필드 누락(5필드) -> 드롭
            "V\tui\t3.0\tf3.jpg\tmedium\t다른좋은값\n")
    p = evidence.expand_lines(text)
    assert len(p["visual_evidence"]) == 2
    assert p["_line_stats"]["attempted"]["V"] == 3
    assert p["_line_stats"]["dropped"]["V"] == 1


def test_expand_lines_vn_position_preserved_when_middle_v_is_dropped():
    """드롭된 V도 vn을 소모해야 한다 — 하류 K/C의 로컬 v# 참조는 위치 기준이라,
    드롭이 번호를 밀면 드롭과 무관한 뒤쪽 V들의 id가 전부 어긋난다."""
    text = ("V\tui\t1.0\tf1.jpg\thigh\t첫값\n"      # v1
            "V\tui\t2.0\tf2.jpg\thigh\n"            # 필드 부족 -> 드롭(그래도 vn 소모)
            "V\tui\t3.0\tf3.jpg\thigh\t셋째값\n"    # v3이어야 한다(v2가 아니라)
            "K\tconcept\t3.0\tv3\t셋째값 참조\n")
    p = evidence.expand_lines(text)
    assert [v["id"] for v in p["visual_evidence"]] == ["v1", "v3"]
    assert p["knowledge_items"][0]["evidence"] == [{"source": "frame", "ref": "v3"}]
    assert p["_line_stats"]["dropped"]["V"] == 1


def test_expand_lines_drops_malformed_k_and_counts():
    text = ("K\tcommand\t1.0\tv1\t좋은 명령\n"
            "K\tcommand\t2.0\t\n"        # content 필드 없음 -> 드롭
            "K\tcommand\t3.0\tv1\t또 좋은 명령\n")
    p = evidence.expand_lines(text)
    assert len(p["knowledge_items"]) == 2
    assert p["_line_stats"]["attempted"]["K"] == 3
    assert p["_line_stats"]["dropped"]["K"] == 1


def test_expand_lines_unknown_record_kind_still_fails_loud():
    """관용 드롭은 T/V/K/C/G 안의 낱줄 형식 오류에만 적용된다 — 완전히 다른 레코드
    종류는 여전히 즉시 거부한다(기존 test_expand_lines_rejects_unknown_record와
    동일 계약, 관용 드롭 도입 후에도 유지되는지 별도 고정)."""
    import pytest as _pytest
    with _pytest.raises(ValueError, match=r"1행"):
        evidence.expand_lines("Q\t알수없음\n")


def test_expand_lines_well_formed_batch_has_zero_drops_in_stats():
    """기존 정상 배치(_LINES)는 드롭 0건으로 집계돼야 한다 — 하위호환 회귀 가드."""
    p = evidence.expand_lines(_LINES)
    assert p["_line_stats"]["dropped"] == {"T": 0, "V": 0, "K": 0, "C": 0, "G": 0}
    assert p["_line_stats"]["attempted"] == {"T": 1, "V": 1, "K": 1, "C": 1, "G": 1}


# ── CLI: 관용 드롭 + K/C 20% 게이트 ─────────────────────────────────────────

def test_cli_from_lines_lenient_batch_with_v_typos_exits_zero_with_dropped_count(tmp_path):
    """핵심 계약: V 오타 3줄이 섞여도 전량거부(exit 2)하지 않고 나머지를 병합한 뒤
    exit 0 + stdout `DROPPED 3`을 보고한다."""
    n_frames = 100
    frame_names = [f"frame{i:03d}.jpg" for i in range(n_frames)]
    ev = evidence.register_frames(_skel(), frame_names)
    evidence.save(tmp_path, ev)

    typo_frames = {10, 50, 90}
    lines = []
    for i, name in enumerate(frame_names):
        if i in typo_frames:
            lines.append(f"V\tui\t{float(i)}\t{name}\thigh\n")  # value 필드 누락 -> 드롭
        else:
            lines.append(f"V\tui\t{float(i)}\t{name}\thigh\tvalue-{i}\n")
    text = "".join(lines)

    patch_file = tmp_path / "patch.lines"
    patch_file.write_text(text, encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "DROPPED 3" in p.stdout

    merged = evidence.load(tmp_path)
    assert len(merged["visual_evidence"]) == n_frames - 3


def test_cli_from_lines_dropped_count_matches_actual_drops(tmp_path):
    """stdout의 DROPPED n이 실제 드롭 수와 정확히 일치하는지 작은 배치로 별도 고정."""
    ev = evidence.register_frames(_skel(), ["ok.jpg"])
    evidence.save(tmp_path, ev)
    text = (
        "V\tui\t1.0\tok.jpg\thigh\t정상값1\n"
        "V\tui\t2.0\tok.jpg\thigh\n"        # 5필드 -> 드롭 1
        "V\tui\t3.0\tok.jpg\n"              # 4필드 -> 드롭 2
        "V\tui\t4.0\tok.jpg\thigh\t정상값2\n"
        "V\ta\tb\tc\td\te\n"                # timestamp 비수치 -> 드롭 3
    )
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text(text, encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "DROPPED 3" in p.stdout

    merged = evidence.load(tmp_path)
    assert len(merged["visual_evidence"]) == 2


def test_cli_from_lines_k_drop_rate_over_20_percent_rejects_whole_batch(tmp_path):
    """K 드롭율이 20%를 넘으면(여기서는 30%) 관용하지 않는다 — 산발적 오타가 아니라
    파일 전체가 잘못된 규약이라는 신호이므로 기존처럼 배치 전체를 거부한다."""
    evidence.save(tmp_path, _skel())
    n_k, n_bad = 20, 6  # 30%
    lines = []
    for i in range(n_k):
        if i < n_bad:
            lines.append(f"K\tcommand\t{float(i)}\t")  # refs·content 누락 -> 드롭
        else:
            lines.append(f"K\tcommand\t{float(i)}\tt0\t명령 {i}")
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 2, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "INVALID" in p.stderr
    assert "knowledge_items" in p.stderr
    assert evidence.load(tmp_path)["knowledge_items"] == []


def test_cli_from_lines_c_drop_rate_over_20_percent_rejects_whole_batch(tmp_path):
    """K와 대칭 계약 — C도 같은 20% 게이트를 공유한다."""
    evidence.save(tmp_path, _skel())
    n_c, n_bad = 10, 4  # 40%
    lines = []
    for i in range(n_c):
        if i < n_bad:
            lines.append(f"C\t{float(i)}\t")  # refs·claim 누락 -> 드롭
        else:
            lines.append(f"C\t{float(i)}\tt0\t주장 {i}")
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 2, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "INVALID" in p.stderr
    assert "claims" in p.stderr
    assert evidence.load(tmp_path)["claims"] == []


def test_cli_from_lines_kc_drop_rate_at_or_below_20_percent_still_merges(tmp_path):
    """20% 경계값 자체는 게이트를 넘지 않는다(엄격 부등호 `>`) — 정확히 20%는 관용."""
    evidence.save(tmp_path, _skel())
    n_k, n_bad = 10, 2  # 정확히 20%
    lines = []
    for i in range(n_k):
        if i < n_bad:
            lines.append(f"K\tcommand\t{float(i)}\t")
        else:
            lines.append(f"K\tcommand\t{float(i)}\tt0\t명령 {i}")
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "DROPPED 2" in p.stdout
    assert len(evidence.load(tmp_path)["knowledge_items"]) == 8


def test_cli_dropped_v_referenced_by_k_causes_validate_rejection(tmp_path):
    """드롭된 V(2번째, v2 자리)를 K가 참조하면 그 v-id는 실재하지 않으므로
    validate()가 exit 2로 배치 전체를 거부한다 — 위치 오배선이 아니라 의도된
    fail-loud(드롭 = 그 id가 아예 존재하지 않게 되는 것)."""
    ev = evidence.register_frames(_skel(), ["f1.jpg", "f3.jpg"])
    evidence.save(tmp_path, ev)
    text = (
        "V\tui\t1.0\tf1.jpg\thigh\t첫값\n"      # v1
        "V\tui\t2.0\tf2.jpg\thigh\n"            # 필드 부족 -> 드롭(v2 자리)
        "V\tui\t3.0\tf3.jpg\thigh\t셋째값\n"    # v3
        "K\tconcept\t3.0\tv2\t드롭된 값 참조\n"  # 존재하지 않는 v2 참조
    )
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text(text, encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 2, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "v2" in p.stderr
    assert "visual_evidence" in p.stderr
    assert evidence.load(tmp_path)["knowledge_items"] == []


def test_cli_surviving_v_ids_referenced_by_k_merges_successfully(tmp_path):
    """같은 드롭 구조에서 살아남은 v1·v3만 참조하면(드롭된 v2는 참조하지 않음)
    위치 보존이 정확해 exit 0으로 정상 병합된다."""
    ev = evidence.register_frames(_skel(), ["f1.jpg", "f3.jpg"])
    evidence.save(tmp_path, ev)
    text = (
        "V\tui\t1.0\tf1.jpg\thigh\t첫값\n"      # v1
        "V\tui\t2.0\tf2.jpg\thigh\n"            # 필드 부족 -> 드롭(v2 자리)
        "V\tui\t3.0\tf3.jpg\thigh\t셋째값\n"    # v3
        "K\tconcept\t1.0\tv1\t첫값 참조\n"
        "K\tconcept\t3.0\tv3\t셋째값 참조\n"
    )
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text(text, encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "DROPPED 1" in p.stdout

    merged = evidence.load(tmp_path)
    assert {v["id"] for v in merged["visual_evidence"]} == {"v1", "v3"}
    refs = {k["content"]: k["evidence"][0]["ref"] for k in merged["knowledge_items"]}
    assert refs == {"첫값 참조": "v1", "셋째값 참조": "v3"}


def test_cli_from_lines_single_file_still_backward_compatible(tmp_path):
    """관용 드롭·20% 게이트 도입 이후에도 기존 단일 파일 --from-lines 호출은
    완전히 하위 호환이다 — 기존 T/V/K/C/G 전량 fixture(_LINES)가 그대로 병합된다."""
    tr = {"source": "captions", "lang": "ko", "dupes_removed": 0, "flags": [],
          "segments": [{"start": float(i), "text": f"s{i}"} for i in range(20)]}
    ev = evidence.build_skeleton(_info(), _sig(), tr, [], "u")
    ev = evidence.register_frames(ev, ["t0212_1024.jpg"])
    evidence.save(tmp_path, ev)
    lines = tmp_path / "patch.lines"
    lines.write_text(_LINES, encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(lines)])
    assert p.returncode == 0, p.stderr

    merged = evidence.load(tmp_path)
    assert merged["visual_evidence"][0]["value"] == "16.3x 표시"
    assert merged["knowledge_items"][0]["content"] == "pip install -U yt-dlp"


# ── id_offset 수정: len() 기반 -> 기존 v-id 최대 숫자 기반 (스케일 프리모템 ③) ──

def test_cli_from_lines_id_offset_survives_drop_created_gap(tmp_path):
    """관용 드롭이 v-id 결번(v1·v3 생존, v2 드롭)을 만든 뒤 후속 --from-lines
    배치가 새 V를 추가하는 상황 — len(visual_evidence)(=2) 기반 오프셋은 새 id를
    v3으로 매겨 기존 v3과 충돌한다(수정 전 버그). 최대 숫자 기반 오프셋(=3)은
    v4로 매겨 충돌 없이 병합돼야 한다."""
    ev = evidence.register_frames(_skel(), ["f1.jpg", "f3.jpg", "f4.jpg"])
    evidence.save(tmp_path, ev)

    first_batch = (
        "V\tui\t1.0\tf1.jpg\thigh\t첫값\n"      # v1
        "V\tui\t2.0\tf2.jpg\thigh\n"            # 필드 부족 -> 드롭(v2 자리, 결번)
        "V\tui\t3.0\tf3.jpg\thigh\t셋째값\n"    # v3
    )
    first_file = tmp_path / "first.lines"
    first_file.write_text(first_batch, encoding="utf-8")
    p1 = _run([str(tmp_path), "--from-lines", str(first_file)])
    assert p1.returncode == 0, f"stdout={p1.stdout}\nstderr={p1.stderr}"
    after_first = evidence.load(tmp_path)
    assert {v["id"] for v in after_first["visual_evidence"]} == {"v1", "v3"}

    second_batch = "V\tui\t4.0\tf4.jpg\thigh\t넷째값\n"
    second_file = tmp_path / "second.lines"
    second_file.write_text(second_batch, encoding="utf-8")
    p2 = _run([str(tmp_path), "--from-lines", str(second_file)])
    assert p2.returncode == 0, f"stdout={p2.stdout}\nstderr={p2.stderr}"

    merged = evidence.load(tmp_path)
    ids = [v["id"] for v in merged["visual_evidence"]]
    assert ids == ["v1", "v3", "v4"], ids  # v3 재사용(충돌) 없이 v4로 이어져야 한다
    assert len(set(ids)) == len(ids), "중복 id 없어야 한다"
    assert evidence.validate(merged) == []


def test_expand_lines_id_offset_param_is_max_id_not_count():
    """단위 수준 회귀 가드: id_offset 파라미터에 "결번 있는 최대 숫자"(예: 3, 항목은
    2개뿐)를 넘기면 새 V는 v4부터 시작해야 한다 — len() 기반 오프셋(2)이었다면
    v3이 되어 기존 v3과 충돌했을 것이다."""
    p = evidence.expand_lines("V\tui\t9.0\tf9.jpg\thigh\t새값\n", id_offset=3)
    assert p["visual_evidence"][0]["id"] == "v4"


# ── Task 1b: 게이트 실패 흡수 (실측 통합 게이트, nHcfoHOW4uA, 2026-08-21) ──
#
# ① 비전(haiku)이 V type에 enum 밖 `diagram`을 17건 출력 → merge가 17건 전량
#   거부(지식 손실 + 수정 왕복 3회 = 비용 5배). ② 합성(sonnet)이 K 5필드에
# confidence를 refs와 content 사이에 끼워 6필드로 출력 → K 100% 드롭(사실상
# 지식 손실 — 원 코드는 confidence를 content로 오배선해 조용히 값을 날린다).
# 관용 정책 일관 적용: 라벨 오류로 실제 관측을 버리지 않는다 — 드롭 대신
# 정규화하고, 정규화 건수는 조용히 삼키지 않고 반드시 보고한다.

def test_expand_lines_normalizes_out_of_enum_v_type_diagram_to_chart():
    """실측 게이트 회귀 고정: diagram 17건이 전량 거부되지 않고 chart로 정규화돼
    생존해야 한다 — 드롭 0, normalized 17."""
    lines = "".join(
        f"V\tdiagram\t{float(i)}\tf{i}.jpg\thigh\t다이어그램 값{i}\n" for i in range(17)
    )
    p = evidence.expand_lines(lines)
    assert len(p["visual_evidence"]) == 17
    assert all(v["type"] == "chart" for v in p["visual_evidence"])
    assert p["_line_stats"]["dropped"]["V"] == 0
    assert p["_line_stats"]["normalized"]["V"] == 17


def test_expand_lines_v_type_aliases_and_unknown_fallback_to_other():
    """별칭 맵(diagram/graph->chart, terminal->code, screenshot->ui)에 없는 미지
    type은 드롭하지 않고 other로 강제한다 — 어느 쪽이든 드롭하지 않는다."""
    lines = (
        "V\tgraph\t1.0\tf1.jpg\thigh\t그래프값\n"
        "V\tterminal\t2.0\tf2.jpg\thigh\t터미널값\n"
        "V\tscreenshot\t3.0\tf3.jpg\thigh\t스크린샷값\n"
        "V\tmystery\t4.0\tf4.jpg\thigh\t미지값\n"
    )
    p = evidence.expand_lines(lines)
    types = [v["type"] for v in p["visual_evidence"]]
    assert types == ["chart", "code", "ui", "other"]
    assert p["_line_stats"]["dropped"]["V"] == 0
    assert p["_line_stats"]["normalized"]["V"] == 4


def test_expand_lines_v_type_already_valid_is_not_counted_as_normalized():
    """이미 유효한 enum 값(예: ui)은 정규화 대상이 아니다 — normalized 카운트가
    거짓으로 올라가면 안 된다."""
    p = evidence.expand_lines("V\tui\t1.0\tf1.jpg\thigh\t정상값\n")
    assert p["visual_evidence"][0]["type"] == "ui"
    assert p["_line_stats"]["normalized"]["V"] == 0


def test_expand_lines_k_six_field_stray_confidence_normalizes_to_five():
    """실측 게이트 회귀 고정: K 5필드(K/type/초/refs/content)에 confidence가
    refs와 content 사이에 끼어 6필드가 되면 — 5번째 필드(0-기준 4)가 정확히
    high|medium|low일 때만 그 필드를 제거하고 5필드로 정상 파싱한다."""
    line = "K\tsetting\t12.5\tv1\thigh\tCUDA 12.6 필요\n"
    p = evidence.expand_lines(line)
    assert len(p["knowledge_items"]) == 1
    item = p["knowledge_items"][0]
    assert item["type"] == "setting"
    assert item["timestamp"] == 12.5
    assert item["content"] == "CUDA 12.6 필요"
    assert p["_line_stats"]["dropped"]["K"] == 0
    assert p["_line_stats"]["normalized"]["K"] == 1


def test_expand_lines_k_six_field_non_confidence_fifth_field_still_dropped():
    """5번째 필드가 high|medium|low가 아니면 정규화 대상이 아니다 — 그 외 필드
    수 오류는 기존 관용 규칙(드롭+보고)을 그대로 유지한다."""
    text = (
        "K\tcommand\t1.0\tv1\t좋은명령\n"           # 정상 5필드
        "K\tsetting\t2.0\tv1\t뭔가\t추가필드\n"     # 6필드지만 5번째가 confidence 아님 -> 드롭
    )
    p = evidence.expand_lines(text)
    assert len(p["knowledge_items"]) == 1
    assert p["knowledge_items"][0]["content"] == "좋은명령"
    assert p["_line_stats"]["attempted"]["K"] == 2
    assert p["_line_stats"]["dropped"]["K"] == 1
    assert p["_line_stats"]["normalized"]["K"] == 0


def test_cli_from_lines_normalized_count_reported_in_merged_line(tmp_path):
    """조용한 변조 금지: 정규화가 일어나면 stdout의 `MERGED ... DROPPED n`에
    `NORMALIZED n`이 병기돼야 한다."""
    ev = evidence.register_frames(_skel(), ["f1.jpg", "f2.jpg"])
    evidence.save(tmp_path, ev)
    text = (
        "V\tdiagram\t1.0\tf1.jpg\thigh\t값1\n"   # 별칭 정규화 -> chart
        "V\tui\t2.0\tf2.jpg\thigh\t값2\n"        # 정상, 정규화 아님
    )
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text(text, encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "DROPPED 0" in p.stdout
    assert "NORMALIZED 1" in p.stdout

    merged = evidence.load(tmp_path)
    assert {v["type"] for v in merged["visual_evidence"]} == {"chart", "ui"}


def test_cli_from_lines_normalized_absent_from_stdout_when_zero(tmp_path):
    """정규화 0건이면 MERGED 라인에 NORMALIZED가 아예 나오지 않는다 — 무조건
    붙이는 회귀(0건에도 잡음 섞인 보고)를 잡는다."""
    ev = evidence.register_frames(_skel(), ["f1.jpg"])
    evidence.save(tmp_path, ev)
    text = "V\tui\t1.0\tf1.jpg\thigh\t값1\n"
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text(text, encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "DROPPED 0" in p.stdout
    assert "NORMALIZED" not in p.stdout


# ── 정보량 비례 K 예산 (info-budget 라운드, 2026-08-22) ─────────────────────
# 시간 비례 천장(구 max(30, 분당2.5))을 폐기하고 자막 문자수(CJK 언어보정)·
# V라인 수로 계산한다. 회귀 수치는 docs/superpowers/plans/2026-08-22-info-budget.md의
# 보존 캐시 12영상 보정표에서 그대로 가져온다 — 실제 캐시(pwGeWRlrU10·
# 7MEsgHKQGLg)의 transcript.json 문자수와 정확히 일치함을 별도 확인했다.

def _make_transcript(cache_dir, chars: int, cjk: bool):
    unit = "가나다라마바사아자차카타파하" if cjk else "the quick brown fox jumps over lazy dog "
    text = (unit * (chars // len(unit) + 1))[:chars]
    tr = {"source": "captions", "lang": "ko" if cjk else "en",
          "segments": [{"start": 0.0, "text": text}]}
    (Path(cache_dir) / "transcript.json").write_text(
        json.dumps(tr, ensure_ascii=False), encoding="utf-8")


def _make_vision_lines(cache_dir, n: int, name="vision-map.lines"):
    lines = "\n".join(f"V\tui\t{i}.0\tf{i}.jpg\thigh\tval{i}" for i in range(n))
    (Path(cache_dir) / name).write_text(lines, encoding="utf-8")


def test_k_budget_ko_dense_regression(tmp_path):
    """실측 회귀 1(플랜 보정표): 7MEsgHKQGLg(ko) 5363자/94V → 천장 59·하한 30."""
    _make_transcript(tmp_path, 5363, cjk=True)
    _make_vision_lines(tmp_path, 94)
    assert evidence.k_budget(tmp_path) == (30, 59)


def test_k_budget_en_dense_regression(tmp_path):
    """실측 회귀 2: pwGeWRlrU10(en) 16709자/116V → 천장 77·하한 38."""
    _make_transcript(tmp_path, 16709, cjk=False)
    _make_vision_lines(tmp_path, 116)
    assert evidence.k_budget(tmp_path) == (38, 77)


def test_k_budget_en_sparse_hits_ceiling_floor(tmp_path):
    """실측 회귀 3: 0chZFIZLR_0(en) 4333자/0V → 공식값(12.38)이 하한선 15에
    못 미쳐 천장이 15로 바닥을 친다 · 하한 8."""
    _make_transcript(tmp_path, 4333, cjk=False)
    assert evidence.k_budget(tmp_path) == (8, 15)


def test_k_budget_falls_back_when_no_input_at_all(tmp_path):
    """transcript.json도 vision-*.lines도 전혀 없으면(캐시 갓 생성 등) 폭이
    아니라 부드러운 기본값 (8, 15)로 물러난다 — 플랜 Task 1의 명시 폴백."""
    assert evidence.k_budget(tmp_path) == (8, 15)


def test_k_budget_malformed_transcript_json_falls_back(tmp_path):
    """transcript.json이 파손돼도(JSON 파싱 불가) 크래시하지 않고 chars=0으로
    폴백한다 — --k-budget은 다른 서브커맨드와 독립적으로 fail-soft해야 한다."""
    (tmp_path / "transcript.json").write_text("{not valid json", encoding="utf-8")
    assert evidence.k_budget(tmp_path) == (8, 15)


def test_k_budget_language_correction_raises_ceiling_for_cjk(tmp_path):
    """같은 문자수·V=0이라도 CJK 비율 > 0.2(L=150)면 L=350(영어)보다 천장이
    높아야 한다 — 한국어 문자당 정보밀도가 2배 이상이라는 플랜 설계 전제."""
    ko_dir, en_dir = tmp_path / "ko", tmp_path / "en"
    ko_dir.mkdir()
    en_dir.mkdir()
    _make_transcript(ko_dir, 6000, cjk=True)
    _make_transcript(en_dir, 6000, cjk=False)
    _, ko_ceiling = evidence.k_budget(ko_dir)
    _, en_ceiling = evidence.k_budget(en_dir)
    assert ko_ceiling > en_ceiling


def test_k_budget_floor_is_ceiling_halved_and_rounded(tmp_path):
    _make_transcript(tmp_path, 16709, cjk=False)
    _make_vision_lines(tmp_path, 116)
    floor, ceiling = evidence.k_budget(tmp_path)
    assert floor == round(ceiling * 0.5)


def test_cli_k_budget_prints_kfloor_kceiling(tmp_path):
    _make_transcript(tmp_path, 16709, cjk=False)
    _make_vision_lines(tmp_path, 116)
    p = _run([str(tmp_path), "--k-budget"])
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == "KFLOOR 38 KCEILING 77"


def test_cli_k_budget_alone_is_fail_soft_when_evidence_missing(tmp_path):
    """--k-budget만 단독 요청되면 evidence.json 부재와 무관하게 성공한다 —
    "다른 서브커맨드와 독립적으로 동작해야 한다"(플랜 Task 1)의 CLI 단(段)."""
    p = _run([str(tmp_path), "--k-budget"])
    assert p.returncode == 0
    assert "KFLOOR 8 KCEILING 15" in p.stdout
    assert p.stderr == ""


def test_cli_k_budget_with_other_action_still_hits_hard_gate(tmp_path):
    """다른 액션(--render)과 한 호출에 섞이면 evidence.json 부재 하드게이트는
    기존과 동일하게 적용된다 — k-budget 결과는 이미 stdout에 나갔어도 전체
    exit code는 실패(2)를 유지해 조용한 스킵을 만들지 않는다."""
    p = _run([str(tmp_path), "--k-budget", "--render"])
    assert "KFLOOR" in p.stdout
    assert p.returncode == 2
    assert "ERROR" in p.stderr


# ── Task 2: 합성 K/C 라인의 타임스탬프 자리 변이 복구 (info-budget 라운드,
# 2026-08-22) ────────────────────────────────────────────────────────────────
# 실측 3연속 게이트, 매번 다른 변이·매번 100% 드롭 → INVALID → 왕복:
#   변이1: K 6필드, confidence가 refs·content 사이에 낌 (이미 흡수됨, 위 Task 1b)
#   변이2: confidence가 timestamp 자리에 들어옴 (K\ttype\thigh\trefs\tcontent)
#   변이3: timestamp 필드가 통째로 빠짐 (K\ttype\trefs\tcontent — 4필드)
# 두 변이 모두 드롭 대신 복구한다. 복구된 timestamp는 refs에서 유도한다(가짜
# 값 금지) — 첫 v#가 같은 배치 V로 풀리면 그 timestamp, 없고 첫 ref가 t#이면
# t_times(자막 세그먼트 시작 시각)에서, 둘 다 불가하면 기존대로 드롭한다.

def test_expand_lines_k_variant2_confidence_in_timestamp_slot_recovers_from_v_ref():
    """변이2: K의 timestamp 자리에 confidence 단어가 들어와도 드롭 대신 v1의
    timestamp로 복구돼 생존해야 한다."""
    text = ("V\tui\t50.0\tf1.jpg\thigh\t화면값\n"
            "K\tsetting\thigh\tv1\tCUDA 설정\n")
    p = evidence.expand_lines(text)
    assert len(p["knowledge_items"]) == 1
    k = p["knowledge_items"][0]
    assert k["type"] == "setting"
    assert k["timestamp"] == 50.0
    assert k["content"] == "CUDA 설정"
    assert k["evidence"] == [{"source": "frame", "ref": "v1"}]
    assert p["_line_stats"]["dropped"]["K"] == 0
    assert p["_line_stats"]["normalized"]["K"] == 1


def test_expand_lines_k_variant3_missing_timestamp_recovers_from_v_ref():
    """변이3: K의 timestamp 필드가 통째로 빠져도(4필드) v1의 timestamp로
    복구돼 생존해야 한다."""
    text = ("V\tui\t50.0\tf1.jpg\thigh\t화면값\n"
            "K\tsetting\tv1\tCUDA 설정\n")
    p = evidence.expand_lines(text)
    assert len(p["knowledge_items"]) == 1
    k = p["knowledge_items"][0]
    assert k["timestamp"] == 50.0
    assert k["content"] == "CUDA 설정"
    assert p["_line_stats"]["dropped"]["K"] == 0
    assert p["_line_stats"]["normalized"]["K"] == 1


def test_expand_lines_c_variant2_confidence_in_timestamp_slot_recovers_from_v_ref():
    text = ("V\tui\t77.0\tf1.jpg\thigh\t화면값\n"
            "C\thigh\tv1\t주장내용\n")
    p = evidence.expand_lines(text)
    assert len(p["claims"]) == 1
    c = p["claims"][0]
    assert c["timestamp"] == 77.0
    assert c["claim"] == "주장내용"
    assert c["evidence"] == [{"source": "frame", "ref": "v1"}]
    assert p["_line_stats"]["dropped"]["C"] == 0
    assert p["_line_stats"]["normalized"]["C"] == 1


def test_expand_lines_c_variant3_missing_timestamp_recovers_from_v_ref():
    text = ("V\tui\t77.0\tf1.jpg\thigh\t화면값\n"
            "C\tv1\t주장내용\n")
    p = evidence.expand_lines(text)
    assert len(p["claims"]) == 1
    c = p["claims"][0]
    assert c["timestamp"] == 77.0
    assert c["claim"] == "주장내용"
    assert p["_line_stats"]["dropped"]["C"] == 0
    assert p["_line_stats"]["normalized"]["C"] == 1


def test_expand_lines_c_variant2_preserves_conflict_field_after_recovery():
    """복구 후에도 꼬리의 conflict= 필드는 그대로 살아야 한다."""
    text = ("V\tui\t77.0\tf1.jpg\thigh\t화면값\n"
            "C\thigh\tv1\t주장내용\tconflict=16배=>16.3x\n")
    p = evidence.expand_lines(text)
    c = p["claims"][0]
    assert c["conflict"] == {"transcript": "16배", "screen": "16.3x"}


def test_expand_lines_k_variant3_derives_timestamp_from_t_ref_when_t_times_given():
    """v#가 없고 첫 ref가 t#이면 t_times(자막 세그먼트 시작 시각)에서 유도한다."""
    text = "K\tconcept\tt2\t개념 설명\n"
    t_times = [0.0, 5.0, 12.5, 20.0]
    p = evidence.expand_lines(text, t_times=t_times)
    assert len(p["knowledge_items"]) == 1
    k = p["knowledge_items"][0]
    assert k["timestamp"] == 12.5
    assert k["evidence"] == [{"source": "transcript", "ref": "2"}]
    assert p["_line_stats"]["normalized"]["K"] == 1
    assert p["_line_stats"]["dropped"]["K"] == 0


def test_expand_lines_c_variant2_derives_timestamp_from_t_ref_when_t_times_given():
    text = "C\thigh\tt1\t주장\n"
    t_times = [0.0, 5.0, 12.5]
    p = evidence.expand_lines(text, t_times=t_times)
    c = p["claims"][0]
    assert c["timestamp"] == 5.0
    assert p["_line_stats"]["normalized"]["C"] == 1


def test_expand_lines_k_variant3_drops_when_no_t_times_and_no_v_ref():
    """t_times가 없고(None) 참조가 t#뿐이면 유도 불가 — 기존대로 드롭한다.
    근거 추적이 정본의 존재 이유이므로 0.0 같은 가짜 값은 넣지 않는다."""
    text = "K\tconcept\tt2\t개념 설명\n"
    p = evidence.expand_lines(text)
    assert p["knowledge_items"] == []
    assert p["_line_stats"]["dropped"]["K"] == 1
    assert p["_line_stats"]["normalized"]["K"] == 0


def test_expand_lines_c_variant3_drops_when_no_t_times_and_no_v_ref():
    text = "C\tt2\t주장\n"
    p = evidence.expand_lines(text)
    assert p["claims"] == []
    assert p["_line_stats"]["dropped"]["C"] == 1
    assert p["_line_stats"]["normalized"]["C"] == 0


def test_expand_lines_k_variant3_drops_when_v_ref_unresolvable_in_batch():
    """refs가 v9를 가리키는데 배치 안에 v9가 없으면(같은 배치에 없음) t# 대체도
    없으므로 드롭한다."""
    text = "K\tconcept\tv9\t개념 설명\n"
    p = evidence.expand_lines(text)
    assert p["knowledge_items"] == []
    assert p["_line_stats"]["dropped"]["K"] == 1


def test_expand_lines_kc_recovery_does_not_regress_existing_lenient_rules():
    """기존 관용 규칙(V 정규화·K stray-confidence 변이1·필드 부족 드롭)은
    이번 변경 이후에도 그대로 동작해야 한다 — 회귀 가드."""
    text = ("V\tdiagram\t1.0\tf1.jpg\thigh\t값1\n"          # V 별칭 정규화 -> chart
            "K\tsetting\t12.5\tv1\thigh\tCUDA 12.6 필요\n"  # 변이1: 6필드 stray confidence
            "K\tcommand\t2.0\t\n"                            # content 없음 -> 여전히 드롭
            "C\t132.0\tv1\t정상 주장\n")                     # 정상 4필드 C
    p = evidence.expand_lines(text)
    assert p["_line_stats"]["dropped"] == {"T": 0, "V": 0, "K": 1, "C": 0, "G": 0}
    assert p["_line_stats"]["normalized"] == {"T": 0, "V": 1, "K": 1, "C": 0, "G": 0}
    assert len(p["knowledge_items"]) == 1
    assert p["knowledge_items"][0]["content"] == "CUDA 12.6 필요"
    assert p["claims"][0]["claim"] == "정상 주장"


def test_cli_from_lines_recovers_k_timestamp_from_v_ref_reports_normalized(tmp_path):
    """CLI 왕복: 변이2 K 라인이 같은 배치의 V로 복구되고 NORMALIZED에 잡힌다."""
    ev = evidence.register_frames(_skel(), ["f1.jpg"])
    evidence.save(tmp_path, ev)
    text = ("V\tui\t50.0\tf1.jpg\thigh\t화면값\n"
            "K\tsetting\thigh\tv1\tCUDA 설정\n")
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text(text, encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "DROPPED 0" in p.stdout
    assert "NORMALIZED 1" in p.stdout

    merged = evidence.load(tmp_path)
    assert merged["knowledge_items"][0]["timestamp"] == 50.0


def test_cli_from_lines_recovers_k_timestamp_from_transcript_segment_start(tmp_path):
    """CLI가 cache_dir의 transcript.json에서 segments start를 읽어 t_times로
    넘겨야 t# 유도가 가능하다."""
    tr = {"source": "captions", "lang": "en", "dupes_removed": 0, "flags": [],
          "segments": [{"start": 0.0, "text": "a"}, {"start": 5.0, "text": "b"},
                       {"start": 12.5, "text": "c"}, {"start": 20.0, "text": "d"}]}
    ev = evidence.build_skeleton(_info(), _sig(), tr, [], "u")
    evidence.save(tmp_path, ev)
    (tmp_path / "transcript.json").write_text(json.dumps(tr), encoding="utf-8")

    patch_file = tmp_path / "patch.lines"
    patch_file.write_text("K\tconcept\tt2\t개념 설명\n", encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "NORMALIZED 1" in p.stdout

    merged = evidence.load(tmp_path)
    assert merged["knowledge_items"][0]["timestamp"] == 12.5
    assert merged["knowledge_items"][0]["evidence"] == [{"source": "transcript", "ref": "2"}]


def test_cli_from_lines_missing_transcript_json_falls_back_to_none_without_crash(tmp_path):
    """transcript.json이 아예 없으면(cache_dir 갓 생성 등) t_times=None으로
    fail-soft해야 한다 — t# 유도만 못 하고 나머지는 정상 진행."""
    evidence.save(tmp_path, _skel())
    lines = [f"K\tcommand\t{float(i)}\tt0\t명령 {i}\n" for i in range(4)]
    lines.append("K\tconcept\tt0\t개념 설명\n")  # v# 없음 + t_times 없음 -> 드롭
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text("".join(lines), encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "Traceback" not in p.stderr
    assert "DROPPED 1" in p.stdout

    merged = evidence.load(tmp_path)
    assert len(merged["knowledge_items"]) == 4


def test_cli_from_lines_malformed_transcript_json_falls_back_to_none_without_crash(tmp_path):
    """transcript.json이 파손돼도(JSON 파싱 불가) 크래시 없이 None으로 폴백한다."""
    evidence.save(tmp_path, _skel())
    (tmp_path / "transcript.json").write_text("{not valid json", encoding="utf-8")
    lines = [f"K\tcommand\t{float(i)}\tt0\t명령 {i}\n" for i in range(4)]
    lines.append("K\tconcept\tt0\t개념 설명\n")
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text("".join(lines), encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "Traceback" not in p.stderr
    assert "DROPPED 1" in p.stdout


# ── 화면↔지식 검문 screen_check (grounding 라운드 Task A) ───────────────────

def _screen_check_fixture():
    """실측 회귀 고정(pwGeWRlrU10 03:33~03:37): 자막 유래 '30'과 화면 '25'가
    ±90초 창에서 병존하는 실패 사례를 재현한다. v6("Size")은 라벨이라 숫자
    후보가 아니고, v7("25")만 순수 숫자라 후보가 된다(실측 캐시와 동일 구조)."""
    return {
        "knowledge_items": [
            {"id": "k1", "type": "setting", "content": "Scale caption size down to 30",
             "timestamp": 188.0, "evidence": [{"source": "transcript", "ref": "27"}],
             "verification": {"status": "unaudited"}}],
        "claims": [],
        "visual_evidence": [
            {"id": "v6", "type": "ui", "timestamp": 217.0, "frame": "f.jpg",
             "confidence": "medium", "value": "Size"},
            {"id": "v7", "type": "ui", "timestamp": 217.0, "frame": "f.jpg",
             "confidence": "medium", "value": "25"}],
    }


def test_screen_check_flags_setting_value_missing_from_in_window_screen_values():
    """25↔30 실패 사례 그대로 재현 — flag 1건, v7('25')과 함께."""
    flags = evidence.screen_check(_screen_check_fixture())
    assert flags == [{"item_id": "k1", "text_value": "30",
                       "screen_candidates": ["25"], "v_ids": ["v7"]}]


def test_screen_check_ignores_v_outside_window():
    """창 밖 V는 무시한다 — 창 밖에 우연히 일치하는 '30'이 있어도 flag를 억제하지
    않는다(대조 대상에서 아예 빠져야 한다)."""
    ev = _screen_check_fixture()
    ev["visual_evidence"].append({"id": "v99", "type": "ui", "timestamp": 188.0 + 91,
                                  "frame": "f.jpg", "confidence": "high", "value": "30"})
    flags = evidence.screen_check(ev)
    assert flags == [{"item_id": "k1", "text_value": "30",
                       "screen_candidates": ["25"], "v_ids": ["v7"]}]


def test_screen_check_no_flag_when_window_has_no_v_at_all():
    """창에 V가 없으면 flag하지 않는다 — 미관측은 모순이 아니다."""
    ev = _screen_check_fixture()
    ev["visual_evidence"] = []
    assert evidence.screen_check(ev) == []


def test_screen_check_no_flag_when_window_v_have_no_numeric_value():
    """창에 V는 있어도 값이 전부 비숫자("Size" 같은 라벨)면 무flag — 숫자를
    가진 V가 하나도 없는 것과 동치다."""
    ev = _screen_check_fixture()
    ev["visual_evidence"] = [v for v in ev["visual_evidence"] if v["id"] == "v6"]
    assert evidence.screen_check(ev) == []


def test_screen_check_skips_non_setting_command_type_even_with_dollar_digit():
    """`$25`처럼 자막 유래 수치가 있어도 type이 setting/command가 아니면(예: concept)
    무flag — 범위를 좁혀 오탐을 막는다는 계약."""
    ev = _screen_check_fixture()
    ev["knowledge_items"][0]["type"] = "concept"
    ev["knowledge_items"][0]["content"] = "가격은 $25 정도다"
    assert evidence.screen_check(ev) == []


def test_screen_check_checks_claims_too_when_type_is_setting_or_command():
    """claims도 type이 setting|command면 검문 대상이다 — knowledge_items 전용이 아니다."""
    ev = _screen_check_fixture()
    ev["knowledge_items"] = []
    ev["claims"] = [{"id": "c1", "type": "setting", "claim": "Scale caption size down to 30",
                     "timestamp": 188.0, "evidence": [{"source": "transcript", "ref": "27"}],
                     "verification": {"status": "unaudited"}}]
    flags = evidence.screen_check(ev)
    assert flags == [{"item_id": "c1", "text_value": "30",
                       "screen_candidates": ["25"], "v_ids": ["v7"]}]


def test_apply_screen_check_marks_screen_conflict_without_mutating_body_text():
    """정본 표기 — 본문 문자열은 그대로 두고 screen_conflict만 얹는다(자동 치환 금지,
    플랜 Task A §2)."""
    ev = _screen_check_fixture()
    flags = evidence.apply_screen_check(ev)
    assert len(flags) == 1
    k = ev["knowledge_items"][0]
    assert k["content"] == "Scale caption size down to 30"       # 본문 불변
    assert k["screen_conflict"] == {"text": "30", "screen": ["25"], "v_ids": ["v7"]}


def test_apply_screen_check_accepts_precomputed_flags():
    """flags를 미리 계산해 넘기면 재계산 없이 그대로 표기한다."""
    ev = _screen_check_fixture()
    flags = evidence.screen_check(ev)
    evidence.apply_screen_check(ev, flags)
    assert ev["knowledge_items"][0]["screen_conflict"]["text"] == "30"


# ── render_video_md: screen_conflict 노출 ──────────────────────────────────

def test_render_shows_screen_conflict_marker():
    """게이트 기준(플랜 Task A §3): 렌더된 줄 끝에 ⚠️ 화면값 25 (자막 30)이 붙는다."""
    ev = _render_fixture()
    ev["knowledge_items"][0]["screen_conflict"] = {"text": "30", "screen": ["25"], "v_ids": ["v7"]}
    md = evidence.render_video_md(ev)
    assert "⚠️ 화면값 25 (자막 30)" in md


# ── K type 별칭 정규화(Task A 5) ────────────────────────────────────────────

def test_expand_lines_k_type_alias_setting_suffix_normalizes():
    """실측 회귀: font-setting·layout-setting처럼 `*-setting` 접미사는 setting으로
    정규화된다(드롭이 아니라 매핑) — 커버리지 감사 전량 거부 원인이었다."""
    p = evidence.expand_lines("K\tfont-setting\t1.0\tv1\t폰트 크게\n")
    assert p["knowledge_items"][0]["type"] == "setting"
    assert p["_line_stats"]["dropped"]["K"] == 0
    assert p["_line_stats"]["normalized"]["K"] == 1


def test_expand_lines_k_type_alias_config_normalizes_to_setting():
    p = evidence.expand_lines("K\tconfig\t1.0\tv1\t설정값\n")
    assert p["knowledge_items"][0]["type"] == "setting"
    assert p["_line_stats"]["normalized"]["K"] == 1


def test_expand_lines_k_type_alias_step_normalizes_to_procedure():
    p = evidence.expand_lines("K\tstep\t1.0\tv1\t첫 단계\n")
    assert p["knowledge_items"][0]["type"] == "procedure"
    assert p["_line_stats"]["normalized"]["K"] == 1


def test_expand_lines_k_type_alias_tip_normalizes_to_warning():
    p = evidence.expand_lines("K\ttip\t1.0\tv1\t유용한 팁\n")
    assert p["knowledge_items"][0]["type"] == "warning"
    assert p["_line_stats"]["normalized"]["K"] == 1


def test_expand_lines_k_type_alias_note_normalizes_to_warning():
    p = evidence.expand_lines("K\tnote\t1.0\tv1\t참고\n")
    assert p["knowledge_items"][0]["type"] == "warning"
    assert p["_line_stats"]["normalized"]["K"] == 1


def test_expand_lines_k_type_unknown_falls_back_to_concept_not_dropped():
    """별칭에도 없는 미지 type은 드롭 대신 concept으로 강제한다 — 드롭 0."""
    p = evidence.expand_lines("K\tmystery\t1.0\tv1\t알 수 없는 유형\n")
    assert p["knowledge_items"][0]["type"] == "concept"
    assert p["_line_stats"]["dropped"]["K"] == 0
    assert p["_line_stats"]["normalized"]["K"] == 1


def test_expand_lines_k_type_already_valid_not_counted_as_normalized():
    """이미 유효한 enum 값은 정규화 대상이 아니다 — normalized가 거짓으로 올라가면
    안 된다."""
    p = evidence.expand_lines("K\tsetting\t1.0\tv1\t정상 설정\n")
    assert p["knowledge_items"][0]["type"] == "setting"
    assert p["_line_stats"]["normalized"]["K"] == 0


# ── CLI --from-lines: SCREENCHECK stdout (Task A 4) ────────────────────────

def test_cli_from_lines_prints_screencheck_when_text_value_missing_on_screen(tmp_path):
    """실측 회귀(pwGeWRlrU10 03:33~03:37): 합성 배치(V+K 동시 병합)에서 자막
    유래 '30'과 화면 '25'가 병존하면 SCREENCHECK 1을 stdout에 낸다."""
    ev = evidence.register_frames(_skel(), ["f1.jpg"])
    evidence.save(tmp_path, ev)
    text = (
        "V\tui\t217.0\tf1.jpg\tmedium\t25\n"
        "K\tsetting\t188.0\tv1\tScale caption size down to 30\n"
    )
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text(text, encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "SCREENCHECK 1" in p.stdout

    merged = evidence.load(tmp_path)
    k = merged["knowledge_items"][0]
    assert k["content"] == "Scale caption size down to 30"        # 본문 불변
    assert k["screen_conflict"] == {"text": "30", "screen": ["25"], "v_ids": ["v1"]}


def test_cli_from_lines_screencheck_absent_from_stdout_when_zero(tmp_path):
    """0건이면 SCREENCHECK 자체가 stdout에 나타나지 않는다(NORMALIZED와 동일 관례
    — 잡음 섞인 보고 금지)."""
    ev = evidence.register_frames(_skel(), ["f1.jpg"])
    evidence.save(tmp_path, ev)
    text = (
        "V\tui\t217.0\tf1.jpg\tmedium\t25\n"
        "K\tsetting\t188.0\tv1\tScale caption size down to 25\n"
    )
    patch_file = tmp_path / "patch.lines"
    patch_file.write_text(text, encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "SCREENCHECK" not in p.stdout


def test_cli_from_lines_screencheck_runs_on_coverage_audit_style_batch_too(tmp_path):
    """커버리지 감사분도 같은 --from-lines 경로를 타므로 검문이 걸려야 한다 —
    이번 실패의 2번 원인(감사 경로의 구멍)을 봉쇄하는 회귀. 감사는 설계상
    텍스트 전용(화면 접근 없음)이라 evidence는 t#(transcript) 참조만 쓰지만,
    이미 병합된 V(화면)와는 여전히 대조돼야 한다."""
    ev = evidence.register_frames(_skel(), ["f1.jpg"])
    ev = evidence.merge(ev, {"visual_evidence": [
        {"type": "ui", "value": "25", "timestamp": 217.0, "frame": "f1.jpg", "confidence": "medium"}]})
    evidence.save(tmp_path, ev)
    # 커버리지 감사 보강 배치 — 화면에 접근하지 않고 자막만 보고 낸 K(화면과 반대되는 값)
    text = "K\tsetting\t188.0\tt0\tScale caption size down to 30\n"
    patch_file = tmp_path / "coverage.lines"
    patch_file.write_text(text, encoding="utf-8")

    p = _run([str(tmp_path), "--from-lines", str(patch_file)])
    assert p.returncode == 0, f"stdout={p.stdout}\nstderr={p.stderr}"
    assert "SCREENCHECK 1" in p.stdout
