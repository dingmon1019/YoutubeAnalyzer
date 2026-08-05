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
