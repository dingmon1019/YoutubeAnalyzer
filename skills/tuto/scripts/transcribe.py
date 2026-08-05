"""자막 사슬: VTT 파싱·롤링 중복 제거 (+Groq/로컬 whisper는 T6). §5 P5/P6."""
import re
import sys
from pathlib import Path

import common

_TS_LINE = re.compile(
    r"(\d{2}:\d{2}:\d{2})\.(\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2})\.(\d{3})"
)
_INLINE = re.compile(r"<[^>]+>")


def parse_vtt(text: str) -> list:
    cues, cur = [], None
    for line in text.splitlines():
        m = _TS_LINE.search(line)
        if m:
            if cur and cur["text"]:
                cues.append(cur)
            start = common.parse_ts(m.group(1)) + int(m.group(2)) / 1000
            end = common.parse_ts(m.group(3)) + int(m.group(4)) / 1000
            cur = {"start": start, "end": end, "text": ""}
        elif cur is not None:
            clean = _INLINE.sub("", line).strip()
            if clean and not clean.startswith(("WEBVTT", "Kind:", "Language:")):
                cur["text"] = (cur["text"] + "\n" + clean).strip() if cur["text"] else clean
    if cur and cur["text"]:
        cues.append(cur)
    return cues


def dedup_cues(cues: list) -> tuple:
    """자동자막 롤링 중복: 각 큐의 앞줄 = 직전 큐의 마지막 줄 반복 → 제거."""
    removed = 0
    prev_last = None
    out = []
    for c in cues:
        lines = c["text"].split("\n")
        if prev_last is not None and lines and lines[0] == prev_last:
            lines = lines[1:]
            removed += 1
        prev_last = lines[-1] if lines else prev_last
        text = " ".join(lines).strip()
        if text:
            out.append({"start": c["start"], "end": c["end"], "text": text})
    return out, removed
