# YoutubeAnalyzer v0.3 — Working Knowledge 리팩터링 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans 또는 subagent-driven-development.

**Goal:** 사용자-facing 모드(GUIDE/INSIGHT/ASK)를 없애고 `/tuto <url> <자연어 요청>` 하나로 통일한다. 산출물을 `evidence.json` + `video.md`로 정리하고, `video.md`는 고정 템플릿이 아니라 **영상 구조에 맞춰 자율 구성**한다.

**Architecture:** Python 층은 모드를 모른다(확인 완료 — 유일한 언급은 주석 1줄). 모드 의존은 `SKILL.md` 14곳에 몰려 있다. 따라서 v0.2와 같은 패턴: **`evidence.py` 스키마 확장 + `SKILL.md` 오케스트레이션 재작성**. 파이프라인(MAP→ZOOM→감사)은 손대지 않는다.

**Tech Stack:** 변경 없음 (표준 라이브러리, pytest).

## Global Constraints

- 신규 런타임 의존성 **0**
- 기존 테스트 **140개 전부 통과** 유지
- 기존 함수 시그니처 변경 금지 (추가만)
- **MAP→ZOOM·신호 가중 선정·감사·캐시·불확실성 표기 전부 보존** — 사용자가 명시 요구
- 신뢰도 숫자 날조 금지, `source: "both"` 금지, transcript/visual 분리 유지
- 골든셋 결과·비용 실측·OCR 롤백 교훈 등 **기존 실험 자산 삭제 금지**
- MCP/Web UI/DB/임베딩 **구현하지 않음**

---

## 핵심 설계 판단 3가지

### 1. `knowledge_items` type 목록을 14개 → 11개로 줄인다

사용자 예시의 `claim`은 이미 `claims[]`가 담당하므로 중복이다. `configuration`/`parameter`는 실무에서 구분이 모호해 `setting`으로 합친다. `artifact`는 `result`와 겹친다. `success_criterion`은 `criterion`으로 줄인다.

```
concept · procedure · action · command · setting · prerequisite
result · criterion · warning · example · comparison
```

**빈 카테고리를 만들지 않는다** — 영상에 없으면 그 type은 배열에 등장하지 않는다.

### 2. `video.md`는 outline을 빌더가 정한다

고정 섹션을 강제하지 않는다. 대신 **누락 방지 질문 9개**를 계약으로 박고, "있으면 수집, 없으면 생략"을 규칙으로 둔다. 구조는 영상이 정하고, 커버리지는 질문이 보장한다.

> What must not be missed is structured. How it is explained is adaptive.

### 3. provenance 검증을 참조 무결성까지 올린다

v0.2는 `frame`이 비어 있는지만 봤다. v0.3은 **실재하는 프레임인지**(`provenance.frames.map|zoom`에 있는 파일명인지)와 **transcript ref가 `segments` 범위 안인지**를 검사한다. LLM이 없는 프레임명을 지어내면 거부된다.

---

## Task 1: evidence.py — knowledge_items + 참조 무결성

**Files:** `skills/tuto/scripts/evidence.py`, `tests/test_evidence.py`

**Produces:**
- `SCHEMA_VERSION = "0.3"`
- `KNOWLEDGE_TYPES: tuple` (11종)
- `build_skeleton`에 `knowledge_items: []` 추가
- `merge`가 `knowledge_items`를 `k1`부터 부여하며 append
- `validate` 추가 검사 3종: 프레임 실재성, transcript ref 범위, knowledge_items 근거 규칙
- `_known_frames(ev) -> set` 헬퍼

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_knowledge_items_start_empty_and_get_k_ids():
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "command", "content": "pip install -U yt-dlp", "timestamp": 10.0,
         "evidence": [{"source": "transcript", "ref": "0"}]}]})
    assert ev["knowledge_items"][0]["id"] == "k1"


def test_validate_rejects_unknown_knowledge_type():
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "vibe", "content": "x", "timestamp": 1.0,
         "evidence": [{"source": "transcript", "ref": "0"}]}]})
    assert any("vibe" in e for e in evidence.validate(ev))


def test_validate_rejects_knowledge_item_without_evidence():
    ev = evidence.merge(_skel(), {"knowledge_items": [
        {"type": "concept", "content": "x", "timestamp": 1.0, "evidence": []}]})
    assert any("evidence" in e for e in evidence.validate(ev))


def test_validate_rejects_frame_not_in_provenance(tmp_path):
    """LLM이 없는 프레임 파일명을 지어내면 거부한다."""
    f = tmp_path / "t0132_1024.jpg"; f.write_bytes(b"x")
    ev = evidence.build_skeleton(_info(), _sig(), _tr(), [f], "u")
    ev = evidence.merge(ev, {"visual_evidence": [
        {"type": "slide", "value": "x", "timestamp": 1.0,
         "frame": "t9999_1024.jpg", "confidence": "high"}]})
    assert any("t9999_1024.jpg" in e for e in evidence.validate(ev))


def test_validate_accepts_frame_present_in_provenance(tmp_path):
    f = tmp_path / "t0132_1024.jpg"; f.write_bytes(b"x")
    ev = evidence.build_skeleton(_info(), _sig(), _tr(), [f], "u")
    ev = evidence.merge(ev, {"visual_evidence": [
        {"type": "slide", "value": "x", "timestamp": 92.0,
         "frame": "t0132_1024.jpg", "confidence": "high"}]})
    assert evidence.validate(ev) == []


def test_validate_accepts_zoom_frame_added_by_patch():
    ev = evidence.merge(_skel(), {
        "zoom_frames": ["t0212_1024.jpg"],
        "visual_evidence": [{"type": "chart", "value": "16.3x", "timestamp": 132.0,
                             "frame": "t0212_1024.jpg", "confidence": "high"}]})
    assert evidence.validate(ev) == []


def test_validate_rejects_transcript_ref_out_of_range():
    """세그먼트가 2개인데 ref=99면 근거가 실재하지 않는다."""
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "transcript", "ref": "99"}]}]})
    assert any("99" in e for e in evidence.validate(ev))


def test_validate_rejects_non_numeric_transcript_ref():
    ev = evidence.merge(_skel(), {"claims": [
        {"claim": "x", "timestamp": 1.0, "evidence": [{"source": "transcript", "ref": "중간쯤"}]}]})
    assert any("transcript" in e for e in evidence.validate(ev))


def test_summary_line_includes_knowledge_count():
    assert "knowledge=0" in evidence.summary_line(_skel())
```

- [ ] **Step 2: 실패 확인** → `python -m pytest tests/test_evidence.py -k "knowledge or provenance or range" -v`

- [ ] **Step 3: 구현**

```python
SCHEMA_VERSION = "0.3"

KNOWLEDGE_TYPES = ("concept", "procedure", "action", "command", "setting",
                   "prerequisite", "result", "criterion", "warning",
                   "example", "comparison")
```

`build_skeleton` 반환 dict에 `"knowledge_items": []` 추가 (claims 다음).

`merge`에 추가:
```python
    for item in patch.get("knowledge_items") or []:
        item = dict(item)
        item.setdefault("id", _next_id(ev.setdefault("knowledge_items", []), "k"))
        ev["knowledge_items"].append(item)
```

`validate`에 헬퍼와 검사 추가:
```python
def _known_frames(ev: dict) -> set:
    fr = (ev.get("provenance") or {}).get("frames") or {}
    out = set()
    for bucket in ("map", "zoom"):
        for f in fr.get(bucket) or []:
            name = f.get("file") if isinstance(f, dict) else str(f)
            if name:
                out.add(name)
    return out


def _check_evidence_refs(kind, ident, ev_list, ve_ids, known_frames, n_segments, errs):
    """claims와 knowledge_items가 같은 근거 규칙을 쓰므로 한 곳에 둔다."""
    if not ev_list:
        errs.append(f"{kind}[{ident}].evidence: empty — 근거 없는 항목은 담지 않는다")
    for e in ev_list:
        src = e.get("source")
        if src not in EVIDENCE_SOURCES:
            errs.append(f"{kind}[{ident}].evidence.source: {src!r} not in {EVIDENCE_SOURCES} "
                        f"— 'both' 대신 transcript/frame 두 항목으로 나눠 적는다")
            continue
        ref = e.get("ref")
        if not ref:
            errs.append(f"{kind}[{ident}].evidence.ref: empty for source={src!r}")
        elif src == "frame":
            if ref not in ve_ids:
                errs.append(f"{kind}[{ident}].evidence.ref: {ref!r} not found in visual_evidence")
        else:
            s = str(ref)
            if not s.isdigit():
                errs.append(f"{kind}[{ident}].evidence.ref: transcript ref는 세그먼트 인덱스"
                            f"(숫자)여야 한다, got {ref!r}")
            elif int(s) >= n_segments:
                errs.append(f"{kind}[{ident}].evidence.ref: transcript 세그먼트 {s} 없음 "
                            f"(총 {n_segments}개) — 근거가 실재하지 않는다")
```

`validate` 본문에서 visual_evidence 검사에 프레임 실재성 추가:
```python
        elif v["frame"] not in known:
            errs.append(f"visual_evidence[{vid}].frame: {v['frame']!r} not in "
                        f"provenance.frames — 실재하지 않는 프레임을 근거로 쓸 수 없다")
```

그리고 claims·knowledge_items 양쪽에 `_check_evidence_refs`를 적용, knowledge type 검사 추가.

`summary_line`에 `knowledge={len(...)}` 추가.

- [ ] **Step 4~6:** 테스트 통과 → 전체 스위트 → 커밋

---

## Task 2: SKILL.md — 자연어 단일 인터페이스 + adaptive video.md

**Files:** `skills/tuto/SKILL.md`

- [ ] **Step 1: frontmatter**

```yaml
argument-hint: "<video-url> [자연어 요청]"
```
description에서 모드 열거를 제거하고 "AI가 대신 영상을 보고 검증된 지식으로 만든다"로 재작성.

- [ ] **Step 2: 모드 판정 절 삭제 → 역할 경계 절로 교체**

```markdown
## 이 스킬이 하는 일과 하지 않는 일

**하는 일:** 영상을 충분히 이해하고 근거를 수집해 `evidence.json` + `video.md`를 만든다.
**하지 않는 일:** 사용자의 자연어 요청을 수행하는 것. 그건 이 스킬을 호출한 에이전트의 몫이다.

**사용자 요청은 분석 깊이를 바꾸지 않는다.** "핵심만 알려줘"라고 해도 영상을 얕게 보지 않는다 —
사용자는 영상을 보지 않으므로 무엇을 놓쳤는지 검증할 수 없다. 요청은 **수집한 지식을
어떻게 쓸지**만 바꾼다.
```

- [ ] **Step 3: §4 산출 계약 재작성** — evidence patch에 `knowledge_items` 추가, 그 다음 `video.md`.

**누락 방지 질문 9개**를 빌더 계약에 박는다 (있으면 수집·없으면 생략).

**video.md outline은 빌더가 정한다** — 예시 4종(튜토리얼/강의/인터뷰/데모)을 참고용으로만 제시하고 "이건 예시일 뿐"을 명시.

- [ ] **Step 4: §6-B INSIGHT 절 삭제**, §7 응답을 단일 흐름으로.

- [ ] **Step 5: 후속 질문 절** — 모드가 아니라 내부 fallback으로 재서술.

- [ ] **Step 6: 실행 안전 절 신설**

```markdown
## 실행형 요청 시 (calling agent 대상 안내)

영상의 명령을 그대로 실행하지 않는다:
튜토리얼 지시 → 현재 환경 점검 → 의미·호환성 확인 → 안전한 적용 → 실행 → 결과 검증

`curl | bash`·삭제·sudo·시스템 설정 변경은 호출한 에이전트의 안전 정책과 권한 흐름을 따른다.
이 스킬은 지식을 제공할 뿐 실행을 지시하지 않는다.
```

- [ ] **Step 7: backward compatibility 절**

```markdown
`--guide`/`--insight`는 내부 alias로만 남는다(무시해도 동작에 지장 없음).
`guide.md`/`insight.md`는 더 이상 생성하지 않는다 — `video.md`가 대체한다.
기존 캐시의 파일은 지우지 않는다.
```

- [ ] **Step 8: 커밋**

---

## Task 3: 스키마 문서 · 메타데이터 · README

- [ ] `docs/eval/evidence-schema.md`에 `knowledge_items` 절, 참조 무결성 불변식 2개 추가, 버전 0.3
- [ ] `plugin.json`/`marketplace.json` → `0.3.0`, description 재작성
- [ ] README 히어로를 **"Let AI watch YouTube for you."** 로, 아키텍처 다이어그램을 `MAP → ZOOM → EVIDENCE → VERIFY → ORGANIZE → video.md`로. **측정 수치·감사 사례·교훈·평가 도구 전부 보존**
- [ ] 커밋

---

## Task 4: 통합 검증 · PR

- [ ] 전체 테스트
- [ ] `claude plugin validate .`
- [ ] 거부 케이스 5종 실측 (가짜 프레임 / 범위 밖 transcript ref / both / 숫자 confidence / 근거 없는 항목)
- [ ] 푸시 · PR

---

## Self-Review

**스펙 커버리지**

| 요구 | 태스크 |
|---|---|
| 사용자-facing 모드 제거 | T2 Step 1·2·4 |
| 요청과 이해의 분리 | T2 Step 2 |
| evidence canonical 유지 | T1 (스키마 확장만, 원칙 무변경) |
| knowledge_items | T1 |
| video.md 고정 템플릿 금지 | T2 Step 3 |
| 누락 방지 질문 9개 | T2 Step 3 |
| evidence 우선 순서 유지 | T2 Step 3 (v0.2 계약 계승) |
| guide/insight 통합 | T2 Step 7 |
| 실행 안전 | T2 Step 6 |
| provenance 검증 강화 | T1 |
| README 재포지셔닝 | T3 |
| 기존 자산 보존 | Global Constraints + T3 |
| 과확장 금지 | Global Constraints |

**타입 일관성** — `_known_frames(ev)`, `_check_evidence_refs(kind, ident, ev_list, ve_ids, known_frames, n_segments, errs)`를 T1에서 정의하고 `validate`가 claims·knowledge_items 양쪽에 적용한다.
