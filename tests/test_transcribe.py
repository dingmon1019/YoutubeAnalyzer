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
