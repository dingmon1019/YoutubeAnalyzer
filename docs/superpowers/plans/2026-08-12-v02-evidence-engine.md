# YoutubeAnalyzer v0.2 — Evidence Engine 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `guide.md`가 아니라 **`evidence.json`**을 파이프라인의 중심 산출물로 만들고, 그 위에 GUIDE / INSIGHT / ASK 세 모드를 얹어 튜토리얼 전용 도구를 범용 영상 근거 엔진으로 확장한다.

**Architecture:** Python 층(1,257줄)은 이미 튜토리얼 가정이 없으므로 **그대로 둔다.** 새 모듈 `evidence.py` 하나를 추가해 결정론적 골격(비디오 메타·자막 세그먼트·프레임 provenance·신호)을 만들고, LLM이 산출한 시각 증거·주장·감사 결과를 **병합·검증**한다. 렌더링(guide.md/insight.md 산문)은 LLM이 evidence.json을 읽고 수행한다 — Python은 산문을 만들지 않는다. 튜토리얼 종속은 전부 `SKILL.md` 프롬프트 층에 있으므로 거기만 범용화한다.

**Tech Stack:** Python 3.11 표준 라이브러리만 (신규 의존성 0). pytest. 기존 ffmpeg/yt-dlp 파이프라인 무변경.

## Global Constraints

- **신규 런타임 의존성 추가 금지.** `evidence.py`는 `json`·`pathlib`·`re`만 쓴다.
- **기존 테스트 101개 전부 통과 유지.** 깨지면 그 태스크는 실패다.
- **기존 스크립트의 공개 시그니처 변경 금지** — `analyze.py`·`zoom.py`·`transcribe.py`·`signals.py`·`frames.py`·`common.py`·`setup.py`의 기존 함수 이름·인자·반환형을 바꾸지 않는다. 추가만 한다.
- **`/tuto <url>` 무인자 호출은 GUIDE 모드로 동작해야 한다** (backward compatibility).
- **신뢰도를 숫자로 날조하지 않는다.** `confidence`는 `high|medium|low`, `status`는 `verified|disputed|unverifiable|unaudited` 열거형만 쓴다. 0.87 같은 값을 만들어내지 않는다.
- **transcript 증거와 visual 증거를 같은 배열에 섞지 않는다.** 출처가 구조로 구분돼야 한다.
- **화면에 없는 값을 자막으로 채우지 않는다** — 기존 검증 규칙 4를 evidence 스키마 차원에서도 강제한다.
- Windows 기준. 모든 파이썬 실행은 `python`(not `python3`), stdout은 `common.utf8_stdout()`로 UTF-8 강제.
- 파일 저장 시 파이프 조기 종료 조합(`| head`, `| tee | head`) 금지 — 조용한 절단 사고 재발 방지.

---

## 파일 구조

| 파일 | 책임 | 상태 |
|---|---|---|
| `skills/tuto/scripts/evidence.py` | evidence.json 스키마·골격 생성·병합·검증·CLI | **신규** |
| `skills/tuto/scripts/analyze.py` | 패스1 끝에 evidence 골격 자동 생성 + `== EVIDENCE ==` 줄 출력 | 수정 (추가만) |
| `skills/tuto/SKILL.md` | 모드 분기 · 범용화 · evidence 산출 계약 | 수정 |
| `.claude-plugin/plugin.json` `.claude-plugin/marketplace.json` | 설명·트리거 범용화 | 수정 |
| `README.md` | 포지셔닝 변경 (수치·평가 섹션 보존) | 수정 |
| `tests/test_evidence.py` | evidence.py 단위 테스트 | **신규** |
| `docs/eval/evidence-schema.md` | 스키마 정본 문서 | **신규** |

### 왜 `visual_evidence`를 세그먼트 안이 아니라 최상위에 두는가

사용자 예시는 `segments[].visual_evidence[]` 중첩이지만, 실제 파이프라인에서는 **한 프레임이 여러 세그먼트에 걸친 주장의 근거**가 된다(예: 6:55의 요약표가 스텝 5·6·7의 근거). 중첩하면 같은 프레임을 복제해야 하고 provenance가 갈라진다. 최상위 배열 + `id` 참조로 정규화한다.

### `conflict` 필드를 1급으로 두는 이유

"자막은 16배, 화면은 16.3x"를 각주 텍스트가 아니라 **구조화된 필드**로 남긴다. 상위 에이전트가 "발표자 발언과 실제 데이터의 괴리"를 프로그램적으로 찾을 수 있어야 한다. 이게 v0.2가 요약기와 갈라지는 지점이다.

---

## Task 1: evidence.py — 스키마 상수와 골격 생성

**Files:**
- Create: `skills/tuto/scripts/evidence.py`
- Test: `tests/test_evidence.py`

**Interfaces:**
- Consumes: `common.cache_dir`, `common.fmt_ts` (기존)
- Produces:
  - `SCHEMA_VERSION: str = "0.2"`
  - `VIDEO_TYPES: tuple` — `("tutorial","presentation","interview","lecture","demo","screen-recording","mixed","unknown")`
  - `EVIDENCE_TYPES: tuple` — `("slide","ui","chart","code","table","text","other")`
  - `CONFIDENCE: tuple` — `("high","medium","low")`
  - `VERIFY_STATUS: tuple` — `("verified","disputed","unverifiable","unaudited")`
  - `build_skeleton(info: dict, sig: dict, tr: dict, frames_kept: list, url: str) -> dict`
  - `evidence_path(cache_dir: Path) -> Path`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_evidence.py
import json
from pathlib import Path
import pytest
from skills.tuto.scripts import evidence


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


def test_skeleton_has_required_top_level_keys():
    ev = evidence.build_skeleton(_info(), _sig(), _tr(), [], "https://youtu.be/abc12345678")
    for key in ("schema_version", "video", "video_type", "provenance",
                "segments", "visual_evidence", "claims", "gaps", "flags"):
        assert key in ev, f"missing {key}"
    assert ev["schema_version"] == evidence.SCHEMA_VERSION


def test_skeleton_video_block():
    ev = evidence.build_skeleton(_info(), _sig(), _tr(), [], "https://youtu.be/abc12345678")
    assert ev["video"]["id"] == "abc12345678"
    assert ev["video"]["title"] == "Test Video"
    assert ev["video"]["duration"] == 300.0
    assert ev["video"]["url"] == "https://youtu.be/abc12345678"


def test_skeleton_segments_get_end_from_next_start():
    ev = evidence.build_skeleton(_info(), _sig(), _tr(), [], "u")
    segs = ev["segments"]
    assert len(segs) == 2
    assert segs[0]["start"] == 0.0 and segs[0]["end"] == 5.0
    assert segs[0]["transcript"] == "안녕하세요"
    # 마지막 세그먼트의 end는 영상 길이로 채운다
    assert segs[1]["end"] == 300.0


def test_skeleton_llm_slots_start_empty():
    ev = evidence.build_skeleton(_info(), _sig(), _tr(), [], "u")
    assert ev["visual_evidence"] == []
    assert ev["claims"] == []
    assert ev["video_type"]["primary"] == "unknown"


def test_skeleton_provenance_records_transcript_and_signals():
    ev = evidence.build_skeleton(_info(), _sig(), _tr(), [], "u")
    p = ev["provenance"]
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
    ev = evidence.build_skeleton(_info(), _sig(), _tr(), [f], "u")
    frames = ev["provenance"]["frames"]["map"]
    assert len(frames) == 1
    assert frames[0]["t"] == 92.0          # t0132 -> 1분 32초
    assert frames[0]["res"] == 1024
    assert frames[0]["file"] == "t0132_1024.jpg"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_evidence.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skills.tuto.scripts.evidence'`

- [ ] **Step 3: Write minimal implementation**

```python
# skills/tuto/scripts/evidence.py
"""evidence.json — 영상 분석의 구조화 산출물.

설계 원칙:
- **결정론적 골격만 Python이 만든다.** 비디오 메타·자막 세그먼트·프레임 provenance·신호
  요약은 계산 가능하므로 여기서 만들고, 시각 증거(visual_evidence)와 주장(claims)은
  LLM이 판독해 병합한다. 산문 렌더링은 이 모듈의 책임이 아니다.
- **transcript 증거와 visual 증거를 구조로 분리한다.** segments[].transcript는 자막이고,
  visual_evidence[]는 화면이다. 둘을 같은 배열에 담지 않는다.
- **신뢰도를 날조하지 않는다.** confidence/status는 열거형만 쓴다. 정량화 근거가 없는
  0.87 같은 숫자를 만들어내지 않는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common  # noqa: E402

SCHEMA_VERSION = "0.2"

VIDEO_TYPES = ("tutorial", "presentation", "interview", "lecture",
               "demo", "screen-recording", "mixed", "unknown")
EVIDENCE_TYPES = ("slide", "ui", "chart", "code", "table", "text", "other")
CONFIDENCE = ("high", "medium", "low")
VERIFY_STATUS = ("verified", "disputed", "unverifiable", "unaudited")

_FRAME_RE = re.compile(r"^t(\d{2})(\d{2})(?:d\d+)?(?:c[\d_]+)?_(\d+)\.jpg$")


def evidence_path(cache_dir) -> Path:
    return Path(cache_dir) / "evidence.json"


def _frame_meta(path) -> dict:
    """프레임 파일명에서 타임스탬프·해상도를 되읽는다.

    파일명 규약은 frames._frame_tag가 만든다: t<MM><SS>[d<n>][c<crop>]_<res>.jpg
    규약을 벗어나면 None 좌표로 남기되 파일명은 보존한다 — 조용히 버리지 않는다."""
    name = Path(path).name
    m = _FRAME_RE.match(name)
    if not m:
        return {"file": name, "t": None, "res": None}
    mm, ss, res = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return {"file": name, "t": float(mm * 60 + ss), "res": res}


def build_skeleton(info: dict, sig: dict, tr: dict, frames_kept: list, url: str) -> dict:
    """패스1 산출물로 evidence 골격을 만든다. LLM 슬롯은 비운 채 반환한다."""
    duration = float(info.get("duration") or 0)
    segs_in = tr.get("segments") or []
    segments = []
    for i, s in enumerate(segs_in):
        start = float(s.get("start") or 0)
        end = float(segs_in[i + 1]["start"]) if i + 1 < len(segs_in) else duration
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
        "video_type": {"primary": "unknown", "confidence": "low", "basis": ""},
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
        "gaps": [],
        "flags": list(sig.get("flags") or []) + list(tr.get("flags") or []),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_evidence.py -v`
Expected: 6 passed

- [ ] **Step 5: Run full suite to confirm nothing broke**

Run: `python -m pytest -q`
Expected: 107 passed (기존 101 + 신규 6)

- [ ] **Step 6: Commit**

```bash
git add skills/tuto/scripts/evidence.py tests/test_evidence.py
git commit -m "feat(evidence): evidence.json 스키마와 결정론적 골격 생성

Python은 계산 가능한 것만 만든다 - 비디오 메타·자막 세그먼트·프레임
provenance·신호 요약. visual_evidence와 claims는 LLM 슬롯으로 비워 둔다.

confidence/status는 열거형만 허용해 신뢰도 날조를 스키마 차원에서 차단한다."
```

---

## Task 2: evidence.py — 병합과 검증

**Files:**
- Modify: `skills/tuto/scripts/evidence.py`
- Test: `tests/test_evidence.py`

**Interfaces:**
- Consumes: Task 1의 `build_skeleton`, `VIDEO_TYPES`, `EVIDENCE_TYPES`, `CONFIDENCE`, `VERIFY_STATUS`
- Produces:
  - `merge(ev: dict, patch: dict) -> dict` — LLM 산출물을 골격에 병합 (visual_evidence·claims·gaps·video_type·zoom 프레임)
  - `validate(ev: dict) -> list` — 위반 메시지 리스트 (빈 리스트면 통과)
  - `load(cache_dir) -> dict` / `save(cache_dir, ev) -> Path`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_evidence.py 에 추가

def _skel():
    return evidence.build_skeleton(_info(), _sig(), _tr(), [], "u")


def test_merge_adds_visual_evidence_and_assigns_ids():
    ev = _skel()
    ev = evidence.merge(ev, {"visual_evidence": [
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
    ev = _skel()
    ev = evidence.merge(ev, {
        "video_type": {"primary": "presentation", "confidence": "high", "basis": "slides"},
        "claims": [{"claim": "성능이 16.3배 향상", "timestamp": 132.0,
                    "evidence": [{"source": "frame", "ref": "v1"}],
                    "verification": {"status": "unaudited"}}]})
    assert ev["video_type"]["primary"] == "presentation"
    assert ev["claims"][0]["id"] == "c1"


def test_validate_passes_on_clean_skeleton():
    assert evidence.validate(_skel()) == []


def test_validate_rejects_unknown_evidence_type():
    ev = evidence.merge(_skel(), {"visual_evidence": [
        {"type": "hologram", "value": "x", "timestamp": 1.0, "frame": "f",
         "confidence": "high"}]})
    errs = evidence.validate(ev)
    assert any("type" in e and "hologram" in e for e in errs)


def test_validate_rejects_numeric_confidence():
    ev = evidence.merge(_skel(), {"visual_evidence": [
        {"type": "slide", "value": "x", "timestamp": 1.0, "frame": "f",
         "confidence": 0.87}]})
    errs = evidence.validate(ev)
    assert any("confidence" in e for e in errs)


def test_validate_rejects_claim_referencing_missing_visual_evidence():
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0,
         "evidence": [{"source": "frame", "ref": "v99"}],
         "verification": {"status": "unaudited"}}]})
    errs = evidence.validate(ev)
    assert any("v99" in e for e in errs)


def test_validate_rejects_frame_sourced_evidence_without_ref():
    """화면 증거라고 주장하면서 근거 id가 없으면 자막으로 몰래 보충한 것이다."""
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0,
         "evidence": [{"source": "frame", "ref": ""}],
         "verification": {"status": "unaudited"}}]})
    errs = evidence.validate(ev)
    assert any("ref" in e for e in errs)


def test_validate_rejects_unknown_verification_status():
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0,
         "evidence": [{"source": "transcript", "ref": "0"}],
         "verification": {"status": "probably-true"}}]})
    errs = evidence.validate(ev)
    assert any("probably-true" in e for e in errs)


def test_save_and_load_roundtrip(tmp_path):
    ev = _skel()
    p = evidence.save(tmp_path, ev)
    assert p.exists()
    back = evidence.load(tmp_path)
    assert back["video"]["id"] == ev["video"]["id"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_evidence.py -v`
Expected: FAIL — `AttributeError: module 'evidence' has no attribute 'merge'`

- [ ] **Step 3: Write minimal implementation**

```python
# evidence.py 에 추가

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
    """LLM 산출물을 골격에 병합한다. **덮어쓰지 않고 append**가 기본이다 —
    빌더와 감사가 여러 번 나눠 기여하므로 마지막 호출이 앞의 것을 지우면 안 된다.
    video_type만 교체 의미론을 갖는다(분류는 단일 값)."""
    for item in patch.get("visual_evidence") or []:
        item = dict(item)
        item.setdefault("id", _next_id(ev["visual_evidence"], "v"))
        ev["visual_evidence"].append(item)
    for item in patch.get("claims") or []:
        item = dict(item)
        item.setdefault("id", _next_id(ev["claims"], "c"))
        item.setdefault("verification", {"status": "unaudited"})
        ev["claims"].append(item)
    for g in patch.get("gaps") or []:
        ev["gaps"].append(dict(g))
    for f in patch.get("zoom_frames") or []:
        ev["provenance"]["frames"]["zoom"].append(_frame_meta(f) if isinstance(f, str) else dict(f))
    if patch.get("video_type"):
        ev["video_type"] = dict(patch["video_type"])
    for f in patch.get("flags") or []:
        if f not in ev["flags"]:
            ev["flags"].append(f)
    return ev


def _apply_verdicts(ev: dict, verdicts: list) -> dict:
    """감사 결과를 claim id 기준으로 반영한다."""
    by_id = {c["id"]: c for c in ev["claims"]}
    for v in verdicts:
        c = by_id.get(v.get("claim_id"))
        if c is None:
            ev["flags"].append(f"verdict_orphan: {v.get('claim_id')}")
            continue
        c["verification"] = {k: v[k] for k in ("status", "auditor", "note") if k in v}
    return ev


def validate(ev: dict) -> list:
    """스키마 위반 목록을 반환한다. 빈 리스트면 통과.

    예외를 던지지 않고 목록으로 반환하는 이유: 한 번에 전부 보여줘야 고치는 쪽이
    왕복을 덜 한다. 호출부가 비어 있지 않으면 fail-loud 하면 된다."""
    errs = []
    if ev.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version: {ev.get('schema_version')} != {SCHEMA_VERSION}")
    vt = (ev.get("video_type") or {}).get("primary")
    if vt not in VIDEO_TYPES:
        errs.append(f"video_type.primary: unknown value {vt!r}")
    ve_ids = set()
    for v in ev.get("visual_evidence") or []:
        vid = v.get("id", "?")
        ve_ids.add(vid)
        if v.get("type") not in EVIDENCE_TYPES:
            errs.append(f"visual_evidence[{vid}].type: unknown value {v.get('type')!r}")
        if v.get("confidence") not in CONFIDENCE:
            errs.append(f"visual_evidence[{vid}].confidence: must be one of "
                        f"{CONFIDENCE}, got {v.get('confidence')!r}")
        if not v.get("frame"):
            errs.append(f"visual_evidence[{vid}].frame: missing frame provenance")
    for c in ev.get("claims") or []:
        cid = c.get("id", "?")
        ev_list = c.get("evidence") or []
        if not ev_list:
            errs.append(f"claims[{cid}].evidence: empty — 근거 없는 주장은 담지 않는다")
        for e in ev_list:
            src = e.get("source")
            if src not in ("transcript", "frame"):
                errs.append(f"claims[{cid}].evidence.source: {src!r} "
                            f"(both 금지 — 출처를 분리해 각각 적는다)")
            if not e.get("ref"):
                errs.append(f"claims[{cid}].evidence.ref: empty for source={src!r}")
            elif src == "frame" and e["ref"] not in ve_ids:
                errs.append(f"claims[{cid}].evidence.ref: {e['ref']!r} "
                            f"not found in visual_evidence")
        st = (c.get("verification") or {}).get("status")
        if st not in VERIFY_STATUS:
            errs.append(f"claims[{cid}].verification.status: unknown value {st!r}")
    return errs
```

> **`source: "both"`를 금지한 이유** — 사용자 예시에는 `both`가 있었지만, 이를 허용하면
> "화면에도 있고 자막에도 있다"는 주장이 검증 없이 통과한다. 대신 `evidence` 배열에
> `{"source":"transcript",...}`와 `{"source":"frame",...}` **두 항목**을 넣게 강제한다.
> 그러면 각각의 ref를 따로 검증할 수 있고, 하나만 있는 경우와 구조적으로 구분된다.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_evidence.py -v`
Expected: 16 passed

- [ ] **Step 5: Run full suite**

Run: `python -m pytest -q`
Expected: 117 passed

- [ ] **Step 6: Commit**

```bash
git add skills/tuto/scripts/evidence.py tests/test_evidence.py
git commit -m "feat(evidence): merge/validate — 스키마 차원의 환각 차단

validate가 잡는 것:
- 열거형 밖 값 (type/confidence/status) — 숫자 신뢰도 날조 차단
- frame 출처인데 visual_evidence에 없는 id 참조 — 화면 증거 위조 차단
- 근거 없는 claim
- source=both 금지 — transcript와 frame을 각각의 항목으로 분리 강제

merge는 append 의미론이다. 빌더와 감사가 나눠 기여하므로 덮어쓰면 안 된다."
```

---

## Task 3: evidence.py CLI + analyze.py 연동

**Files:**
- Modify: `skills/tuto/scripts/evidence.py` (main 추가)
- Modify: `skills/tuto/scripts/analyze.py:224-278` (`run_pass1` 끝부분)
- Test: `tests/test_evidence.py`, `tests/test_analyze.py`

**Interfaces:**
- Consumes: Task 2의 `merge`·`validate`·`load`·`save`·`_apply_verdicts`
- Produces: CLI `python evidence.py <cache_dir> --merge <patch.json>` / `--validate` / `--verdicts <file.json>` / `--summary`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_evidence.py 에 추가
import subprocess

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "tuto" / "scripts" / "evidence.py"


def _run(args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT)] + args,
                          capture_output=True, text=True, encoding="utf-8")


def test_cli_validate_exit_zero_on_clean(tmp_path):
    evidence.save(tmp_path, _skel())
    p = _run([str(tmp_path), "--validate"])
    assert p.returncode == 0


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
    patch.write_text(json.dumps({"visual_evidence": [
        {"type": "chart", "value": "16.3x", "timestamp": 132.0,
         "frame": "t0212_1024.jpg", "confidence": "high"}]}), encoding="utf-8")
    p = _run([str(tmp_path), "--merge", str(patch)])
    assert p.returncode == 0
    assert evidence.load(tmp_path)["visual_evidence"][0]["value"] == "16.3x"


def test_cli_summary_prints_counts(tmp_path):
    evidence.save(tmp_path, _skel())
    p = _run([str(tmp_path), "--summary"])
    assert p.returncode == 0
    assert "segments=2" in p.stdout
```

```python
# tests/test_analyze.py 에 추가
def test_run_pass1_writes_evidence_json(monkeypatch, tmp_path):
    """패스1이 끝나면 evidence.json 골격이 캐시에 남아야 한다."""
    # 기존 test_analyze.py의 모킹 패턴을 그대로 따른다 (download/transcribe/frames 스텁).
    # 검증 포인트: (cd / "evidence.json").exists() and schema_version == "0.2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_evidence.py -k cli -v`
Expected: FAIL — `--validate` 인자 미인식 (exit 2 with argparse error, 메시지 불일치)

- [ ] **Step 3: Write minimal implementation**

```python
# evidence.py 에 추가

def summary_line(ev: dict) -> str:
    p = ev["provenance"]
    return (f"EVIDENCE schema={ev['schema_version']} type={ev['video_type']['primary']} "
            f"segments={len(ev['segments'])} visual={len(ev['visual_evidence'])} "
            f"claims={len(ev['claims'])} gaps={len(ev['gaps'])} "
            f"map_frames={len(p['frames']['map'])} zoom_frames={len(p['frames']['zoom'])}")


def main() -> int:
    common.utf8_stdout()
    ap = argparse.ArgumentParser(description="evidence.json 병합·검증")
    ap.add_argument("cache_dir")
    ap.add_argument("--merge", help="병합할 patch json 경로")
    ap.add_argument("--verdicts", help="감사 결과 json 경로 (claim_id/status/auditor/note 배열)")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    cd = Path(args.cache_dir)
    if not evidence_path(cd).exists():
        print(f"ERROR: {evidence_path(cd)} 없음 — analyze.py를 먼저 실행한다", file=sys.stderr)
        return 2
    ev = load(cd)
    if args.merge:
        ev = merge(ev, json.loads(Path(args.merge).read_text(encoding="utf-8")))
        save(cd, ev)
    if args.verdicts:
        ev = _apply_verdicts(ev, json.loads(Path(args.verdicts).read_text(encoding="utf-8")))
        save(cd, ev)
    if args.summary:
        print(summary_line(ev))
    if args.validate or args.merge or args.verdicts:
        errs = validate(ev)
        if errs:
            for e in errs:
                print(f"INVALID: {e}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

```python
# analyze.py — import 추가
import evidence  # noqa: E402   (기존 import 블록 옆)

# analyze.py run_pass1 — `print(f"== CACHE == {cd}")` 바로 앞에 삽입
    ev = evidence.build_skeleton(info, sig, tr, kept, url)
    evidence.save(cd, ev)
    print("== EVIDENCE ==")
    print(evidence.summary_line(ev))
    print(f"EVIDENCE_FILE {evidence.evidence_path(cd)}")
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_evidence.py tests/test_analyze.py -v`
Expected: 모두 PASS

- [ ] **Step 5: Run full suite**

Run: `python -m pytest -q`
Expected: 122 passed

- [ ] **Step 6: Commit**

```bash
git add skills/tuto/scripts/evidence.py skills/tuto/scripts/analyze.py tests/
git commit -m "feat(evidence): CLI + 패스1 연동

analyze.py가 패스1 끝에 evidence.json 골격을 자동 저장하고 == EVIDENCE == 줄로
경로를 알린다. LLM 층은 evidence.py --merge / --verdicts / --validate 로만
evidence.json을 건드린다 - 직접 JSON을 쓰지 않게 해 스키마 위반을 exit 2로 잡는다."
```

---

## Task 4: 영상 유형 분류 힌트 (결정론적)

**Files:**
- Modify: `skills/tuto/scripts/evidence.py`
- Test: `tests/test_evidence.py`

**Interfaces:**
- Produces: `classify_hint(sig: dict, tr: dict, duration: float) -> dict` — `{"candidates": [...], "basis": "..."}`

**설계 판단:** 분류의 **최종 판정은 LLM(판독 에이전트)** 이 한다 — 화면을 봐야 알 수 있기 때문이다. Python은 신호만으로 **후보를 좁히는 힌트**를 준다. 힌트가 틀려도 LLM이 덮어쓸 수 있으므로 과신하지 않는다.

- [ ] **Step 1: Write the failing test**

```python
def test_classify_hint_dense_chapters_suggests_lecture_or_presentation():
    sig = _sig(); sig["chapters"] = [{"start": float(i * 60), "title": f"c{i}"} for i in range(11)]
    tr = _tr(); tr["segments"] = [{"start": float(i), "text": "말" * 20} for i in range(600)]
    h = evidence.classify_hint(sig, tr, 1200.0)
    assert "presentation" in h["candidates"] or "lecture" in h["candidates"]
    assert h["basis"]


def test_classify_hint_no_transcript_suggests_screen_recording():
    tr = {"source": "none", "lang": "", "segments": [], "dupes_removed": 0, "flags": []}
    h = evidence.classify_hint(_sig(), tr, 300.0)
    assert "screen-recording" in h["candidates"]


def test_classify_hint_never_returns_value_outside_enum():
    h = evidence.classify_hint(_sig(), _tr(), 300.0)
    assert all(c in evidence.VIDEO_TYPES for c in h["candidates"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_evidence.py -k classify -v`
Expected: FAIL — `AttributeError: ... 'classify_hint'`

- [ ] **Step 3: Write minimal implementation**

```python
def classify_hint(sig: dict, tr: dict, duration: float) -> dict:
    """신호만으로 영상 유형 후보를 좁힌다 — **판정이 아니라 힌트다.**

    화면을 봐야 알 수 있는 것(슬라이드인가 IDE인가)은 판독 에이전트가 정한다.
    여기서는 자막 밀도·챕터 수·활동 피크 밀도라는 세 축만 쓴다."""
    segs = tr.get("segments") or []
    peaks = (sig.get("activity") or {}).get("peaks") or []
    chapters = sig.get("chapters") or []
    minutes = max(duration / 60.0, 1e-9)
    words_per_min = sum(len(s.get("text", "")) for s in segs) / minutes
    peaks_per_min = len(peaks) / minutes

    cands, basis = [], []
    if not segs:
        cands.append("screen-recording")
        basis.append("자막 없음")
    if len(chapters) >= 6:
        cands += ["presentation", "lecture"]
        basis.append(f"챕터 {len(chapters)}개")
    if words_per_min >= 300:
        cands += ["interview", "lecture"]
        basis.append(f"자막 밀도 {words_per_min:.0f}자/분")
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
```

`build_skeleton`의 `video_type` 초기값에 힌트를 실어 보낸다:

```python
        "video_type": {"primary": "unknown", "confidence": "low", "basis": "",
                       "hint": classify_hint(sig, tr, duration)},
```

- [ ] **Step 4: Run tests** → `python -m pytest tests/test_evidence.py -v` → PASS
- [ ] **Step 5: Run full suite** → `python -m pytest -q` → 125 passed
- [ ] **Step 6: Commit**

```bash
git add skills/tuto/scripts/evidence.py tests/test_evidence.py
git commit -m "feat(evidence): 영상 유형 분류 힌트 (신호 기반 후보 좁히기)

판정이 아니라 힌트다. 자막 밀도·챕터 수·활동 피크 밀도 세 축으로 후보를 좁히고,
최종 판정은 화면을 보는 판독 에이전트가 한다. 열거형 밖 값은 반환하지 않는다."
```

---

## Task 5: SKILL.md — 모드 분기와 범용화

**Files:**
- Modify: `skills/tuto/SKILL.md`

**Interfaces:**
- Consumes: `evidence.py` CLI (Task 3), `classify_hint`(Task 4)
- Produces: GUIDE/INSIGHT/ASK 모드 계약, evidence 산출 계약

**보존해야 하는 것 (변경 금지):** §0 프리플라이트, §1 패스1(오케스트레이터 프레임 미판독 규칙), §2 판정 루브릭 6개(해상도 티어링·미관측 1024·프레임 공백), §3 확대(--timestamps 지침), §5 표본 감사 6건 + 커버리지 + MISMATCH 에스컬레이션, 검증 규칙 4개.

- [ ] **Step 1: frontmatter 교체**

```yaml
---
name: tuto
description: 유튜브 영상을 화면 근거와 함께 분석한다 — 자막뿐 아니라 슬라이드·UI·표·차트·설정값·코드를 프레임에서 직접 판독하고, 독립 감사로 검증한 뒤 evidence.json으로 구조화한다. 따라하기 가이드(GUIDE), 핵심 주장·수치 분석(INSIGHT), 영상 대상 질의응답(ASK) 세 모드. "영상 분석해줘", "핵심 인사이트", "화면에 나온 설정값", "영상에서 나온 숫자 정리", "이 발표의 주장과 근거", "영상 보고 따라할 것 정리", "영상에 대해 질문" 요청 시 사용. 단순 링크 공유나 영상 추천 요청에는 쓰지 않는다.
argument-hint: "<video-url> [--guide|--insight] [질문]"
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Agent
user-invocable: true
---
```

- [ ] **Step 2: §0 앞에 모드 분기 절 삽입**

````markdown
## 모드 판정 (가장 먼저)

인자를 보고 셋 중 하나로 판정한다.

| 조건 | 모드 | 산출물 |
|---|---|---|
| `--insight` 플래그 | **INSIGHT** | `insight.md` |
| URL 없이 질문만 (직전 분석 영상 대상) | **ASK** | 채팅 응답 |
| URL + 질문 | **GUIDE 후 ASK** | `guide.md` + 질문 답변 |
| 그 외 (URL만, `--guide`) | **GUIDE** (기본값) | `guide.md` |

**backward compatibility: `/tuto <url>`은 무조건 GUIDE다.** 기존 사용자의 호출이 깨지면 안 된다.

**ASK 모드는 §1~§3을 건너뛴다.** `<cache_dir>/evidence.json`이 있으면 그것으로 답하고,
새 시각 근거가 필요할 때만 `zoom.py --timestamps`로 추가 프레임을 확보한다.
`evidence.json`이 없으면 사용자에게 "이 영상은 아직 분석되지 않았다"고 알리고 GUIDE부터 제안한다.
````

- [ ] **Step 3: §2 판독 에이전트 산출 계약에 영상 유형·evidence 추가**

기존 4줄 반환 계약을 5줄로 확장한다 (`장르:` 줄을 열거형으로 고정):

```markdown
  1. `영상유형:` `tutorial|presentation|interview|lecture|demo|screen-recording|mixed` 중 하나
     + `신뢰도(high|medium|low)` + 근거 한 줄. 패스1 보고서의 `EVIDENCE ... hint` 후보를
     참고하되 화면을 보고 최종 판정한다 — 힌트와 달라도 된다.
  2. `프레임 공백:` (기존과 동일)
  3. `확대 배정:` (기존과 동일)
  4. `특이:` (기존과 동일)
```

- [ ] **Step 4: §4 빌더 계약을 "evidence 우선"으로 변경**

````markdown
## 4. 근거 추출 → evidence.json → 모드별 산출물

빌더(`model: "sonnet"`)에게 **먼저 evidence patch를 만들게 하고**, 그다음 모드별 문서를 쓰게 한다.
산출 순서가 중요하다 — 문서를 먼저 쓰면 문서에 맞춰 근거를 지어내게 된다.

**산출 계약 (순서 고정):**
1. `<cache_dir>/evidence-patch.json` 작성:
```json
{
  "video_type": {"primary": "...", "confidence": "high|medium|low", "basis": "..."},
  "visual_evidence": [
    {"type": "slide|ui|chart|code|table|text|other", "value": "화면에서 읽은 문자열 그대로",
     "timestamp": 132.0, "frame": "t0212_1024.jpg", "confidence": "high|medium|low"}
  ],
  "claims": [
    {"claim": "한 문장", "timestamp": 132.0,
     "evidence": [{"source": "frame", "ref": "v1"}, {"source": "transcript", "ref": "12"}],
     "conflict": {"transcript": "16배", "screen": "16.3x"},
     "verification": {"status": "unaudited"}}
  ],
  "gaps": [{"start": 350.0, "end": 469.0, "reason": "지도 프레임 공백"}]
}
```
2. 오케스트레이터가 병합·검증한다:
   `python "<SKILL_DIR>/scripts/evidence.py" "<cache_dir>" --merge "<cache_dir>/evidence-patch.json"`
   **exit 2면 stderr의 `INVALID:` 줄을 그대로 빌더에게 돌려주고 1회 재지시한다.**
3. 빌더가 `evidence.json`을 근거로 모드별 문서를 쓴다 (GUIDE→`guide.md`, INSIGHT→`insight.md`).

**`evidence` 배열 작성 규칙:**
- `source: "frame"`의 `ref`는 **같은 patch의 `visual_evidence` id**여야 한다 (`v1`, `v2`…).
  아직 id가 없으면 배열 순서대로 `v1`부터 센다.
- `source: "transcript"`의 `ref`는 패스1 보고서의 **세그먼트 인덱스**(0부터)다.
- `source: "both"`는 없다. 화면과 자막 양쪽 근거가 있으면 **두 항목을 각각** 넣는다.
- 자막과 화면 값이 다르면 `conflict`에 둘 다 적는다. 본문에서는 화면 값을 채택한다.
````

- [ ] **Step 5: §5 감사 결과를 evidence에 반영하는 절 추가**

````markdown
감사가 끝나면 판정을 `<cache_dir>/verdicts.json`으로 모아 반영한다:

```json
[{"claim_id": "c1", "status": "verified", "auditor": "sonnet", "note": "..."},
 {"claim_id": "c4", "status": "disputed", "auditor": "escalated", "note": "..."}]
```
```
python "<SKILL_DIR>/scripts/evidence.py" "<cache_dir>" --verdicts "<cache_dir>/verdicts.json"
```
감사하지 않은 주장은 `unaudited`로 남는다 — **`verified`와 구분된다.** 감사 못 한 것을
통과한 것처럼 보이게 하지 않는다.
````

- [ ] **Step 6: INSIGHT 모드 산출 형식 절 추가 (§7 앞)**

````markdown
## 6-B. INSIGHT 모드 산출 형식

`<cache_dir>/insight.md`:

```markdown
## Executive summary            (5줄 이내)
## Key claims                   (주장별로 아래 6항목)
### Claim N: <주장>
- 왜 중요한가
- transcript 근거 (t=MM:SS, 인용)
- visual 근거 (frame, 화면에서 읽은 값)
- 불일치 (있으면 자막값 vs 화면값 병기)
- 검증 상태 (verified|disputed|unverifiable|unaudited)
## Important numbers / benchmarks   (표. 화면 근거가 있는 것과 자막 전용을 열로 구분)
## Novel insights
## Practical implications
## Assumptions / caveats
## Evidence map                 (claim id → visual_evidence id → frame 파일명)
```

**INSIGHT는 요약이 아니다.** 근거 없는 문장을 쓰지 않는다 — 모든 Key claim은
evidence.json의 claim id를 갖는다. 화면 근거가 없는 주장은 그렇게 명시하고
`Assumptions / caveats`로 내린다.
````

- [ ] **Step 7: §7 사용자 응답을 모드별로 분기**

```markdown
## 7. 사용자 응답

- **GUIDE**: 스텝 제목 + 핵심 값 위주로 요약하고 `guide.md` 경로를 안내한다.
- **INSIGHT**: Executive summary와 Key claims 제목만 채팅에 싣고 `insight.md` 경로를 안내한다.
- **ASK**: 아래 4항목을 반드시 포함한다 — `답변` / `근거 타임스탬프` /
  `transcript 근거`와 `visual 근거`(구분해서) / `불확실한 부분`.

모든 모드에서 `evidence.json` 경로도 함께 안내한다 — 상위 에이전트가 재사용할 산출물이다.
```

- [ ] **Step 8: 튜토리얼 고정 표현 일괄 점검**

Run: `grep -n "따라하기\|스텝 후보\|준비물" skills/tuto/SKILL.md`
남은 표현을 모드 조건부로 바꾼다 — GUIDE 모드에서만 "스텝/준비물"을 쓰고, INSIGHT/ASK는 해당 없음.

- [ ] **Step 9: Commit**

```bash
git add skills/tuto/SKILL.md
git commit -m "feat(skill): GUIDE/INSIGHT/ASK 3모드 + evidence 우선 산출 계약

핵심 변경: 빌더가 문서를 먼저 쓰지 않고 evidence-patch.json을 먼저 만든다.
문서를 먼저 쓰면 문서에 맞춰 근거를 지어내기 때문이다.

보존: 프리플라이트, 오케스트레이터 프레임 미판독, 판정 루브릭 6개, 해상도
티어링, 미관측 1024 기본값, 프레임 공백 탐지, 표본 감사 6건 + 커버리지 +
MISMATCH 에스컬레이션, 검증 규칙 4개.

/tuto <url> 무인자는 GUIDE 기본값 - backward compatibility 유지."
```

---

## Task 6: 스키마 문서 + 플러그인 메타데이터

**Files:**
- Create: `docs/eval/evidence-schema.md`
- Modify: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

- [ ] **Step 1: `docs/eval/evidence-schema.md` 작성** — 필드별 의미·열거형·불변식(claim.evidence.ref 참조 무결성, source=both 금지 이유, unaudited vs verified 구분)을 정본으로 기록한다. `evidence.py`의 docstring이 아니라 이 문서가 스키마 정본이다.

- [ ] **Step 2: plugin.json / marketplace.json description 교체**

```json
"description": "유튜브 영상을 AI 에이전트가 추론에 쓸 수 있는 검증된 근거로 바꾼다. 자막뿐 아니라 화면의 슬라이드·UI·표·차트·설정값·코드를 프레임에서 직접 판독하고, 독립 감사로 검증해 evidence.json으로 구조화한다. 따라하기 가이드·인사이트 분석·질의응답 세 모드."
```

- [ ] **Step 3: 버전 0.2.0으로 범프** (`plugin.json`)

- [ ] **Step 4: 검증**

Run: `claude plugin validate .`
Expected: `✔ Validation passed`

- [ ] **Step 5: Commit**

```bash
git add docs/eval/evidence-schema.md .claude-plugin/
git commit -m "docs(evidence): 스키마 정본 문서 + 플러그인 메타데이터 v0.2.0"
```

---

## Task 7: README 포지셔닝 전환

**Files:**
- Modify: `README.md`

**보존 필수:** 측정 수치 표(Hallucinated values 0 / R1 0.913 / Value-F1 0.909 / cache_write −95% / −27% / 8.1× / 5.4× / 101 tests), "What the audits have caught" 표, How it works 5절, Limitations. **삭제 금지 — 아래쪽 technical/evaluation 섹션으로 이동만 한다.**

- [ ] **Step 1: 상단 히어로 교체**

```markdown
### Give AI agents eyes for YouTube.

Turn YouTube videos into **verified evidence** that AI agents can reason over —
transcripts, screen text, slides, UI, charts, numbers, actions, and timestamps.

**Claude와 AI 에이전트가 YouTube 영상을 제대로 읽게 만듭니다.**
자막뿐 아니라 화면·슬라이드·UI·숫자까지 분석하고, 검증된 근거를 제공합니다.

**Understand it. Learn from it. Follow it. Ask questions about it. — With evidence.**
```

- [ ] **Step 2: 3모드 표를 상단에 배치**

```markdown
| Mode | Command | Output |
|---|---|---|
| **GUIDE** | `/tuto <url>` | 재현 가능한 따라하기 단계 |
| **INSIGHT** | `/tuto <url> --insight` | 핵심 주장·수치·근거 지도 |
| **ASK** | `/tuto <url> "질문"` | 타임스탬프·근거 기반 답변 |

모든 모드가 같은 `evidence.json`을 공유합니다 — 한 번 분석하면 재분석 없이 재사용됩니다.
```

- [ ] **Step 3: evidence.json 예시 블록 추가** (실제 스키마 발췌, `conflict` 필드가 보이도록)

- [ ] **Step 4: 기존 수치·감사 섹션을 `## Technical details` 아래로 이동** (내용 무변경)

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs(readme): evidence engine으로 포지셔닝 전환

메인 메시지를 'YouTube tutorial -> reproducible instructions'에서
'Give AI agents eyes for YouTube'로 바꾼다. 3모드를 상단에 노출하고
evidence.json을 중심 산출물로 제시한다.

기존 측정 수치·감사 사례·How it works는 삭제하지 않고 Technical details
섹션으로 이동만 했다."
```

---

## Task 8: 통합 검증 · PR

- [ ] **Step 1: 전체 테스트**

Run: `python -m pytest -q`
Expected: 125+ passed (기존 101 전부 포함)

- [ ] **Step 2: evidence CLI 실제 동작 확인** — 이미 캐시된 영상으로 골격 생성·검증까지 돌려 exit 0 확인

- [ ] **Step 3: 플러그인 매니페스트 검증** → `claude plugin validate .`

- [ ] **Step 4: 저장소 잔류 편집 확인** → `git status --short`

- [ ] **Step 5: 푸시 + PR 생성**

PR 본문에 반드시 포함:
1. **기존 구조** — Python 7모듈(범용) + SKILL.md(튜토리얼 종속) 2층
2. **무엇을 바꿨는지** — evidence.py 신규, analyze.py 연동(추가만), SKILL.md 3모드, 메타데이터·README
3. **왜** — guide.md는 최종 산출물이지 재사용 가능한 데이터가 아니다. 상위 에이전트가 추론에 쓰려면 구조화된 근거가 필요하다
4. **backward compatibility** — `/tuto <url>` = GUIDE, 기존 함수 시그니처 무변경, 기존 테스트 101개 유지
5. **테스트 결과** — 실제 실행 출력
6. **known limitations** — 렌더링은 여전히 LLM 의존(Python이 산문을 만들지 않음), INSIGHT/ASK는 골든셋 미보유, MCP 미구현
7. **확장 포인트** — `evidence.py` CLI가 곧 MCP tool surface. `--merge`/`--validate`/`--summary`가 그대로 MCP 툴이 된다

---

## Self-Review

**1. Spec coverage**

| 스펙 요구 | 태스크 |
|---|---|
| evidence.json 설계 | T1·T2 |
| confidence 날조 금지 | T2 (validate 열거형 강제) |
| transcript/visual 분리 | T1(segments vs visual_evidence) · T2(source=both 금지) |
| timestamp·frame provenance | T1 (`_frame_meta`) |
| GUIDE 모드 유지 | T5 (기본값) |
| INSIGHT 모드 | T5 Step 6 |
| ASK 모드 | T5 Step 2·7 |
| 영상 유형 범용화 | T4(힌트) · T5(판정) |
| Skill description/trigger | T5 Step 1 |
| README 포지셔닝 | T7 |
| 이름·호환성 유지 | Global Constraints |
| Claude 종속 완화 | T3 (CLI 경계) · T8 (PR 확장 포인트) |
| 기존 기능 보존 | Global Constraints + T5 보존 목록 |

**2. Placeholder scan** — TBD·"적절히 처리" 없음. `tests/test_analyze.py` 추가 테스트만 기존 모킹 패턴을 따르라고 지시했는데, 이는 해당 파일을 읽어야 정확한 코드를 쓸 수 있어서다. 실행자는 기존 파일의 패턴을 그대로 복제한다.

**3. Type consistency** — `build_skeleton(info, sig, tr, frames_kept, url)`, `merge(ev, patch)`, `validate(ev) -> list`, `load/save(cache_dir)`, `classify_hint(sig, tr, duration)`, `summary_line(ev)`. T3·T4가 T1·T2의 이름을 그대로 참조한다. `_apply_verdicts`는 T2에서 정의하고 T3 CLI가 쓴다.
