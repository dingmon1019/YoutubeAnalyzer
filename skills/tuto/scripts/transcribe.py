"""자막 사슬: VTT 파싱·롤링 중복 제거 + Groq/로컬 Whisper 사슬·환각 방어. §5 P5/P6."""
import argparse
import json
import mimetypes
import re
import sys
import urllib.request
import uuid
from pathlib import Path

import common

_TS_LINE = re.compile(
    r"((?:\d{2}:)?\d{2}:\d{2}\.\d{3})\s*-->\s*((?:\d{2}:)?\d{2}:\d{2}\.\d{3})"
)
_INLINE = re.compile(r"<[^>]+>")
_SIL = re.compile(r"silence_(start|end): ([\d.]+)")

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_LIMIT = 24 * 1024 * 1024  # 25MB 제한에 여유
NO_SPEECH_MAX = 0.6
CHUNK_SEC = 1200


def _parse_cue_time(token: str) -> float:
    """VTT 큐 타임스탬프 하나(HH:MM:SS.mmm 또는 시(H) 생략된 MM:SS.mmm)를 초로 변환."""
    left, ms = token.rsplit(".", 1)
    return common.parse_ts(left) + int(ms) / 1000


def parse_vtt(text: str) -> list:
    cues, cur = [], None
    for line in text.splitlines():
        m = _TS_LINE.search(line)
        if m:
            if cur and cur["text"]:
                cues.append(cur)
            start = _parse_cue_time(m.group(1))
            end = _parse_cue_time(m.group(2))
            cur = {"start": start, "end": end, "text": ""}
        elif not line.strip():  # blank line resets cur
            if cur and cur["text"]:
                cues.append(cur)
            cur = None
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


def collapse_repeats(segs: list, n: int = 3) -> tuple:
    """동일 텍스트 n회+ 연속 세그먼트 → 1개로 붕괴 (P5 반복 루프 환각)."""
    out, removed, i = [], 0, 0
    while i < len(segs):
        j = i
        while j < len(segs) and segs[j]["text"].strip() == segs[i]["text"].strip():
            j += 1
        run_len = j - i
        if run_len >= n:
            merged = dict(segs[i])
            merged["end"] = segs[j - 1]["end"]
            out.append(merged)
            removed += run_len - 1
        else:
            out.extend(segs[i:j])
        i = j
    return out, removed


def detect_silences(audio_path) -> list:
    import subprocess
    p = subprocess.run(
        ["ffmpeg", "-i", str(audio_path), "-af", "silencedetect=noise=-35dB:d=2",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    if p.returncode != 0:
        # returncode를 무시하면 ffmpeg가 조용히 실패했을 때 partial/empty stderr를 그냥
        # "무음 없음"으로 파싱해버려 P5(무음 환각) 방어가 조용히 무력화된다.
        raise RuntimeError(f"detect_silences ffmpeg failed (rc={p.returncode}): {p.stderr[-300:]}")
    events, start = [], None
    for kind, val in _SIL.findall(p.stderr):
        if kind == "start":
            start = float(val)
        elif start is not None:
            events.append((start, float(val)))
            start = None
    return events


def drop_silence_overlap(segs: list, silences: list) -> tuple:
    """세그먼트 중심이 무음 구간 안이면 드롭 (P5 무음 환각)."""
    def in_silence(s):
        mid = (s["start"] + s["end"]) / 2
        return any(a <= mid <= b for a, b in silences)
    kept = [s for s in segs if not in_silence(s)]
    return kept, len(segs) - len(kept)


def _groq_request(audio_path, api_key: str) -> dict:
    boundary = uuid.uuid4().hex
    data = audio_path.read_bytes()
    parts = []
    for name, val in (("model", "whisper-large-v3"), ("response_format", "verbose_json")):
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n".encode()
        )
    ctype = mimetypes.guess_type(str(audio_path))[0] or "audio/mpeg"
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{audio_path.name}\"\r\nContent-Type: {ctype}\r\n\r\n".encode()
        + data + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        GROQ_URL, data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def _split_audio(audio_path, chunk_sec: int = CHUNK_SEC) -> list:
    """25MB 초과 시 시간 분할. 64kbps mono mp3 기준 20분 ≈ 9.6MB."""
    out_tpl = audio_path.parent / "chunk_%03d.mp3"
    common.run(["ffmpeg", "-y", "-i", audio_path, "-f", "segment",
                "-segment_time", chunk_sec, "-c", "copy", out_tpl])
    return sorted(audio_path.parent.glob("chunk_*.mp3"))


def _probe_duration(path) -> float:
    """ffprobe로 청크 실제 길이 측정. ffmpeg -f segment -c copy는 프레임 경계에서 잘라
    실제 길이가 명목상 CHUNK_SEC과 어긋나므로, 다음 청크 오프셋은 이 실측값을 누적해야 함."""
    import subprocess
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    return float(p.stdout.strip())


def groq_transcribe(audio_path, api_key: str) -> list:
    chunks = [audio_path] if audio_path.stat().st_size <= GROQ_LIMIT else _split_audio(audio_path)
    segs, offset = [], 0.0
    for i, chunk in enumerate(chunks):
        resp = _groq_request(chunk, api_key)
        for s in resp.get("segments", []):
            if s.get("no_speech_prob", 0.0) > NO_SPEECH_MAX:
                continue
            segs.append({
                "start": float(s["start"]) + offset,
                "end": float(s["end"]) + offset,
                "text": s["text"].strip(),
            })
        if i + 1 < len(chunks):  # 마지막 청크 뒤에는 오프셋이 쓰일 데가 없으므로 측정 생략
            try:
                offset += _probe_duration(chunk)
            except Exception:
                # 측정 실패 시 명목상 CHUNK_SEC으로 폴백 — 오차는 프레임 경계 수준으로 제한되어
                # 허용 가능 (조용한 폴백; 이 레이어에서는 별도 플래그를 남기지 않음).
                offset += float(CHUNK_SEC)
    return segs


def local_transcribe(audio_path):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    model = WhisperModel("large-v3", device="auto", compute_type="int8")
    raw, _info = model.transcribe(str(audio_path), vad_filter=True)
    return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in raw]


def _extract_audio(cache_dir: Path) -> Path:
    audio = cache_dir / "audio.mp3"
    if not audio.exists():
        common.run(["ffmpeg", "-y", "-i", cache_dir / "video.mp4",
                    "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", audio])
    return audio


def get_transcript(cache_dir: Path, mode: str = "auto") -> dict:
    result = {"source": "none", "lang": "", "segments": [], "flags": [], "dupes_removed": 0}
    vtts = sorted(cache_dir.glob("subs*.vtt"))
    # 원어 자동자막 트랙(-orig)이 있으면 사전순(sorted()[0])보다 우선한다 — 그렇지 않으면
    # 예: subs.en.vtt(번역본)가 subs.ko-orig.vtt(원어)를 알파벳순으로 조용히 이겨버린다.
    orig_vtts = [v for v in vtts if "-orig" in v.name]
    vtt = orig_vtts[0] if orig_vtts else (vtts[0] if vtts else None)
    if vtt and mode != "no-captions-test":
        lang = "ko" if ".ko" in vtt.name else ("en" if ".en" in vtt.name else "?")
        cues = parse_vtt(vtt.read_text(encoding="utf-8", errors="replace"))
        segs, removed = dedup_cues(cues)
        if segs:
            result.update(source="captions", lang=lang, segments=segs, dupes_removed=removed)
        else:
            # 캡션 파일은 있었지만(예: 헤더뿐이거나 지원 안 하는 타임스탬프 형식) 파싱 결과가
            # 0세그먼트 — 예전에는 여기서 source="captions"로 영구 확정되어 whisper 사슬을
            # 아예 시도조차 안 했다. 흔적을 남기고 아래에서 whisper로 폴백시킨다.
            result["flags"].append(f"captions_unparseable: {vtt.name}")
    if not result["segments"] and mode != "no-whisper":
        video = cache_dir / "video.mp4"
        if video.exists():
            audio = _extract_audio(cache_dir)
            cfg = common.load_config()
            segs = None
            if mode in ("auto", "groq") and cfg.get("GROQ_API_KEY"):
                try:
                    segs = groq_transcribe(audio, cfg["GROQ_API_KEY"])
                    result["source"] = "groq"
                except Exception as e:
                    result["flags"].append(f"groq_failed: {str(e)[:200]}")
            if segs is None and mode in ("auto", "local"):
                try:
                    segs = local_transcribe(audio)
                    if segs is not None:
                        result["source"] = "local"
                except Exception as e:
                    result["flags"].append(f"local_failed: {str(e)[:200]}")
                    segs = None
            if segs:
                try:
                    silences = detect_silences(audio)
                except Exception as e:
                    result["flags"].append(f"silence_detect_failed: {str(e)[:200]}")
                    silences = []
                segs, sil_n = drop_silence_overlap(segs, silences)
                segs, rep_n = collapse_repeats(segs)
                if sil_n:
                    result["flags"].append(f"silence_dropped: {sil_n}")
                if rep_n:
                    result["flags"].append(f"repeats_collapsed: {rep_n}")
                if not segs:
                    # ASR는 세그먼트를 반환했지만 무음 드롭·반복 붕괴가 전부 걸러냈다 — "애초에
                    # 0개 반환"(아래 elif 분기)과는 다른 상황이므로 같은 명명 패턴으로 구분해
                    # 남긴다(둘 다 zero_segments지만 원인이 다르다).
                    result["flags"].append(
                        f"{result['source']}_zero_segments: post-filter removed all segments"
                    )
                result["segments"] = segs
            elif segs is not None:
                # ASR 백엔드가 예외 없이 응답했지만(source가 이미 세팅됨) 세그먼트 0개 — VAD나
                # no_speech_prob 필터가 스피치를 못 찾은 정상 케이스(예: 무음·ASMR류 오디오,
                # 실측 zxTH99U21Rw 5분 클립: local_transcribe 21.7초 실행 후 [] 반환)다.
                # "애초에 시도조차 안 함"과 구분되게 남긴다 — 바로 아래에서 source가 다시
                # "none"으로 재설정돼도 이 시도 사실은 flags에 보존된다.
                result["flags"].append(f"{result['source']}_zero_segments: ASR ran, no speech detected")
    if not result["segments"]:
        result["source"] = "none"
        result["flags"].append("no transcript available — frames-only mode")
    (cache_dir / "transcript.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return result


def main() -> int:
    common.utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("cache_dir")
    ap.add_argument("--whisper", choices=["groq", "local"], default=None)
    ap.add_argument("--no-whisper", action="store_true")
    args = ap.parse_args()
    mode = "no-whisper" if args.no_whisper else (args.whisper or "auto")
    r = get_transcript(Path(args.cache_dir), mode)
    print(f"transcript: source={r['source']} lang={r['lang']} segments={len(r['segments'])} "
          f"dupes_removed={r['dupes_removed']} flags={r['flags'] or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
