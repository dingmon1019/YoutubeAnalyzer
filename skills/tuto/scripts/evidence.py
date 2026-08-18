"""evidence.json — 영상 분석의 구조화 산출물.

설계 원칙 세 가지:

1. **결정론적 골격만 파이썬이 만든다.** 비디오 메타·자막 세그먼트·프레임 provenance·신호
   요약은 계산 가능하므로 여기서 만들고, 시각 증거(visual_evidence)와 주장(claims)은
   화면을 본 LLM이 판독해 병합한다. 산문 렌더링(video.md)은 이 모듈의
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
import re
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

# 표본 감사 우선순위 — **호출한 에이전트의 행동에 영향을 주는 정도** 순이다.
# 잘못 판독된 `command`("pip install package-x")나 `setting`("CUDA 12.6")은 단순 주장
# 오류보다 실전에서 훨씬 위험하다. 영상 유형별 고정 비율은 만들지 않는다 — 존재하는
# 항목 중에서만 이 순서로 뽑는다(개념 영상이면 자연히 claim/concept이 올라온다).
AUDIT_PRIORITY = ("command", "setting", "action", "criterion", "prerequisite",
                  "warning", "procedure", "result", "comparison",
                  "claim", "concept", "example")

# 시각 관측(visual-coverage.json)의 kind. 새 온톨로지를 만들지 않고 KNOWLEDGE_TYPES를
# 재사용해 커버리지 대조가 `kind ↔ knowledge type`으로 직접 이어지게 한다.
# `numeric`은 "수치가 화면에 보인다"는 신호, `other`는 분류 애매한 경우.
OBSERVATION_KINDS = KNOWLEDGE_TYPES + ("numeric", "other")

# 결정론적 교차 대조 — LLM 없이 "같은 값의 판독이 갈린" 자리를 찾는다.
# 실측(2026-08-18): 표본 감사 6건이 4편 연속 수정 0건을 낸 반면, 실제 오류 2건
# (3f4a625를 3f4a0625로 오독)은 표본 밖에 있었다. 이 유형은 같은 값이 여러 프레임에
# 반복 등장한다는 성질을 이용하면 비용 0으로 잡힌다.
_TOKEN_HEX = re.compile(r"\b[0-9a-f]{6,10}\b")
_TOKEN_NUM = re.compile(r"\b\d{3,}\b")


def _near_miss(a: str, b: str) -> bool:
    """편집거리 1 이내인가 (같은 문자열은 제외). 치환 1회 또는 삽입·삭제 1회."""
    if a == b:
        return False
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long = (a, b) if la < lb else (b, a)
    i = j = skipped = 0
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = 1
            j += 1
    return True


def cross_check_values(ev: dict) -> list:
    """visual_evidence의 값에서 해시·수치 토큰을 뽑아 판독이 갈린 쌍을 찾는다.

    반환: [{"values": [a, b], "ids": [id_a, id_b], "kind": "hash"|"numeric"}]
    같은 토큰의 반복은 정상이므로 제외하고, 편집거리 1인 쌍만 남긴다."""
    buckets = {"hash": {}, "numeric": {}}
    for ve in ev.get("visual_evidence") or []:
        if not isinstance(ve, dict):
            continue
        vid = ve.get("id")
        if not vid:
            continue  # id 없는 항목은 건너뛴다 — audit_candidates가 항상 호출하므로 크래시하면 안 된다
        val = str(ve.get("value", ""))
        for kind, rx in (("hash", _TOKEN_HEX), ("numeric", _TOKEN_NUM)):
            for tok in rx.findall(val.lower()):
                if kind == "hash" and not any(c in "abcdef" for c in tok):
                    # 순수 숫자는 numeric 버킷 전담 — 커밋 해시로 오분류되면
                    # CROSSCHECK가 같은 쌍을 두 번 낸다
                    continue
                buckets[kind].setdefault(tok, set()).add(vid)
    out = []
    for kind, toks in buckets.items():
        keys = sorted(toks)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                if _near_miss(a, b):
                    out.append({"values": [a, b], "kind": kind,
                                "ids": sorted(toks[a] | toks[b])})
    return out


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


def parse_frame_lines(text: str) -> list:
    """zoom.py 출력이나 평문 목록에서 프레임 **파일명**을 뽑는다.

    zoom.py는 `FRAME <절대경로> t=MM:SS` 형식으로 찍는다. 그 출력을 그대로 먹일 수 있어야
    오케스트레이터가 §3 직후 손쉽게 등록한다 — 경로를 손으로 옮겨 적게 하면 오타가 난다."""
    names = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("zoom:"):
            continue
        if line.startswith("FRAME "):
            parts = line.split()
            if len(parts) < 2:
                continue
            line = parts[1]
        name = line.replace("\\", "/").rsplit("/", 1)[-1]
        if name.lower().endswith((".jpg", ".jpeg", ".png")):
            names.append(name)
    return names


def register_frames(ev: dict, frames: list, bucket: str = "zoom") -> dict:
    """추출된 프레임을 provenance에 등록한다. 같은 파일명은 한 번만 들어간다.

    **이건 오케스트레이터의 책임이다.** §3이 zoom.py로 뽑은 프레임을 파이프라인이 이미
    아는데 빌더에게 재신고시키면 계약이 깨진다 — E2E 실측에서 12건이 그렇게 거부됐다."""
    dest = ev.setdefault("provenance", {}).setdefault("frames", {}).setdefault(bucket, [])
    have = {f.get("file") for f in dest if isinstance(f, dict)}
    for item in frames or []:
        meta = _frame_meta(item) if isinstance(item, str) else dict(item)
        if meta.get("file") and meta["file"] not in have:
            dest.append(meta)
            have.add(meta["file"])
    return ev


def knowledge_digest(ev: dict) -> list:
    """커버리지 감사가 대조할 **evidence의 실제 지식 목록**.

    커버리지 감사의 심판 대상은 `video.md`의 섹션 제목이 아니다 — adaptive 문서는
    "## Phase 1" 같은 제목만으로 내부에 무엇이 들어갔는지 알 수 없다. 정본인
    evidence.json의 claims + knowledge_items를 대조해야 **evidence 자체의 누락**을 잡는다.

    순서: 소스 → evidence completeness → (그다음) evidence → video.md rendering."""
    out = []
    for k in ev.get("knowledge_items") or []:
        if isinstance(k, dict) and k.get("content"):
            out.append(f"[{k.get('type', '?')}] {k['content']}")
    for c in ev.get("claims") or []:
        if isinstance(c, dict) and c.get("claim"):
            out.append(f"[claim] {c['claim']}")
    return out


def observations_path(cache_dir) -> Path:
    return Path(cache_dir) / "visual-coverage.json"


def load_observations(cache_dir) -> list:
    """§2 판독 에이전트가 남긴 시각 관측. 없으면 빈 리스트."""
    p = observations_path(cache_dir)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("observations", []) if isinstance(data, dict) else (data or [])


def validate_observations(obs: list, ev: dict) -> list:
    """시각 관측의 스키마·provenance를 검사한다.

    관측은 **검증되지 않은 존재 신호**다 — 정확한 값의 정본이 아니다. 그래서 evidence.json에
    섞지 않고 별도 산출물로 두지만, 프레임 provenance만큼은 evidence와 같은 기준으로 본다.
    없는 프레임을 가리키는 관측은 커버리지 후보를 헛되이 만들어낸다."""
    errs = []
    known = _known_frames(ev)
    for i, o in enumerate(obs or []):
        if not isinstance(o, dict):
            errs.append(f"observations[{i}]: 객체여야 한다, got {type(o).__name__}")
            continue
        if o.get("kind") not in OBSERVATION_KINDS:
            errs.append(f"observations[{i}].kind: unknown value {o.get('kind')!r} "
                        f"(allowed: {OBSERVATION_KINDS})")
        if not str(o.get("observation") or "").strip():
            errs.append(f"observations[{i}].observation: empty")
        try:
            float(o.get("timestamp"))
        except (TypeError, ValueError):
            errs.append(f"observations[{i}].timestamp: 숫자여야 한다, got {o.get('timestamp')!r}")
        frame = o.get("frame")
        if not frame:
            errs.append(f"observations[{i}].frame: missing frame provenance")
        elif known and frame not in known:
            errs.append(f"observations[{i}].frame: {frame!r} not in provenance.frames")
    return errs


def _knowledge_points(ev: dict) -> list:
    """(type, timestamp) 목록 — 관측 대조용. claims는 type을 'claim'으로 본다."""
    pts = []
    for k in ev.get("knowledge_items") or []:
        if isinstance(k, dict):
            try:
                pts.append((k.get("type"), float(k.get("timestamp"))))
            except (TypeError, ValueError):
                pass
    for c in ev.get("claims") or []:
        if isinstance(c, dict):
            try:
                pts.append(("claim", float(c.get("timestamp"))))
            except (TypeError, ValueError):
                pass
    return pts


def uncovered_observations(ev: dict, obs: list, window: float = 20.0) -> list:
    """evidence가 통째로 놓친 것으로 **의심되는** 시각 관측을 고른다.

    이 프로젝트의 핵심 차별점은 자막에 없고 화면에만 있는 정보를 읽는 것이다. 그런데
    빌더가 그걸 놓치면 자막 기반 커버리지 감사도 **존재 자체를 모른다** — 그게 사각지대다.

    규칙: 관측 시각 ±window초 안에 **evidence 항목이 하나도 없으면** 후보.

    **kind 일치는 보지 않는다** — 실측으로 폐기한 설계다. 판독 에이전트와 빌더는 같은
    화면을 다르게 분류한다. 실측(t1-XAN6AyOs): t=492s에 evidence 항목이 10건이나 있는데
    아무것도 `comparison` 타입이 아니라는 이유로 후보가 됐다(판독은 "비교 카드", 빌더는
    "claim"). kind 일치를 요구하면 오탐이 11건 중 8건까지 올라간다.

    **window=20초는 실측으로 정했다.** 3편 스윕 결과:

        window  모드    PlMpk   KEidt   t1-XA   진짜누락(ablation)
        20      loose   0/10    0/9     2/11    검출 O   ← 채택
        30      loose   0/10    0/9     2/11    검출 X
        45      loose   0/10    0/9     1/11    검출 X
        45      strict  0/10    3/9     8/11    검출 O (오탐 과다)

    30초 이상이면 근처의 무관한 항목이 진짜 누락을 덮어버린다(ablation에서 28초 떨어진
    procedure가 빠진 command를 가렸다). 10~15초는 오탐이 늘기 시작한다.

    **이건 힌트지 판정이 아니다.** 최종 판단은 커버리지 감사 에이전트가 원본 프레임·자막으로
    재확인해서 내린다."""
    pts = [t for _, t in _knowledge_points(ev)]
    out = []
    for o in obs or []:
        if not isinstance(o, dict):
            continue
        try:
            t = float(o.get("timestamp"))
        except (TypeError, ValueError):
            continue
        if not any(abs(pt - t) <= window for pt in pts):
            out.append(o)
    return out


def coverage_input(ev: dict, obs: list, window: float = 20.0) -> str:
    """커버리지 감사 에이전트에게 줄 대조 블록."""
    lines = ["== EVIDENCE DIGEST =="]
    lines += knowledge_digest(ev) or ["(비어 있음)"]
    lines.append("")
    lines.append("== VISUAL OBSERVATIONS (존재 신호 — 값의 정본이 아니다) ==")
    if obs:
        for o in obs:
            if isinstance(o, dict):
                lines.append(f"[{common.fmt_ts(float(o.get('timestamp', 0)))}] "
                             f"{o.get('kind')} — {o.get('observation')} ({o.get('frame')})")
    else:
        lines.append("(없음)")
    unc = uncovered_observations(ev, obs, window)
    lines.append("")
    lines.append(f"== 결정론적 사전 필터: 근처(±{window:.0f}s)에 같은 kind가 없는 관측 ==")
    if unc:
        for o in unc:
            lines.append(f"[{common.fmt_ts(float(o.get('timestamp', 0)))}] "
                         f"{o.get('kind')} — {o.get('observation')} ({o.get('frame')})")
    else:
        lines.append("(없음)")
    return "\n".join(lines)


def load(cache_dir) -> dict:
    return json.loads(evidence_path(cache_dir).read_text(encoding="utf-8"))


def save(cache_dir, ev: dict) -> Path:
    p = evidence_path(cache_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _next_id(items: list, prefix: str) -> str:
    return f"{prefix}{len(items) + 1}"


# ── 컴팩트 patch 라인 확장기 — LLM이 JSON 보일러플레이트(따옴표·중괄호·필드명)를
# 출력하던 토큰을 30~40% 줄인다. 확장 결과는 기존 merge/validate 게이트를 그대로 탄다.

def _parse_refs(spec: str, id_offset: int = 0) -> list:
    out = []
    for tok in (spec or "").split(";"):
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith("v"):
            n = tok[1:]
            if not n.isdigit():
                raise ValueError(f"알 수 없는 근거 참조: {tok!r} (v#=frame, t#=transcript)")
            out.append({"source": "frame", "ref": f"v{id_offset + int(n)}"})
        elif tok.startswith("t"):
            out.append({"source": "transcript", "ref": tok[1:]})
        else:
            raise ValueError(f"알 수 없는 근거 참조: {tok!r} (v#=frame, t#=transcript)")
    return out


def expand_lines(text: str, id_offset: int = 0) -> dict:
    """TAB 구분 라인(T/V/K/C/G)을 evidence patch dict로 확장한다. 형식 위반은
    ValueError로 fail-loud — 조용히 건너뛰면 지식이 소리 없이 유실된다. 값 내부의
    탭은 작성 시 스페이스로 치환한다.

    id_offset: 이미 존재하는 visual_evidence 개수. --from-lines가 재호출되면(교차대조
    정정·커버리지 보강) V의 id를 v{id_offset+1}..부터 부여해 기존 v-id와 충돌하지
    않게 하고, 같은 배치의 K/C가 쓰는 로컬 v# 참조도 같은 오프셋으로 재매핑한다
    (LLM은 항상 로컬 v1..vN으로 쓴다)."""
    patch = {"visual_evidence": [], "claims": [], "knowledge_items": [], "gaps": []}
    vn = 0
    for ln, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        f = raw.split("\t")
        kind = f[0].strip()
        try:
            if kind == "T":
                patch["video_type"] = {"primary": f[1], "confidence": f[2], "basis": f[3]}
            elif kind == "V":
                vn += 1
                patch["visual_evidence"].append({
                    "id": f"v{id_offset + vn}", "type": f[1], "timestamp": float(f[2]),
                    "frame": f[3], "confidence": f[4], "value": f[5]})
            elif kind == "K":
                patch["knowledge_items"].append({
                    "type": f[1], "timestamp": float(f[2]),
                    "evidence": _parse_refs(f[3], id_offset), "content": f[4]})
            elif kind == "C":
                c = {"timestamp": float(f[1]), "evidence": _parse_refs(f[2], id_offset),
                     "claim": f[3], "verification": {"status": "unaudited"}}
                if len(f) > 4 and f[4].startswith("conflict="):
                    a, _, b = f[4][len("conflict="):].partition("=>")
                    c["conflict"] = {"transcript": a, "screen": b}
                patch["claims"].append(c)
            elif kind == "G":
                patch["gaps"].append({"start": float(f[1]), "end": float(f[2]), "reason": f[3]})
            else:
                raise ValueError(f"알 수 없는 레코드 종류: {kind!r}")
        except (IndexError, ValueError) as e:
            # 모든 예외를 행 번호로 수렴시킨다 — 특수 케이스 재-raise는 행 번호를
            # 잃어 "INVALID 보고 1회 수정" 왕복을 깬다. 원본 메시지는 `— {e}`에 남는다.
            raise ValueError(f"{ln}행 형식 오류 ({kind}): {raw[:80]!r} — {e}") from e
    return patch


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
        item.setdefault("verification", {"status": "unaudited"})
        ev["knowledge_items"].append(item)
    for g in patch.get("gaps") or []:
        # 형식이 어긋나도 여기서 죽지 않는다 — 그대로 실어 보내고 validate가 잡는다.
        # merge가 예외를 던지면 스택 트레이스+exit 1이 나와 "INVALID 줄을 빌더에게
        # 돌려준다"는 계약이 깨진다 (E2E 실측에서 발생).
        ev["gaps"].append(dict(g) if isinstance(g, dict) else g)
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


def _audit_index(ev: dict) -> dict:
    """감사 대상 id → 항목. claims와 knowledge_items를 한 네임스페이스로 본다
    (`c*`/`k*` 접두사가 이미 서로 구분해 준다)."""
    idx = {}
    for coll in ("claims", "knowledge_items"):
        for item in ev.get(coll) or []:
            if isinstance(item, dict) and item.get("id"):
                idx[item["id"]] = item
    return idx


def apply_verdicts(ev: dict, verdicts: list) -> dict:
    """감사 판정을 반영한다. **claims와 knowledge_items 양쪽**을 대상으로 한다.

    대응 항목이 없으면 조용히 넘기지 않고 flags에 남긴다 — 감사 결과가 유실되면
    unaudited가 verified처럼 보일 수 있다.
    `claim_id`는 구 형식 호환용이고 새 형식은 `id`다."""
    idx = _audit_index(ev)
    for v in verdicts:
        vid = v.get("id") or v.get("claim_id") or v.get("item_id")
        target = idx.get(vid)
        if target is None:
            ev.setdefault("flags", []).append(f"verdict_orphan: {vid}")
            continue
        target["verification"] = {k: v[k] for k in ("status", "auditor", "note") if k in v}
    return ev


def audit_candidates(ev: dict, limit: int = 3) -> list:
    """표본 감사 후보를 뽑는다 — claims와 knowledge_items 통합.

    **모든 항목을 감사하지 않는다.** 표본 감사 원칙을 유지하되, 호출한 에이전트의
    행동에 영향을 크게 주는 항목(command/setting/action/criterion…)을 먼저 뽑는다.
    이미 감사된(unaudited가 아닌) 항목은 제외한다."""
    rank = {t: i for i, t in enumerate(AUDIT_PRIORITY)}
    pool = []
    for k in ev.get("knowledge_items") or []:
        if not isinstance(k, dict):
            continue
        if (k.get("verification") or {}).get("status", "unaudited") != "unaudited":
            continue
        pool.append({"kind": "knowledge_item", "id": k.get("id"), "type": k.get("type"),
                     "content": k.get("content", ""), "timestamp": k.get("timestamp"),
                     "evidence": k.get("evidence") or []})
    for c in ev.get("claims") or []:
        if not isinstance(c, dict):
            continue
        if (c.get("verification") or {}).get("status", "unaudited") != "unaudited":
            continue
        pool.append({"kind": "claim", "id": c.get("id"), "type": "claim",
                     "content": c.get("claim", ""), "timestamp": c.get("timestamp"),
                     "evidence": c.get("evidence") or []})
    # 교차 대조에 걸린 근거를 쓰는 항목은 표본 최상위로 — 표본 감사가 놓친 실제 오류
    # 유형이 정확히 이것이었다(2026-08-18). 단, 승격은 **최대 1건**이다 — 표본이 3건으로
    # 줄어든 체제에서 flag된 항목이 여러 개면 오탐 하나가 슬롯을 과점한다
    # (2026-08-18 최종 리뷰). flag된 항목이 여럿이면 AUDIT_PRIORITY 상위 1건만 올리고
    # 나머지는 flag가 없는 것처럼 원래 순위로 되돌아간다.
    flagged = set()
    for f in cross_check_values(ev):
        flagged.update(f["ids"])
    def _is_flagged(x):
        return any(e.get("ref") in flagged for e in x["evidence"]
                   if isinstance(e, dict) and e.get("source") == "frame")
    flagged_items = [x for x in pool if _is_flagged(x)]
    promoted_id = None
    if flagged_items:
        promoted_id = min(
            flagged_items,
            key=lambda x: (rank.get(x["type"], len(rank)), str(x["id"])),
        )["id"]
    def _flag_rank(x):
        return 0 if promoted_id is not None and x["id"] == promoted_id else 1
    pool.sort(key=lambda x: (_flag_rank(x), rank.get(x["type"], len(rank)), str(x["id"])))
    return pool[:limit]


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

    for field in ("visual_evidence", "claims", "knowledge_items", "gaps"):
        for i, item in enumerate(ev.get(field) or []):
            if not isinstance(item, dict):
                errs.append(f"{field}[{i}]: 객체여야 한다, got {type(item).__name__} "
                            f"— {str(item)[:60]!r}")

    ve_ids = set()
    for v in ev.get("visual_evidence") or []:
        if not isinstance(v, dict):
            continue
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

    # 중복 id 심층 방어 — expand_lines의 id_offset이 잘못되거나(호출부 버그) 두 소스가
    # 겹쳐 써도 여기서 잡는다. merge()의 setdefault는 id가 이미 있으면 그냥 통과시키므로
    # 이 검사가 마지막 방어선이다.
    _seen_ve_ids, _dupe_ve_ids = [], []
    for v in ev.get("visual_evidence") or []:
        if not isinstance(v, dict):
            continue
        vid = v.get("id")
        if vid in _seen_ve_ids and vid not in _dupe_ve_ids:
            _dupe_ve_ids.append(vid)
        _seen_ve_ids.append(vid)
    for vid in _dupe_ve_ids:
        errs.append(f"visual_evidence: 중복 id {vid!r}")

    for c in ev.get("claims") or []:
        if not isinstance(c, dict):
            continue
        cid = c.get("id", "?")
        _check_evidence_refs("claims", cid, c.get("evidence") or [],
                             ve_ids, n_segments, errs)
        st = (c.get("verification") or {}).get("status")
        if st not in VERIFY_STATUS:
            errs.append(f"claims[{cid}].verification.status: unknown value {st!r} "
                        f"(allowed: {VERIFY_STATUS})")

    for k in ev.get("knowledge_items") or []:
        if not isinstance(k, dict):
            continue
        kid = k.get("id", "?")
        if k.get("type") not in KNOWLEDGE_TYPES:
            errs.append(f"knowledge_items[{kid}].type: unknown value {k.get('type')!r} "
                        f"(allowed: {KNOWLEDGE_TYPES})")
        if not str(k.get("content") or "").strip():
            errs.append(f"knowledge_items[{kid}].content: empty")
        _check_evidence_refs("knowledge_items", kid, k.get("evidence") or [],
                             ve_ids, n_segments, errs)
        kst = (k.get("verification") or {}).get("status")
        if kst is not None and kst not in VERIFY_STATUS:
            errs.append(f"knowledge_items[{kid}].verification.status: unknown value "
                        f"{kst!r} (allowed: {VERIFY_STATUS})")
    return errs


# ── video.md 렌더러 — "정본은 evidence.json, video.md는 그것의 렌더링"의 문자적 구현.
# LLM이 16KB 문서를 출력하던 비용(solo 실측 output의 약 절반)을 0으로 만든다.
# 자율 구성 대신 고정 템플릿 — 값·근거는 evidence와 바이트 단위로 동일하다.

_TYPE_LABELS = {
    "command": "명령어", "setting": "설정", "action": "조작", "criterion": "판단 기준",
    "prerequisite": "준비조건", "warning": "주의사항", "procedure": "절차",
    "result": "결과", "comparison": "비교", "claim": "주장", "concept": "개념",
    "example": "예시",
}


def _safe_ts(val) -> float:
    """null·비수치 timestamp를 0.0으로 — --render는 저장된 파일에 단독 실행될 수 있어
    validate를 안 거친 값이 올 수 있다 (파일 내 기존 try/except 관례와 동일)."""
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _evidence_tag(item: dict) -> str:
    srcs = {e.get("source") for e in (item.get("evidence") or []) if isinstance(e, dict)}
    if "frame" in srcs and "transcript" in srcs:
        return "화면+자막"
    if "frame" in srcs:
        return "화면 확인"
    return "자막 근거만"


def _item_line(item: dict, text_key: str) -> str:
    t = common.fmt_ts(_safe_ts(item.get("timestamp")))
    line = f"- {item.get(text_key, '')} `(t={t})` [{_evidence_tag(item)}]"
    cf = item.get("conflict")
    if isinstance(cf, dict) and cf:
        line += f" — ⚠️ 자막 \"{cf.get('transcript', '')}\" vs 화면 \"{cf.get('screen', '')}\" (화면 채택)"
    return line


def render_video_md(ev: dict, cross_flags: int = 0, coverage_added: int = 0) -> str:
    v = ev.get("video") or {}
    vt = ev.get("video_type") or {}
    lines = [
        f"# {v.get('title', '(제목 없음)')}",
        "",
        f"- **URL**: {v.get('url', '')}",
        f"- **길이**: {common.fmt_ts(_safe_ts(v.get('duration')))} · **채널**: {v.get('channel', '')}",
        f"- **영상 유형**: {vt.get('primary', '?')} ({vt.get('confidence', '?')}) — {vt.get('basis', '')}",
        f"- **검증**: 교차 대조 flag {cross_flags}건 · 커버리지 보강 {coverage_added}건 · "
        "**표본 감사 미실시 — 근거는 프레임·자막으로 추적 가능하나 독립 검증되지 않음**",
        "",
        "## 핵심 지식",
        "",
    ]
    items = ev.get("knowledge_items") or []
    rank = {t: i for i, t in enumerate(AUDIT_PRIORITY)}
    for typ in sorted({i.get("type") for i in items}, key=lambda t: rank.get(t, 99)):
        lines.append(f"### {_TYPE_LABELS.get(typ, typ)}")
        for it in items:
            if it.get("type") == typ:
                lines.append(_item_line(it, "content"))
        lines.append("")
    claims = ev.get("claims") or []
    if claims:
        lines += ["## 주장·설명", ""]
        for c in claims:
            lines.append(_item_line(c, "claim"))
        lines.append("")
    lines += ["## 누락 후보", ""]
    for g in ev.get("gaps") or []:
        if isinstance(g, dict):
            lines.append(f"- {common.fmt_ts(_safe_ts(g.get('start')))}–"
                         f"{common.fmt_ts(_safe_ts(g.get('end')))} 구간 미확인 ({g.get('reason', '')})")
    for fl in ev.get("flags") or []:
        lines.append(f"- flag: {fl}")
    if not (ev.get("gaps") or ev.get("flags")):
        lines.append("- (기록된 공백 없음)")
    lines += ["", "---", f"*evidence.json이 정본이다 — 이 문서는 `evidence.py --render`가 생성했다.*", ""]
    return "\n".join(lines)


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
    ap.add_argument("--from-lines", dest="from_lines",
                    help="컴팩트 TSV 라인 파일을 patch로 확장해 병합 (T/V/K/C/G). "
                    "값 내부의 탭은 작성 시 스페이스로 치환한다")
    ap.add_argument("--verdicts", help="감사 판정 json 경로 (claim_id/status/auditor/note 배열)")
    ap.add_argument("--add-frames", dest="add_frames",
                    help="확대 프레임 등록 — zoom.py 출력을 담은 파일 경로 (FRAME 줄 파싱)")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--audit-candidates", dest="audit_candidates", type=int, metavar="N",
                    help="표본 감사 후보 N건 출력 (행동 영향도 높은 순, 미감사 항목만)")
    ap.add_argument("--coverage-input", dest="coverage_input", metavar="OBS_JSON",
                    nargs="?", const="", help="커버리지 감사 입력 출력 "
                    "(digest + 시각 관측 + 사전 필터). 경로 생략 시 캐시의 visual-coverage.json")
    ap.add_argument("--digest", action="store_true",
                    help="커버리지 감사용 지식 목록 출력 (claims + knowledge_items)")
    ap.add_argument("--cross-check", dest="cross_check", action="store_true",
                    help="해시·수치 판독이 갈린 자리 검출 (LLM 없이, 감사 후보 선정용)")
    ap.add_argument("--render", action="store_true",
                    help="evidence.json에서 video.md를 결정론적으로 생성")
    ap.add_argument("--cross-flags", dest="cross_flags", type=int, default=0)
    ap.add_argument("--coverage-added", dest="coverage_added", type=int, default=0)
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
    writing = bool(args.merge or args.verdicts or args.add_frames or args.from_lines)
    if writing:
        candidate = json.loads(json.dumps(ev))
        if args.add_frames:
            names = parse_frame_lines(Path(args.add_frames).read_text(encoding="utf-8"))
            candidate = register_frames(candidate, names)
        if args.from_lines:
            try:
                candidate = merge(candidate, expand_lines(
                    Path(args.from_lines).read_text(encoding="utf-8"),
                    id_offset=len(candidate.get("visual_evidence") or [])))
            except ValueError as e:
                print(f"INVALID: {e}", file=sys.stderr)
                return 2
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

    if args.cross_check:
        flags = cross_check_values(ev)
        for f in flags:
            print(f"CROSSCHECK {f['kind']}\t{' vs '.join(f['values'])}\t{','.join(f['ids'])}")
        if not flags:
            print("CROSSCHECK none")
    if args.render:
        md = render_video_md(ev, args.cross_flags, args.coverage_added)
        out = Path(cd) / "video.md"
        out.write_text(md, encoding="utf-8", newline="\n")
        print(f"RENDERED {out}")
    if args.summary:
        print(summary_line(ev))
    if args.digest:
        for line in knowledge_digest(ev):
            print(line)
    if args.coverage_input is not None:
        obs = (json.loads(Path(args.coverage_input).read_text(encoding="utf-8")).get("observations", [])
               if args.coverage_input else load_observations(cd))
        oerrs = validate_observations(obs, ev)
        if oerrs:
            for e in oerrs:
                print(f"INVALID: {e}", file=sys.stderr)
            return 2
        print(coverage_input(ev, obs))
    if args.audit_candidates:
        for c in audit_candidates(ev, limit=args.audit_candidates):
            refs = " ".join(f"{e.get('source')}:{e.get('ref')}" for e in c["evidence"])
            print(f"{c['id']}	{c['kind']}	{c['type']}	{refs}	{c['content']}")
    if args.validate:
        errs = validate(ev)
        if errs:
            for e in errs:
                print(f"INVALID: {e}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
