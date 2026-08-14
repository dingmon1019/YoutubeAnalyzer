import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import transcribe

AUTO_VTT = """WEBVTT
Kind: captions
Language: ko

00:00:00.000 --> 00:00:02.500
안녕하세요<00:00:01.000><c> 여러분</c>

00:00:02.500 --> 00:00:05.000
안녕하세요 여러분
오늘은 힉스필드를

00:00:05.000 --> 00:00:07.500
오늘은 힉스필드를
써보겠습니다
"""


def test_parse_vtt_strips_inline_tags():
    cues = transcribe.parse_vtt(AUTO_VTT)
    assert cues[0]["start"] == 0.0 and cues[0]["end"] == 2.5
    assert "<" not in cues[0]["text"]
    assert cues[0]["text"] == "안녕하세요 여러분"


def test_dedup_removes_rolling_lines():
    cues = transcribe.parse_vtt(AUTO_VTT)
    clean, removed = transcribe.dedup_cues(cues)
    joined = " ".join(c["text"] for c in clean)
    assert joined.count("안녕하세요") == 1
    assert joined.count("힉스필드를") == 1
    assert removed >= 2


def test_parse_vtt_ignores_cue_identifiers_and_notes():
    vtt = "WEBVTT\n\nNOTE\nthis is a comment\n\n1\n00:00:00.000 --> 00:00:02.000\nHello\n\n2\n00:00:02.000 --> 00:00:04.000\nWorld\n"
    cues = transcribe.parse_vtt(vtt)
    assert [c["text"] for c in cues] == ["Hello", "World"]


def test_parse_vtt_hour_timestamps():
    vtt = "WEBVTT\n\n01:23:45.678 --> 01:24:10.250\n안녕하세요\n"
    c = transcribe.parse_vtt(vtt)[0]
    assert abs(c["start"] - 5025.678) < 0.001 and abs(c["end"] - 5050.250) < 0.001


def test_parse_vtt_drops_tag_only_cue():
    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n<c></c>\n\n00:00:01.000 --> 00:00:02.000\nReal text\n"
    cues = transcribe.parse_vtt(vtt)
    assert [c["text"] for c in cues] == ["Real text"]


def test_collapse_repeats():
    segs = [{"start": float(i), "end": i + 1.0, "text": "감사합니다"} for i in range(5)]
    segs.append({"start": 5.0, "end": 6.0, "text": "다음 단계로"})
    out, n = transcribe.collapse_repeats(segs, n=3)
    texts = [s["text"] for s in out]
    assert texts.count("감사합니다") == 1 and n == 4
    assert "다음 단계로" in texts


def test_drop_silence_overlap():
    segs = [
        {"start": 1.0, "end": 3.0, "text": "진짜 말"},
        {"start": 10.0, "end": 12.0, "text": "시청해주셔서 감사합니다"},  # 무음 구간 안 = 환각
    ]
    out, n = transcribe.drop_silence_overlap(segs, [(8.0, 20.0)])
    assert len(out) == 1 and out[0]["text"] == "진짜 말" and n == 1


def test_groq_drops_no_speech(monkeypatch):
    fake = {"segments": [
        {"start": 0.0, "end": 2.0, "text": " 안녕하세요", "no_speech_prob": 0.1},
        {"start": 2.0, "end": 4.0, "text": " 구독과 좋아요", "no_speech_prob": 0.95},
    ]}
    monkeypatch.setattr(transcribe, "_groq_request", lambda path, key: fake)
    # **kw: 실제 Path.stat()은 follow_symlinks 키워드를 받으므로, 테스트 실패 시 pytest 자체의
    # 리포팅 경로(Path.exists() 등)가 이 패치를 건드려도 TypeError로 죽지 않게 방어.
    monkeypatch.setattr(
        transcribe.Path, "stat", lambda self, **kw: type("S", (), {"st_size": 1000})()
    )
    segs = transcribe.groq_transcribe(Path("fake.mp3"), "key")
    assert len(segs) == 1 and segs[0]["text"] == "안녕하세요"


def test_chain_none_when_all_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(transcribe.common, "load_config", lambda: {})
    monkeypatch.setattr(transcribe, "local_transcribe", lambda p: None)
    r = transcribe.get_transcript(tmp_path, mode="auto")
    assert r["source"] == "none" and r["segments"] == []
    assert any("no transcript" in f for f in r["flags"])


def test_main_survives_narrow_console_encoding(tmp_path, monkeypatch):
    """"no transcript" 플래그의 em-dash(—)가 cp949/ascii 등 좁은 콘솔 인코딩에서도
    CLI를 크래시시키지 않아야 함 (UnicodeEncodeError 방어)."""
    fake_stdout = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict")
    monkeypatch.setattr(transcribe.sys, "stdout", fake_stdout)
    monkeypatch.setattr(transcribe.sys, "argv", ["transcribe.py", str(tmp_path), "--no-whisper"])
    assert transcribe.main() == 0


def test_local_transcribe_failure_falls_to_none(tmp_path, monkeypatch):
    """local_transcribe가 예외를 던져도(모델 다운로드 실패·CUDA 오류 등) 전체 런이
    죽지 않고 source=none + local_failed 플래그로 우아하게 저하되어야 함."""
    (tmp_path / "video.mp4").write_bytes(b"")
    (tmp_path / "audio.mp3").write_bytes(b"")  # 이미 존재 → 실제 ffmpeg 추출 회피
    monkeypatch.setattr(transcribe.common, "load_config", lambda: {})  # GROQ_API_KEY 없음

    def _boom(p):
        raise RuntimeError("model download failed")

    monkeypatch.setattr(transcribe, "local_transcribe", _boom)
    r = transcribe.get_transcript(tmp_path, mode="auto")
    assert r["source"] == "none"
    assert any(f.startswith("local_failed") for f in r["flags"])


def test_local_zero_segments_recorded_distinctly_from_never_attempted(tmp_path, monkeypatch):
    """L3 실측(zxTH99U21Rw, 5분 무자막 ASMR): faster-whisper가 예외 없이 정상 실행되고
    VAD가 스피치를 못 찾아 세그먼트 0개를 반환하는 경우(직접 재현: local_transcribe()가
    21.7초 걸려 실제로 돌고 [] 반환) — "애초에 시도조차 안 함"(예: faster-whisper 미설치로
    None 반환)과는 다른 상황인데, 지금은 최종 source=none 재설정 시 flags에 "시도했지만
    0건"이라는 사실 자체가 사라져 두 상황이 구분 불가능했다."""
    (tmp_path / "video.mp4").write_bytes(b"")
    (tmp_path / "audio.mp3").write_bytes(b"")  # 이미 존재 → 실제 ffmpeg 추출 회피
    monkeypatch.setattr(transcribe.common, "load_config", lambda: {})  # GROQ_API_KEY 없음
    monkeypatch.setattr(transcribe, "local_transcribe", lambda p: [])  # 실행은 됐지만 0세그먼트

    r = transcribe.get_transcript(tmp_path, mode="auto")
    assert r["source"] == "none" and r["segments"] == []
    assert any("zero_segments" in f for f in r["flags"])


def test_silence_detect_failure_keeps_segments(tmp_path, monkeypatch):
    """detect_silences가 예외를 던져도(ffmpeg 실패 등) 이미 얻은 세그먼트는 버리지 않고
    무음 드롭만 건너뛴 채 silence_detect_failed 플래그로 계속 진행해야 함."""
    (tmp_path / "video.mp4").write_bytes(b"")
    (tmp_path / "audio.mp3").write_bytes(b"")  # 작은 실파일 → 실제 stat()이 GROQ_LIMIT 이하
    monkeypatch.setattr(transcribe.common, "load_config", lambda: {"GROQ_API_KEY": "key"})
    fake = {"segments": [{"start": 0.0, "end": 2.0, "text": "안녕하세요", "no_speech_prob": 0.1}]}
    monkeypatch.setattr(transcribe, "_groq_request", lambda path, key: fake)
    monkeypatch.setattr(transcribe, "_probe_duration", lambda path: 1200.0)

    def _boom(p):
        raise RuntimeError("ffmpeg not found")

    monkeypatch.setattr(transcribe, "detect_silences", _boom)
    r = transcribe.get_transcript(tmp_path, mode="auto")
    assert len(r["segments"]) == 1 and r["segments"][0]["text"] == "안녕하세요"
    assert any(f.startswith("silence_detect_failed") for f in r["flags"])


def test_parse_vtt_mmss_no_hours():
    """일부 자동자막 export는 큐 타임스탬프에 시(HH)가 없는 MM:SS.mmm만 쓴다 — 기존
    정규식은 HH:MM:SS.mmm만 허용해 이런 큐를 통째로 못 읽고 조용히 cues=[]가 됐다."""
    vtt = "WEBVTT\n\n05:30.500 --> 05:32.750\n안녕하세요\n"
    cues = transcribe.parse_vtt(vtt)
    assert len(cues) == 1
    assert abs(cues[0]["start"] - 330.5) < 0.001
    assert abs(cues[0]["end"] - 332.75) < 0.001


def test_captions_unparseable_falls_through_to_whisper(tmp_path, monkeypatch):
    """캡션 VTT 파일은 있지만(헤더뿐, 파싱 가능한 큐가 없음) 세그먼트가 0개면
    "captions_unparseable" 플래그를 남기고 whisper 사슬로 폴백해야 한다 — 이전에는
    source="captions"로 영구 확정되며 groq/local을 아예 시도조차 하지 않았다."""
    (tmp_path / "subs.ko.vtt").write_text("WEBVTT\n\n", encoding="utf-8")
    (tmp_path / "video.mp4").write_bytes(b"")
    (tmp_path / "audio.mp3").write_bytes(b"")  # 이미 존재 → 실제 ffmpeg 추출 회피
    monkeypatch.setattr(transcribe.common, "load_config", lambda: {"GROQ_API_KEY": "key"})
    fake = {"segments": [{"start": 0.0, "end": 2.0, "text": "안녕하세요", "no_speech_prob": 0.1}]}
    monkeypatch.setattr(transcribe, "_groq_request", lambda path, key: fake)
    monkeypatch.setattr(transcribe, "detect_silences", lambda path: [])

    r = transcribe.get_transcript(tmp_path, mode="auto")
    assert r["source"] == "groq"
    assert any(f.startswith("captions_unparseable") for f in r["flags"])


def test_get_transcript_prefers_orig_vtt_over_sorted_first(tmp_path):
    """언어 정렬(sorted()[0])은 예: subs.en.vtt(번역본) < subs.ko-orig.vtt(원어) 알파벳
    순서상 번역본이 원어를 조용히 이겨버린다 — 원어 트랙(파일명에 -orig 포함)이 있으면
    그걸 우선해야 한다."""
    (tmp_path / "subs.en.vtt").write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhello\n", encoding="utf-8"
    )
    (tmp_path / "subs.ko-orig.vtt").write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\n안녕하세요\n", encoding="utf-8"
    )
    r = transcribe.get_transcript(tmp_path, mode="auto")
    assert r["segments"][0]["text"] == "안녕하세요"
    assert r["lang"] == "ko"


def test_post_filter_zero_segments_flagged_distinctly(tmp_path, monkeypatch):
    """ASR가 세그먼트를 반환했지만 무음 드롭으로 전부 걸러지면(예: 세그먼트가 통째로
    무음 구간 안) "애초에 0개 반환"과는 다른 상황이므로 별도 zero_segments 플래그를
    남겨야 한다 — 지금은 이 사실이 조용히 사라진다."""
    (tmp_path / "video.mp4").write_bytes(b"")
    (tmp_path / "audio.mp3").write_bytes(b"")
    monkeypatch.setattr(transcribe.common, "load_config", lambda: {"GROQ_API_KEY": "key"})
    fake = {"segments": [{"start": 10.0, "end": 12.0, "text": "감사합니다", "no_speech_prob": 0.1}]}
    monkeypatch.setattr(transcribe, "_groq_request", lambda path, key: fake)
    monkeypatch.setattr(transcribe, "detect_silences", lambda path: [(8.0, 20.0)])

    r = transcribe.get_transcript(tmp_path, mode="auto")
    assert r["segments"] == []
    assert any(f.startswith("groq_zero_segments") for f in r["flags"])
    assert any("silence_dropped" in f for f in r["flags"])


def test_detect_silences_raises_on_nonzero_returncode(monkeypatch, tmp_path):
    """ffmpeg가 존재해도 조용히 실패(잘못된 인자·손상 파일 등)하면 returncode != 0인데
    지금까지는 이를 무시하고 partial/empty stderr를 그냥 파싱해 조용히 []를 반환했다 —
    P5 무음 방어가 조용히 무력화된다."""
    import subprocess as real_subprocess

    def fake_run(cmd, **kw):
        p = real_subprocess.CompletedProcess(cmd, 1)
        p.stdout = ""
        p.stderr = "Error: something broke"
        return p

    monkeypatch.setattr(real_subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        transcribe.detect_silences(tmp_path / "audio.mp3")


def test_groq_transcribe_offset_uses_probed_duration(monkeypatch):
    """ffmpeg -f segment -c copy는 프레임 경계에서 잘라 실제 청크 길이가 명목상 CHUNK_SEC과
    어긋나므로, 다음 청크의 오프셋은 실측 길이를 누적해야 함 (1200.0 고정값 아님)."""
    fake = {"segments": [{"start": 0.0, "end": 2.0, "text": "청크", "no_speech_prob": 0.1}]}
    monkeypatch.setattr(transcribe, "_groq_request", lambda path, key: fake)
    monkeypatch.setattr(transcribe, "_probe_duration", lambda path: 1197.5)
    monkeypatch.setattr(
        transcribe, "_split_audio",
        lambda path: [Path("chunk_000.mp3"), Path("chunk_001.mp3")],
    )
    monkeypatch.setattr(
        transcribe.Path, "stat",
        lambda self, **kw: type("S", (), {"st_size": transcribe.GROQ_LIMIT + 1})(),
    )
    segs = transcribe.groq_transcribe(Path("big.mp3"), "key")
    assert len(segs) == 2
    assert segs[1]["start"] == 1197.5
    assert segs[1]["start"] != 1200.0


def test_parse_vtt_unescapes_html_entities():
    """실측(2026-08-14, 0chZFIZLR_0): 자막의 &nbsp;가 그대로 남아 video.md 인용까지
    전파될 뻔했다. 엔티티는 마크업 잔재이지 '원문 오타 보존' 대상이 아니다."""
    vtt = ("WEBVTT\n\n"
           "00:01.000 --> 00:03.000\n"
           "To sum it up, git merge&nbsp;&nbsp;gives &amp; keeps\n")
    cues = transcribe.parse_vtt(vtt)
    assert len(cues) == 1
    assert "&nbsp;" not in cues[0]["text"] and "&amp;" not in cues[0]["text"]
    assert "\xa0" not in cues[0]["text"]          # 비분리 공백도 일반 공백으로
    assert "gives & keeps" in cues[0]["text"]
