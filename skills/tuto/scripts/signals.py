"""4신호 수집: 히트맵·챕터·SponsorBlock·설명란 타임스탬프 (+활동 곡선은 T4). §6.

Flags contract: flags list contains prefix-matched identifiers (e.g., "heatmap_absent",
"chapters_absent", "sponsorblock_error: <detail>"). Consumers must use startswith() for
prefix matching, not equality checks. Format: "identifier" or "identifier: detail".
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import common

SB_API = "https://sponsor.ajay.app/api/skipSegments"
SB_CATS = '["sponsor","selfpromo","intro","outro","filler"]'
_DESC_TS = re.compile(r"^\s*\(?(\d{1,2}:\d{2}(?::\d{2})?)\)?\s*[-–—:]?\s*(.+)$")


def _http_get(url: str, timeout: int = 15) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")


def parse_heatmap(info: dict) -> list:
    return [
        {"start": float(h["start_time"]), "end": float(h["end_time"]), "value": float(h["value"])}
        for h in (info.get("heatmap") or [])
    ]


def parse_chapters(info: dict) -> list:
    return [
        {"start": float(c["start_time"]), "end": float(c["end_time"]), "title": c.get("title", "")}
        for c in (info.get("chapters") or [])
    ]


def parse_description_timestamps(info: dict) -> list:
    out = []
    for line in (info.get("description") or "").splitlines():
        m = _DESC_TS.match(line)
        if m and m.group(2).strip():
            out.append({"t": common.parse_ts(m.group(1)), "label": m.group(2).strip()})
    return out


def fetch_sponsorblock(video_id: str) -> list:
    url = f"{SB_API}?videoID={video_id}&categories={urllib.request.quote(SB_CATS)}"
    try:
        data = json.loads(_http_get(url, timeout=15))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    return [
        {"start": float(s["segment"][0]), "end": float(s["segment"][1]), "category": s["category"]}
        for s in data
    ]


def build_signals(info: dict, video_id: str, video_path, curve=None) -> dict:
    flags = []
    try:
        sb = fetch_sponsorblock(video_id)
    except Exception as e:
        sb, flags = [], [f"sponsorblock_error: {e}"]
    sig = {
        "heatmap": parse_heatmap(info),
        "chapters": parse_chapters(info),
        "desc_timestamps": parse_description_timestamps(info),
        "sponsorblock": sb,
        "activity": {"curve": curve or [], "peaks": []},
        "flags": flags,
    }
    if not sig["heatmap"]:
        sig["flags"].append("heatmap_absent")
    if not sig["chapters"]:
        sig["flags"].append("chapters_absent")
    return sig


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cache_dir")
    args = ap.parse_args()
    cd = Path(args.cache_dir)
    info = json.loads((cd / "info.json").read_text(encoding="utf-8"))
    sig = build_signals(info, info["id"], cd / "video.mp4")
    (cd / "signals.json").write_text(json.dumps(sig, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"signals: heatmap={len(sig['heatmap'])} chapters={len(sig['chapters'])} "
        f"desc_ts={len(sig['desc_timestamps'])} sponsorblock={len(sig['sponsorblock'])} "
        f"flags={sig['flags'] or 'none'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
