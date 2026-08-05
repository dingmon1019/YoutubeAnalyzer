import io
import sys
from pathlib import Path

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
    monkeypatch.setattr(transcribe.Path, "stat", lambda self: type("S", (), {"st_size": 1000})())
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
