# 코드 대체 라운드 (렌더러 + 컴팩트 patch) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LLM이 하던 표현·전달 작업 2개를 코드로 대체해 `/tuto` 비용을 $2.91 → $2.0~2.2로 낮춘다 — ① video.md는 `evidence.py --render`가 결정론적으로 생성, ② evidence-patch는 컴팩트 TSV 라인 형식으로 받아 코드가 JSON으로 확장.

**Architecture:** 값 추출(vision)과 지식 서술은 LLM에 남기고, 그 결과의 **직렬화와 렌더링**만 코드로 내린다. 저장소 원칙("정본은 evidence.json, video.md는 그것의 렌더링")의 문자적 구현이다. 스키마 게이트·merge·validate는 무변경 재사용 — 확장된 patch가 기존 게이트를 그대로 통과해야 한다. 자율 구성 문서는 템플릿 문서로 바뀐다(승인된 트레이드).

**Tech Stack:** Python 3.11+ / pytest / evidence.py 확장(신규 스크립트 없음)

**설계 승인:** 2026-08-18 대화에서 사용자 승인(①③ 먼저, ② 자동 확대 선정은 실측 후 별도 라운드). 스펙 문서는 사용자 지시("바로진행")로 생략 — 이 헤더가 설계 기록을 겸한다.

## Global Constraints

- 작업 브랜치: `git checkout -b code-render master` (master = f797d08, v0.5.0)
- `python` 명령, fail-loud(조용한 폴백 금지·traceback 노출 금지), 모듈 독립성(공유는 common.py만)
- 테스트 append-only: 기존 테스트·독스트링 무수정 (**이번 라운드 예외 없음** — SKILL.md 수정은 기존 계약 문자열을 전부 보존해야 하며, 계약 테스트로 검증한다)
- `render_video_md`·`expand_lines`는 **evidence.py 안에** 추가한다 (video.md는 evidence의 렌더링이라는 책임 관점 — 파일 분리하지 않는다)
- SKILL.md `len < 7000자` 유지 (계약 테스트 존재)
- 렌더러 출력에 "표본 감사 미실시" 문구 포함 (정직성 계약)
- 커밋: `<type>(<모듈>): <요약>` 한국어 + 끝에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Task 4 게이트 통과 전 배포 금지

## 기준점 (전체 수용 기준)

1. `python -m pytest tests/ -q` 전체 통과 (기존 241 + 신규, 실패 0)
2. `--from-lines`로 확장한 patch가 JSON patch와 **동일한 merge 결과**를 낸다 (동등성 테스트)
3. Task 4 실측: command·setting 오독 0건 / 지식 항목 ≥28건(solo 35의 80% — 추출 로직 무변경이므로 엄격하게) / 비용 **≤$2.5** (기대 $2.0~2.2) / 시간 ≤20분
4. 렌더된 video.md에 근거 인용 `(t=MM:SS)`·화면/자막 구분·conflict 병기·누락 후보·"표본 감사 미실시"가 전부 존재

## File Structure

| 파일 | 책임 | 태스크 |
|---|---|---|
| `skills/tuto/scripts/evidence.py` | `render_video_md()`+`--render`, `expand_lines()`+`--from-lines` | 1, 2 |
| `skills/tuto/SKILL.md` | §4를 lines 형식으로, §7을 --render로 배선 | 3 |
| `tests/test_evidence.py` | 렌더러·확장기 단위 테스트 (append) | 1, 2 |
| `tests/test_skill_contract.py` | 신규 배선 계약 (append) | 3 |
| `README.md`·`.claude-plugin/plugin.json` | v0.6.0 (실측 후) | 5 |

---

### Task 1: `evidence.py --render` — video.md 결정론 렌더러

**Files:**
- Modify: `skills/tuto/scripts/evidence.py` (`summary_line` 함수 앞에 렌더러 블록 추가, `main()`에 `--render` 추가)
- Test: `tests/test_evidence.py` (append)

**Interfaces:**
- Produces: `render_video_md(ev: dict, cross_flags: int = 0, coverage_added: int = 0) -> str`, CLI `evidence.py <cache_dir> --render [--cross-flags N] [--coverage-added N]` → `<cache_dir>/video.md` Write 후 경로 출력

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_evidence.py` 끝에 append:

```python
def _render_fixture():
    return {
        "video": {"id": "x", "title": "테스트 영상", "url": "https://youtu.be/x",
                  "duration": 687.0, "channel": "채널"},
        "video_type": {"primary": "tutorial", "confidence": "high", "basis": "화면 실연"},
        "visual_evidence": [
            {"id": "v1", "type": "ui", "value": "16.3x", "timestamp": 132.0,
             "frame": "t0212_1024.jpg", "confidence": "high"}],
        "claims": [
            {"id": "c1", "claim": "속도가 빨라진다", "timestamp": 132.0,
             "evidence": [{"source": "frame", "ref": "v1"}, {"source": "transcript", "ref": "12"}],
             "conflict": {"transcript": "16배", "screen": "16.3x"},
             "verification": {"status": "unaudited"}}],
        "knowledge_items": [
            {"id": "k1", "type": "command", "content": "pip install -U yt-dlp",
             "timestamp": 88.0, "evidence": [{"source": "frame", "ref": "v1"}],
             "verification": {"status": "unaudited"}},
            {"id": "k2", "type": "concept", "content": "자막 전용 개념", "timestamp": 10.0,
             "evidence": [{"source": "transcript", "ref": "3"}],
             "verification": {"status": "unaudited"}}],
        "gaps": [{"start": 350.0, "end": 469.0, "reason": "지도 공백"}],
        "flags": [],
    }


def test_render_contains_required_elements():
    """게이트 기준 4: 근거 인용·화면/자막 구분·conflict 병기·누락 후보·정직성 문구."""
    md = evidence.render_video_md(_render_fixture(), cross_flags=1, coverage_added=2)
    assert "# 테스트 영상" in md
    assert "(t=01:28)" in md and "(t=02:12)" in md          # fmt_ts 인용
    assert "화면 확인" in md and "자막 근거만" in md          # 근거 구분
    assert "16배" in md and "16.3x" in md                    # conflict 병기
    assert "05:50" in md and "07:49" in md and "지도 공백" in md   # gaps
    assert "표본 감사 미실시" in md
    assert "교차 대조" in md and "1" in md                   # 스탬프에 flag 수


def test_render_groups_knowledge_by_priority():
    """command가 concept보다 먼저 — AUDIT_PRIORITY 순 그룹."""
    md = evidence.render_video_md(_render_fixture())
    assert md.index("pip install") < md.index("자막 전용 개념")


def test_render_cli_writes_file(tmp_path):
    ev = _render_fixture()
    (tmp_path / "evidence.json").write_text(
        __import__("json").dumps(ev, ensure_ascii=False), encoding="utf-8")
    import sys as _sys
    __import__("importlib").reload(evidence) if False else None
    evidence.save(tmp_path, ev)
    rc = None
    _argv = ["evidence.py", str(tmp_path), "--render", "--cross-flags", "1"]
    old = _sys.argv; _sys.argv = _argv
    try:
        rc = evidence.main()
    finally:
        _sys.argv = old
    assert rc == 0
    out = (tmp_path / "video.md").read_text(encoding="utf-8")
    assert "# 테스트 영상" in out
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_evidence.py -q -k render` / Expected: FAIL (`render_video_md` 부재)

- [ ] **Step 3: 구현** — `evidence.py`의 `summary_line` 정의 앞에 추가:

```python
# ── video.md 렌더러 — "정본은 evidence.json, video.md는 그것의 렌더링"의 문자적 구현.
# LLM이 16KB 문서를 출력하던 비용(solo 실측 output의 약 절반)을 0으로 만든다.
# 자율 구성 대신 고정 템플릿 — 값·근거는 evidence와 바이트 단위로 동일하다.

_TYPE_LABELS = {
    "command": "명령어", "setting": "설정", "action": "조작", "criterion": "판단 기준",
    "prerequisite": "준비조건", "warning": "주의사항", "procedure": "절차",
    "result": "결과", "comparison": "비교", "claim": "주장", "concept": "개념",
    "example": "예시",
}


def _evidence_tag(item: dict) -> str:
    srcs = {e.get("source") for e in (item.get("evidence") or []) if isinstance(e, dict)}
    if "frame" in srcs and "transcript" in srcs:
        return "화면+자막"
    if "frame" in srcs:
        return "화면 확인"
    return "자막 근거만"


def _item_line(item: dict, text_key: str) -> str:
    t = common.fmt_ts(float(item.get("timestamp", 0)))
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
        f"- **길이**: {common.fmt_ts(float(v.get('duration') or 0))} · **채널**: {v.get('channel', '')}",
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
            lines.append(f"- {common.fmt_ts(float(g.get('start', 0)))}–"
                         f"{common.fmt_ts(float(g.get('end', 0)))} 구간 미확인 ({g.get('reason', '')})")
    for fl in ev.get("flags") or []:
        lines.append(f"- flag: {fl}")
    if not (ev.get("gaps") or ev.get("flags")):
        lines.append("- (기록된 공백 없음)")
    lines += ["", "---", f"*evidence.json이 정본이다 — 이 문서는 `evidence.py --render`가 생성했다.*", ""]
    return "\n".join(lines)
```

`main()` 인자 추가(`--summary` 위):

```python
    ap.add_argument("--render", action="store_true",
                    help="evidence.json에서 video.md를 결정론적으로 생성")
    ap.add_argument("--cross-flags", dest="cross_flags", type=int, default=0)
    ap.add_argument("--coverage-added", dest="coverage_added", type=int, default=0)
```

출력부(`if args.summary:` 위):

```python
    if args.render:
        md = render_video_md(ev, args.cross_flags, args.coverage_added)
        out = Path(cd) / "video.md"
        out.write_text(md, encoding="utf-8", newline="\n")
        print(f"RENDERED {out}")
```

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/test_evidence.py -q` → 전체 PASS
- [ ] **Step 5: 실데이터 관측 (L3)** — Run: `python skills/tuto/scripts/evidence.py "%USERPROFILE%\.yta\cache\7MEsgHKQGLg-solo-opus" --render --cross-flags 1` → 생성된 video.md를 열어 형식 확인, 관측 결과를 보고서에 기록 (원본 video.md는 덮어써도 됨 — 보존 사본이 별도 존재)
- [ ] **Step 6: Commit**

```bash
git add skills/tuto/scripts/evidence.py tests/test_evidence.py
git commit -m "feat(evidence): video.md 결정론 렌더러 — LLM 문서 작성 비용을 0으로"
```

---

### Task 2: `evidence.py --from-lines` — 컴팩트 patch 확장기

**Files:**
- Modify: `skills/tuto/scripts/evidence.py` (`merge` 함수 앞에 확장기 추가, `main()`에 `--from-lines` 추가)
- Test: `tests/test_evidence.py` (append)

**Interfaces:**
- Produces: `expand_lines(text: str) -> dict` (patch dict 반환), CLI `evidence.py <cache_dir> --from-lines <파일>` — 확장 → 기존 merge/validate 경로로 저장, INVALID 시 exit 2 동일

**라인 형식 (TAB 구분, 첫 필드가 레코드 종류):**

```
T	tutorial	high	근거 한 줄
V	ui	132.0	t0212_1024.jpg	high	화면에서 읽은 문자열 그대로
K	command	88.0	v1;t12	pip install -U yt-dlp
C	132.0	v1;t12	주장 한 문장	conflict=16배=>16.3x
G	350.0	469.0	지도 공백
```

- V의 id는 등장 순서대로 v1..vN 자동 부여. K/C의 refs는 `;` 구분 — `v#`는 visual id, `t#`은 transcript 인덱스. C의 5번째 필드(conflict)는 선택. 값 내부의 탭은 작성 시 스페이스로 치환한다(문서화).

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_evidence.py` 끝에 append:

```python
_LINES = (
    "T\ttutorial\thigh\t화면 실연\n"
    "V\tui\t132.0\tt0212_1024.jpg\thigh\t16.3x 표시\n"
    "K\tcommand\t88.0\tv1;t12\tpip install -U yt-dlp\n"
    "C\t132.0\tv1;t12\t속도가 빨라진다\tconflict=16배=>16.3x\n"
    "G\t350.0\t469.0\t지도 공백\n"
)


def test_expand_lines_builds_full_patch():
    p = evidence.expand_lines(_LINES)
    assert p["video_type"] == {"primary": "tutorial", "confidence": "high", "basis": "화면 실연"}
    ve = p["visual_evidence"][0]
    assert ve["id"] == "v1" and ve["timestamp"] == 132.0 and ve["frame"] == "t0212_1024.jpg"
    k = p["knowledge_items"][0]
    assert k["evidence"] == [{"source": "frame", "ref": "v1"}, {"source": "transcript", "ref": "12"}]
    c = p["claims"][0]
    assert c["conflict"] == {"transcript": "16배", "screen": "16.3x"}
    assert c["verification"] == {"status": "unaudited"}
    assert p["gaps"] == [{"start": 350.0, "end": 469.0, "reason": "지도 공백"}]


def test_expand_lines_rejects_unknown_record():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        evidence.expand_lines("X\t뭔가\n")


def test_expand_lines_merge_equivalence(tmp_path):
    """확장 결과가 손으로 쓴 JSON patch와 동일한 merge 결과를 내야 한다 (기준점 2)."""
    import json as _json
    base = {"schema_version": "0.3", "video": {"id": "x", "duration": 687.0},
            "video_type": {}, "provenance": {"frames": {"map": [
                {"file": "t0212_1024.jpg", "t": 132.0}], "zoom": []}, "transcript": {}},
            "segments": [{"start": float(i), "text": f"s{i}"} for i in range(20)],
            "visual_evidence": [], "claims": [], "knowledge_items": [], "gaps": [], "flags": []}
    evidence.save(tmp_path, _json.loads(_json.dumps(base)))
    merged_a = evidence.merge(_json.loads(_json.dumps(base)), evidence.expand_lines(_LINES))
    json_patch = {
        "video_type": {"primary": "tutorial", "confidence": "high", "basis": "화면 실연"},
        "visual_evidence": [{"id": "v1", "type": "ui", "value": "16.3x 표시",
                             "timestamp": 132.0, "frame": "t0212_1024.jpg", "confidence": "high"}],
        "knowledge_items": [{"type": "command", "content": "pip install -U yt-dlp", "timestamp": 88.0,
                             "evidence": [{"source": "frame", "ref": "v1"},
                                          {"source": "transcript", "ref": "12"}]}],
        "claims": [{"claim": "속도가 빨라진다", "timestamp": 132.0,
                    "evidence": [{"source": "frame", "ref": "v1"},
                                 {"source": "transcript", "ref": "12"}],
                    "conflict": {"transcript": "16배", "screen": "16.3x"},
                    "verification": {"status": "unaudited"}}],
        "gaps": [{"start": 350.0, "end": 469.0, "reason": "지도 공백"}]}
    merged_b = evidence.merge(_json.loads(_json.dumps(base)), json_patch)
    for key in ("visual_evidence", "claims", "knowledge_items", "gaps"):
        assert merged_a[key] == merged_b[key], key
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_evidence.py -q -k expand` / Expected: FAIL

- [ ] **Step 3: 구현** — `merge` 정의 앞에 추가:

```python
# ── 컴팩트 patch 라인 확장기 — LLM이 JSON 보일러플레이트(따옴표·중괄호·필드명)를
# 출력하던 토큰을 30~40% 줄인다. 확장 결과는 기존 merge/validate 게이트를 그대로 탄다.

def _parse_refs(spec: str) -> list:
    out = []
    for tok in (spec or "").split(";"):
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith("v"):
            out.append({"source": "frame", "ref": tok})
        elif tok.startswith("t"):
            out.append({"source": "transcript", "ref": tok[1:]})
        else:
            raise ValueError(f"알 수 없는 근거 참조: {tok!r} (v#=frame, t#=transcript)")
    return out


def expand_lines(text: str) -> dict:
    """TAB 구분 라인(T/V/K/C/G)을 evidence patch dict로 확장한다. 형식 위반은
    ValueError로 fail-loud — 조용히 건너뛰면 지식이 소리 없이 유실된다."""
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
                    "id": f"v{vn}", "type": f[1], "timestamp": float(f[2]),
                    "frame": f[3], "confidence": f[4], "value": f[5]})
            elif kind == "K":
                patch["knowledge_items"].append({
                    "type": f[1], "timestamp": float(f[2]),
                    "evidence": _parse_refs(f[3]), "content": f[4]})
            elif kind == "C":
                c = {"timestamp": float(f[1]), "evidence": _parse_refs(f[2]),
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
            if isinstance(e, ValueError) and ("레코드" in str(e) or "근거 참조" in str(e)):
                raise
            raise ValueError(f"{ln}행 형식 오류 ({kind}): {raw[:80]!r} — {e}") from e
    return patch
```

`main()` 인자(`--merge` 아래):

```python
    ap.add_argument("--from-lines", dest="from_lines",
                    help="컴팩트 TSV 라인 파일을 patch로 확장해 병합 (T/V/K/C/G)")
```

쓰기 경로 연결 — `writing = bool(args.merge or ...)` 줄을 `args.from_lines` 포함으로 바꾸고, `if args.merge:` 앞에:

```python
        if args.from_lines:
            candidate = merge(candidate, expand_lines(
                Path(args.from_lines).read_text(encoding="utf-8")))
```

(expand_lines의 ValueError는 main에서 잡아 `INVALID:` 접두 stderr + exit 2로 — 기존 fail-loud 관례와 동일하게. try/except를 writing 블록에 추가하라.)

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/ -q` → 전체 PASS
- [ ] **Step 5: Commit**

```bash
git add skills/tuto/scripts/evidence.py tests/test_evidence.py
git commit -m "feat(evidence): 컴팩트 patch 라인 형식 — JSON 보일러플레이트 출력 제거"
```

---

### Task 3: SKILL.md 배선

**Files:**
- Modify: `skills/tuto/SKILL.md` (§4 evidence 단계, §7 video.md 단계, 검증 스탬프 서술)
- Test: `tests/test_skill_contract.py` (append — 기존 16개 무수정)

**Interfaces:**
- Consumes: Task 1 `--render`, Task 2 `--from-lines`
- Produces: solo 문서가 새 CLI를 지시. **기존 계약 문자열 전부 보존** (특히 "한 번에 Write"는 lines 파일에 적용되도록 §4 문구를 유지·조정, "표본 감사 미실시"는 렌더러가 넣지만 SKILL.md 서술에도 유지)

- [ ] **Step 1: 계약 테스트 append**:

```python
def test_render_and_lines_wired():
    """코드 대체 라운드: 문서 생성은 --render, patch는 --from-lines — LLM이 JSON·문서를
    직접 쓰던 시대의 지시가 남아 있으면 안 된다."""
    assert "--render" in TEXT
    assert "--from-lines" in TEXT
    assert "evidence-patch.json" not in TEXT
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_skill_contract.py -q -k wired` / Expected: FAIL

- [ ] **Step 3: SKILL.md 수정**
  - §4를 다음 취지로 교체(기존 검증 규칙 4개·"화면 우선·conflict·⚠️·gaps 객체·unaudited" 서술은 유지하되, JSON 예시를 라인 형식 예시로 교체):
    - `<cache_dir>/patch.lines`를 **한 번에 Write** (TAB 구분, T/V/K/C/G — Task 2의 형식 예시 5줄을 그대로 싣는다. V의 id는 자동 부여, refs는 `v1;t12`, C의 conflict는 `conflict=자막값=>화면값`, 값 안의 탭은 스페이스로)
    - `evidence.py "<cache_dir>" --from-lines "<cache_dir>/patch.lines"` — exit 2면 INVALID 보고 1회 수정
  - §7을 교체: LLM이 문서를 쓰지 않는다 —

    ```
    **7. video.md — 코드가 생성한다.**
    `evidence.py "<cache_dir>" --render --cross-flags <5단계 flag 수> --coverage-added <6단계 보강 수>`
    문서는 evidence.json의 결정론적 렌더링이며 "표본 감사 미실시" 명시를 포함한다.
    네가 문서를 다시 쓰거나 Edit하지 마라 — 고칠 것이 있으면 evidence를 고치고 다시 render한다.
    ```
  - 콜 수 규율의 `&&` 연쇄 예시에 `--from-lines`와 `--render` 연쇄를 반영
- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/ -q` 전체 PASS + `python -c "print(len(open('skills/tuto/SKILL.md',encoding='utf-8').read()))"` < 7000
- [ ] **Step 5: Commit**

```bash
git add skills/tuto/SKILL.md tests/test_skill_contract.py
git commit -m "feat(skill): patch.lines·--render 배선 — LLM은 값 추출만, 직렬화·렌더링은 코드"
```

---

### Task 4: 게이트 실측 (컨트롤러 전담)

- [ ] Step 1: `claude plugin marketplace update yta && claude plugin update tuto@yta`로 새 SKILL 반영 확인
- [ ] Step 2: 캐시 백업 후 빈 디렉토리에서 `claude -p "tuto 스킬로 https://youtu.be/7MEsgHKQGLg 이 영상을 분석해줘" --allowedTools "..." --output-format json --model opus`
- [ ] Step 3: 판정 — 오독 0(command/setting 수동 대조) / 지식 ≥28 / 비용 ≤$2.5 / ≤20분 / video.md가 렌더러 산출인지 확인(`--render가 생성했다` 푸터)
- [ ] Step 4: `measure-cost.py` 집계, 결과 기록

### Task 5: 문서·v0.6.0 (실측 후)

- [ ] README Measured results·R7 행에 실측치, How it works에 렌더러 반영, 버전·plugin.json `0.6.0`, 전체 게이트, 커밋 `chore(release): v0.6.0 — 코드 렌더러·컴팩트 patch`
- [ ] 병합·배포는 사용자 확인 후

---

## Self-Review 결과

- **커버리지:** 렌더러→Task 1, 확장기→Task 2, 배선→Task 3, 게이트→Task 4, 릴리스→Task 5. ② 자동 확대 선정은 범위 밖(실측 후 별도 라운드 — 헤더에 명시).
- **플레이스홀더:** 렌더러·확장기·테스트 전부 실코드. Task 3만 "취지 교체" 서술인데, 보존해야 할 계약 문자열이 계약 테스트로 기계 검증되므로 구현 재량이 안전하다.
- **타입 일관성:** `render_video_md(ev, cross_flags=0, coverage_added=0)`·`expand_lines(text)->dict`를 Task 3 CLI 지시가 같은 이름으로 소비. `_parse_refs`의 `t12`→`{"source":"transcript","ref":"12"}`는 기존 validate의 인덱스 검사 형식과 일치(문자열 ref). 동등성 테스트(기준점 2)가 이를 봉인한다.
- **주의:** Task 1 fixture의 `test_render_cli_writes_file`에서 reload 잔재 줄(`__import__("importlib")...if False`)은 무의미하므로 구현자가 제거해도 된다 — 계획 오기.
