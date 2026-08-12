"""evidence.json — 영상 분석의 구조화 산출물.

설계 원칙 세 가지:

1. **결정론적 골격만 파이썬이 만든다.** 비디오 메타·자막 세그먼트·프레임 provenance·신호
   요약은 계산 가능하므로 여기서 만들고, 시각 증거(visual_evidence)와 주장(claims)은
   화면을 본 LLM이 판독해 병합한다. 산문 렌더링(guide.md / insight.md)은 이 모듈의
   책임이 아니다 — 파이썬은 문장을 쓰지 않는다.

2. **transcript 증거와 visual 증거를 구조로 분리한다.** `segments[].transcript`는 자막이고
   `visual_evidence[]`는 화면이다. 둘을 같은 배열에 담지 않으며, claim이 양쪽을 근거로
   삼을 때도 `source`가 다른 **두 항목**으로 적는다. `source: "both"`는 허용하지 않는다 —
   허용하면 "화면에도 있다"는 주장이 근거 없이 통과한다.

3. **신뢰도를 날조하지 않는다.** confidence/status는 열거형만 쓴다. 파이프라인에 정량화
   근거가 없으므로 0.87 같은 값을 만들어내지 않는다. 감사하지 않은 주장은 `unaudited`로
   남아 `verified`와 구분된다.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402

SCHEMA_VERSION = "0.3"

VIDEO_TYPES = ("tutorial", "presentation", "interview", "lecture",
               "demo", "screen-recording", "mixed", "unknown")
EVIDENCE_TYPES = ("slide", "ui", "chart", "code", "table", "text", "other")
CONFIDENCE = ("high", "medium", "low")
VERIFY_STATUS = ("verified", "disputed", "unverifiable", "unaudited")
EVIDENCE_SOURCES = ("transcript", "frame")

# knowledge_items의 type. 사용자 요청 목록(14종)에서 3종을 정리했다:
#   claim → 이미 claims[]가 담당하므로 중복
#   configuration/parameter → 실무에서 경계가 모호해 setting으로 통합
#   artifact → result와 겹침
# **빈 카테고리를 만들지 않는다** — 영상에 없는 type은 배열에 등장하지 않는다.
KNOWLEDGE_TYPES = ("concept", "procedure", "action", "command", "setting",
                   "prerequisite", "result", "criterion", "warning",
                   "example", "comparison")


def evidence_path(cache_dir) -> Path:
    return Path(cache_dir) / "evidence.json"


def _frame_meta(path) -> dict:
    """프레임 파일명에서 타임스탬프·해상도·크롭 여부를 되읽는다.

    파일명 규약은 frames._frame_tag가 만든다: `t<tag>[d<n>]_<res>[c<x>_<y>_<w>_<h>].jpg`
    태그 자체의 자릿수는 영상 길이에 따라 MMSS 또는 HHMMSS로 달라지므로 정규식을 새로
    쓰지 않고 **common.frame_label을 재사용한다** — 역파싱 규칙을 한 곳에 둔다.
    규약을 벗어난 이름은 좌표를 None으로 두되 파일명은 보존한다(조용히 버리지 않는다)."""
    name = path.name if hasattr(path, "name") else Path(path).name
    meta = {"file": name, "t": None, "res": None}
    try:
        meta["t"] = common.parse_ts(common.frame_label(name))
    except (ValueError, IndexError):
        pass
    parts = name.split("_")
    if len(parts) > 1:
        token = parts[1].split(".")[0]
        digits = token.split("c")[0]
        if digits.isdigit():
            meta["res"] = int(digits)
        if "c" in token:
            meta["crop"] = True
    return meta


def classify_hint(sig: dict, tr: dict, duration: float) -> dict:
    """신호만으로 영상 유형 후보를 좁힌다 — **판정이 아니라 힌트다.**

    화면을 봐야 알 수 있는 것(슬라이드인가 IDE인가)은 판독 에이전트가 정한다. 여기서는
    자막 밀도·챕터 수·활동 피크 밀도 세 축만 본다. 힌트가 틀려도 LLM이 덮어쓸 수 있으므로
    과신하지 않는다. 열거형 밖 값은 반환하지 않는다."""
    segs = tr.get("segments") or []
    peaks = (sig.get("activity") or {}).get("peaks") or []
    chapters = sig.get("chapters") or []
    minutes = max(float(duration) / 60.0, 1e-9)
    chars_per_min = sum(len(s.get("text", "")) for s in segs) / minutes
    peaks_per_min = len(peaks) / minutes

    cands, basis = [], []
    if not segs:
        cands.append("screen-recording")
        basis.append("자막 없음")
    if len(chapters) >= 6:
        cands += ["presentation", "lecture"]
        basis.append(f"챕터 {len(chapters)}개")
    if chars_per_min >= 300:
        cands += ["interview", "lecture"]
        basis.append(f"자막 밀도 {chars_per_min:.0f}자/분")
    if peaks_per_min >= 2.5:
        cands += ["tutorial", "demo", "screen-recording"]
        basis.append(f"활동 피크 {peaks_per_min:.1f}/분")
    if not cands:
        cands = ["mixed"]
        basis.append("판별 신호 부족")
    seen, uniq = set(), []
    for c in cands:
        if c in VIDEO_TYPES and c not in seen:
            seen.add(c)
            uniq.append(c)
    return {"candidates": uniq, "basis": " · ".join(basis)}


def build_skeleton(info: dict, sig: dict, tr: dict, frames_kept: list, url: str = "") -> dict:
    """패스1 산출물로 evidence 골격을 만든다. LLM 슬롯(visual_evidence·claims)은 비운 채 반환한다."""
    duration = float(info.get("duration") or 0)
    segs_in = tr.get("segments") or []
    segments = []
    for i, s in enumerate(segs_in):
        start = float(s.get("start") or 0)
        end = float(segs_in[i + 1].get("start") or 0) if i + 1 < len(segs_in) else duration
        segments.append({"idx": i, "start": start, "end": end,
                         "transcript": s.get("text", "")})
    return {
        "schema_version": SCHEMA_VERSION,
        "video": {
            "id": info.get("id", ""),
            "title": info.get("title", ""),
            "url": url or info.get("webpage_url", ""),
            "duration": duration,
            "channel": info.get("uploader", ""),
        },
        "video_type": {"primary": "unknown", "confidence": "low", "basis": "",
                       "hint": classify_hint(sig, tr, duration)},
        "provenance": {
            "schema_version": SCHEMA_VERSION,
            "transcript": {
                "source": tr.get("source", "none"),
                "lang": tr.get("lang", ""),
                "segments": len(segs_in),
                "dupes_removed": tr.get("dupes_removed", 0),
                "flags": list(tr.get("flags") or []),
            },
            "signals": {
                "heatmap": bool(sig.get("heatmap")),
                "chapters": len(sig.get("chapters") or []),
                "desc_timestamps": len(sig.get("desc_timestamps") or []),
                "activity_peaks": len((sig.get("activity") or {}).get("peaks") or []),
                "sponsorblock": len(sig.get("sponsorblock") or []),
                "flags": list(sig.get("flags") or []),
            },
            "frames": {"map": [_frame_meta(p) for p in frames_kept], "zoom": []},
        },
        "segments": segments,
        "visual_evidence": [],
        "claims": [],
        "knowledge_items": [],
        "gaps": [],
        "flags": list(sig.get("flags") or []) + list(tr.get("flags") or []),
    }


def load(cache_dir) -> dict:
    return json.loads(evidence_path(cache_dir).read_text(encoding="utf-8"))


def save(cache_dir, ev: dict) -> Path:
    p = evidence_path(cache_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _next_id(items: list, prefix: str) -> str:
    return f"{prefix}{len(items) + 1}"


def merge(ev: dict, patch: dict) -> dict:
    """LLM 산출물을 골격에 병합한다.

    **append 의미론이 기본이다.** 빌더와 감사가 여러 번 나눠 기여하므로 나중 호출이 앞의
    것을 지우면 안 된다. video_type만 교체 의미론을 갖는다(분류는 단일 값이므로)."""
    for item in patch.get("visual_evidence") or []:
        item = dict(item)
        item.setdefault("id", _next_id(ev["visual_evidence"], "v"))
        ev["visual_evidence"].append(item)
    for item in patch.get("claims") or []:
        item = dict(item)
        item.setdefault("id", _next_id(ev["claims"], "c"))
        item.setdefault("verification", {"status": "unaudited"})
        ev["claims"].append(item)
    for item in patch.get("knowledge_items") or []:
        item = dict(item)
        item.setdefault("id", _next_id(ev.setdefault("knowledge_items", []), "k"))
        ev["knowledge_items"].append(item)
    for g in patch.get("gaps") or []:
        ev["gaps"].append(dict(g))
    for f in patch.get("zoom_frames") or []:
        ev["provenance"]["frames"]["zoom"].append(
            _frame_meta(f) if isinstance(f, str) else dict(f))
    if patch.get("video_type"):
        vt = dict(patch["video_type"])
        vt.setdefault("hint", (ev.get("video_type") or {}).get("hint"))
        ev["video_type"] = vt
    for f in patch.get("flags") or []:
        if f not in ev["flags"]:
            ev["flags"].append(f)
    return ev


def apply_verdicts(ev: dict, verdicts: list) -> dict:
    """감사 판정을 claim id 기준으로 반영한다. 대응 claim이 없으면 조용히 넘기지 않고
    flags에 남긴다 — 감사 결과가 유실되면 unaudited가 verified처럼 보일 수 있다."""
    by_id = {c.get("id"): c for c in ev.get("claims") or []}
    for v in verdicts:
        cid = v.get("claim_id")
        c = by_id.get(cid)
        if c is None:
            ev["flags"].append(f"verdict_orphan: {cid}")
            continue
        c["verification"] = {k: v[k] for k in ("status", "auditor", "note") if k in v}
    return ev


def _known_frames(ev: dict) -> set:
    """provenance에 실제로 기록된 프레임 파일명 집합.

    visual_evidence가 이 집합 밖의 파일명을 가리키면 그 근거는 실재하지 않는다 —
    LLM이 그럴듯한 이름(t9999_1024.jpg)을 지어내는 경우를 잡는다."""
    fr = (ev.get("provenance") or {}).get("frames") or {}
    out = set()
    for bucket in ("map", "zoom"):
        for f in fr.get(bucket) or []:
            name = f.get("file") if isinstance(f, dict) else str(f)
            if name:
                out.add(name)
    return out


def _check_evidence_refs(kind, ident, ev_list, ve_ids, n_segments, errs) -> None:
    """claims와 knowledge_items가 같은 근거 규칙을 쓰므로 한 곳에 둔다.

    **모든 근거는 실재하는 자막 세그먼트나 포착된 프레임으로 추적 가능해야 한다.**
    `frame` ref는 visual_evidence id를, `transcript` ref는 segments 인덱스를 가리키며
    둘 다 범위를 벗어나면 거부한다."""
    if not ev_list:
        errs.append(f"{kind}[{ident}].evidence: empty — 근거 없는 항목은 담지 않는다")
    for e in ev_list:
        src = e.get("source")
        if src not in EVIDENCE_SOURCES:
            errs.append(f"{kind}[{ident}].evidence.source: {src!r} not in {EVIDENCE_SOURCES} "
                        f"— 'both' 대신 transcript/frame 두 항목으로 나눠 적는다")
            continue
        ref = e.get("ref")
        if ref in (None, ""):
            errs.append(f"{kind}[{ident}].evidence.ref: empty for source={src!r}")
        elif src == "frame":
            if ref not in ve_ids:
                errs.append(f"{kind}[{ident}].evidence.ref: {ref!r} not found in "
                            f"visual_evidence — 화면 근거는 실재하는 id를 가리켜야 한다")
        else:
            s = str(ref)
            if not s.isdigit():
                errs.append(f"{kind}[{ident}].evidence.ref: transcript ref는 세그먼트 "
                            f"인덱스(숫자)여야 한다, got {ref!r}")
            elif int(s) >= n_segments:
                errs.append(f"{kind}[{ident}].evidence.ref: transcript 세그먼트 {s} 없음 "
                            f"(총 {n_segments}개) — 근거가 실재하지 않는다")


def validate(ev: dict) -> list:
    """스키마 위반 목록을 반환한다. 빈 리스트면 통과.

    예외를 던지지 않고 목록으로 반환하는 이유: 한 번에 전부 보여줘야 고치는 쪽이 왕복을
    덜 한다. 호출부(CLI)가 비어 있지 않으면 exit 2로 fail-loud 한다."""
    errs = []
    if ev.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version: {ev.get('schema_version')!r} != {SCHEMA_VERSION!r}")

    vt = (ev.get("video_type") or {}).get("primary")
    if vt not in VIDEO_TYPES:
        errs.append(f"video_type.primary: unknown value {vt!r} (allowed: {VIDEO_TYPES})")

    known = _known_frames(ev)
    n_segments = len(ev.get("segments") or [])

    ve_ids = set()
    for v in ev.get("visual_evidence") or []:
        vid = v.get("id", "?")
        ve_ids.add(vid)
        if v.get("type") not in EVIDENCE_TYPES:
            errs.append(f"visual_evidence[{vid}].type: unknown value {v.get('type')!r}")
        if v.get("confidence") not in CONFIDENCE:
            errs.append(f"visual_evidence[{vid}].confidence: must be one of {CONFIDENCE}, "
                        f"got {v.get('confidence')!r} — 신뢰도를 숫자로 날조하지 않는다")
        frame = v.get("frame")
        if not frame:
            errs.append(f"visual_evidence[{vid}].frame: missing frame provenance")
        elif frame not in known:
            errs.append(f"visual_evidence[{vid}].frame: {frame!r} not in provenance.frames "
                        f"— 실재하지 않는 프레임을 근거로 쓸 수 없다")

    for c in ev.get("claims") or []:
        cid = c.get("id", "?")
        _check_evidence_refs("claims", cid, c.get("evidence") or [],
                             ve_ids, n_segments, errs)
        st = (c.get("verification") or {}).get("status")
        if st not in VERIFY_STATUS:
            errs.append(f"claims[{cid}].verification.status: unknown value {st!r} "
                        f"(allowed: {VERIFY_STATUS})")

    for k in ev.get("knowledge_items") or []:
        kid = k.get("id", "?")
        if k.get("type") not in KNOWLEDGE_TYPES:
            errs.append(f"knowledge_items[{kid}].type: unknown value {k.get('type')!r} "
                        f"(allowed: {KNOWLEDGE_TYPES})")
        if not str(k.get("content") or "").strip():
            errs.append(f"knowledge_items[{kid}].content: empty")
        _check_evidence_refs("knowledge_items", kid, k.get("evidence") or [],
                             ve_ids, n_segments, errs)
    return errs


def summary_line(ev: dict) -> str:
    p = ev["provenance"]
    return (f"EVIDENCE schema={ev['schema_version']} "
            f"type={ev['video_type']['primary']} "
            f"segments={len(ev['segments'])} "
            f"visual={len(ev['visual_evidence'])} "
            f"claims={len(ev['claims'])} "
            f"knowledge={len(ev.get('knowledge_items') or [])} "
            f"gaps={len(ev['gaps'])} "
            f"map_frames={len(p['frames']['map'])} "
            f"zoom_frames={len(p['frames']['zoom'])}")


def main() -> int:
    common.utf8_stdout()
    ap = argparse.ArgumentParser(description="evidence.json 병합·검증")
    ap.add_argument("cache_dir")
    ap.add_argument("--merge", help="병합할 patch json 경로")
    ap.add_argument("--verdicts", help="감사 판정 json 경로 (claim_id/status/auditor/note 배열)")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    cd = Path(args.cache_dir)
    if not evidence_path(cd).exists():
        print(f"ERROR: {evidence_path(cd)} 없음 — analyze.py를 먼저 실행한다", file=sys.stderr)
        return 2
    ev = load(cd)

    # 쓰기 연산은 **검증을 통과한 것만 저장한다**. 먼저 저장하고 나중에 검증하면 거부된
    # patch가 evidence.json에 남아 스키마 게이트가 무의미해진다 (E2E 실측에서 발견:
    # exit 2를 받고도 잘못된 claim 2건·visual_evidence 1건이 파일에 들어갔다).
    # 사본에 적용해 검증한 뒤 통과할 때만 교체한다.
    writing = bool(args.merge or args.verdicts)
    if writing:
        candidate = json.loads(json.dumps(ev))
        if args.merge:
            candidate = merge(candidate, json.loads(Path(args.merge).read_text(encoding="utf-8")))
        if args.verdicts:
            candidate = apply_verdicts(
                candidate, json.loads(Path(args.verdicts).read_text(encoding="utf-8")))
        errs = validate(candidate)
        if errs:
            for e in errs:
                print(f"INVALID: {e}", file=sys.stderr)
            print("REJECTED: evidence.json은 변경되지 않았다", file=sys.stderr)
            return 2
        ev = candidate
        save(cd, ev)

    if args.summary:
        print(summary_line(ev))
    if args.validate:
        errs = validate(ev)
        if errs:
            for e in errs:
                print(f"INVALID: {e}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
