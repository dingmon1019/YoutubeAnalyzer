# evidence.json 스키마 (v0.3)

이 문서가 스키마 **정본**이다. `skills/tuto/scripts/evidence.py`의 docstring이 아니라 여기를
먼저 고치고 코드를 맞춘다. 검증 구현은 `evidence.validate()`이고, CLI는 위반 시 exit 2다.

## 왜 이 파일이 중심 산출물인가

`video.md`는 **사람이 읽는 렌더링**이다. 상위 에이전트(Claude·ChatGPT 등)가
추론에 쓰는 것은 `evidence.json`이다. 문서는 문장으로 뭉개지지만 evidence는
`claim → evidence.ref → visual_evidence.frame`으로 근거가 끝까지 추적된다.

**역할 경계:** 이 파일은 *"영상에서 실제로 무엇이 말해졌고 무엇이 화면에 있었는가"*만 담는다.
*"그것이 사용자의 상황에서 어떤 의미인가"*는 담지 않는다 — 근거 추출과 추론의 분리다.

---

## 최상위 구조

```jsonc
{
  "schema_version": "0.3",
  "video":       { /* 메타 */ },
  "video_type":  { /* 유형 판정 + 결정론적 힌트 */ },
  "provenance":  { /* 이 근거들이 어디서 왔는가 */ },
  "segments":    [ /* 자막 — transcript 증거 */ ],
  "visual_evidence": [ /* 화면 — visual 증거 */ ],
  "claims":      [ /* 주장 + 근거 참조 + 검증 상태 */ ],
  "knowledge_items": [ /* 작업 가능한 지식 단위 */ ],
  "gaps":        [ /* 프레임이 없는 구간 */ ],
  "flags":       [ /* 파이프라인 경고 */ ]
}
```

### 누가 무엇을 채우는가

| 블록 | 생산자 | 시점 |
|---|---|---|
| `video` `provenance` `segments` `flags` | **Python** (`analyze.py` → `build_skeleton`) | 패스1 종료 |
| `video_type.hint` | **Python** (`classify_hint`) | 패스1 종료 |
| `video_type.primary` | LLM 판독 에이전트 (화면 판독 후) | §2 |
| `visual_evidence` `claims` `knowledge_items` `gaps` | LLM 빌더 | §4 |
| `claims[].verification` | LLM 감사 (`--verdicts`) | §5 |

**LLM은 evidence.json을 직접 쓰지 않는다.** `evidence.py --merge` / `--verdicts`로만 기여한다.
직접 쓰게 두면 스키마 위반이 조용히 통과한다.

---

## 블록별 정의

### `video`

| 필드 | 타입 | 비고 |
|---|---|---|
| `id` | string | 11자 YouTube ID |
| `title` `channel` | string | yt-dlp info |
| `url` | string | 호출 시 URL 우선, 없으면 `webpage_url` |
| `duration` | number | 초 |

### `video_type`

```json
{"primary": "tutorial", "confidence": "high", "basis": "IDE 조작 연속",
 "hint": {"candidates": ["tutorial","demo"], "basis": "활동 피크 3.1/분"}}
```

`primary` 허용값 — `tutorial` `presentation` `interview` `lecture` `demo`
`screen-recording` `mixed` `unknown`

`hint`는 **결정론적 힌트**다(자막 밀도·챕터 수·활동 피크 밀도 세 축). 화면을 보지 않고
계산한 것이므로 **판정이 아니다.** 화면을 본 LLM 판정이 hint와 달라도 되고, 그게 정상이다.

### `provenance`

이 근거들이 어디서 왔는지를 남긴다. 상위 에이전트가 신뢰도를 스스로 판단하려면 필요하다.

```json
{
  "transcript": {"source": "captions|groq|local|none", "lang": "ko",
                 "segments": 189, "dupes_removed": 375, "flags": []},
  "signals": {"heatmap": true, "chapters": 11, "desc_timestamps": 11,
              "activity_peaks": 55, "sponsorblock": 0, "flags": []},
  "frames": {"map": [{"file": "t0132_1024.jpg", "t": 92.0, "res": 1024}], "zoom": []}
}
```

`transcript.source`가 `none`이면 이 영상의 모든 근거는 화면 전용이다.
`signals.flags`에 `heatmap_absent`·`chapters_absent`가 있으면 프레임 선정 신호가 약했다는
뜻이므로, 커버리지가 낮을 수 있다는 신호로 읽는다.

`frames[].t`는 파일명에서 역산한다(`common.frame_label` 재사용). 규약을 벗어난 이름은
`t: null`로 두되 `file`은 보존한다 — 조용히 버리지 않는다.

### `segments` — transcript 증거

```json
{"idx": 0, "start": 0.0, "end": 5.0, "transcript": "안녕하세요"}
```

`end`는 다음 세그먼트의 `start`이고, 마지막은 영상 길이로 닫는다.
`claims[].evidence[].ref`가 `source: "transcript"`일 때 가리키는 값이 `idx`다.

### `visual_evidence` — 화면 증거

```json
{"id": "v1", "type": "chart", "value": "16.3x",
 "timestamp": 132.0, "frame": "t0212_1024.jpg", "confidence": "high"}
```

| 필드 | 규칙 |
|---|---|
| `id` | `v1`부터. `merge`가 자동 부여 |
| `type` | `slide` `ui` `chart` `code` `table` `text` `other` |
| `value` | **화면에서 읽은 문자열 그대로.** 원문 오타도 고치지 않는다 (실측: `irresistable`을 표준 철자로 정규화한 회귀 있음) |
| `frame` | **필수.** 없으면 화면 증거라고 부를 수 없다 |
| `confidence` | `high` `medium` `low` — **숫자 금지** |

### `claims` — 주장

```json
{"id": "c1", "claim": "훅 A/B 조회수 격차가 16.3배", "timestamp": 132.0,
 "evidence": [{"source": "frame", "ref": "v1"},
              {"source": "transcript", "ref": "42"}],
 "conflict": {"transcript": "16배", "screen": "16.3x"},
 "verification": {"status": "verified", "auditor": "sonnet", "note": "..."}}
```

**`evidence[].source`는 `transcript` 또는 `frame`뿐이다. `both`는 없다.**
양쪽 근거가 있으면 두 항목으로 나눠 적는다. 하나로 합치면 "화면에도 있다"는 주장이
검증 없이 통과한다 — 실제로 화면 근거가 있는지 `ref`로 확인할 수 없게 된다.

`ref` 의미: `frame` → `visual_evidence[].id` / `transcript` → `segments[].idx`
`frame` 출처의 `ref`는 **실재하는 id**여야 한다. 없는 id면 `validate`가 잡는다.

**`conflict`가 이 스키마의 핵심이다.** 자막값과 화면값이 다를 때 둘 다 남긴다.
"발표자는 16배라 했지만 슬라이드는 16.3x"를 상위 에이전트가 프로그램적으로 찾을 수 있게
하는 것이 v0.2가 요약기와 갈라지는 지점이다.

### `knowledge_items` — 작업 가능한 지식 단위

```json
{"id": "k1", "type": "command", "content": "pip install -U yt-dlp",
 "timestamp": 88.0, "evidence": [{"source": "frame", "ref": "v2"}]}
```

`claims`가 "영상이 주장한 것"이라면 `knowledge_items`는 **"이 영상으로 무엇을 할 수 있는가"**다.
호출한 에이전트가 설명·비교·적용에 바로 쓰는 단위다.

허용 type 11종:

| type | 무엇 |
|---|---|
| `concept` | 설명된 개념 |
| `procedure` | 순서 있는 절차 묶음 |
| `action` | 단일 조작 |
| `command` | 실행 명령·코드 |
| `setting` | 설정값·파라미터 |
| `prerequisite` | 전제조건 |
| `result` | 결과·산출물 |
| `criterion` | 성공/실패 판단 기준 |
| `warning` | 주의·예외·제한 |
| `example` | 예시 |
| `comparison` | 비교 |

**요청받은 14종에서 3종을 정리했다** — `claim`은 `claims[]`와 중복이고,
`configuration`/`parameter`는 실무에서 경계가 모호해 `setting`으로 합쳤으며,
`artifact`는 `result`와 겹친다. **지나친 온톨로지 설계를 하지 않는 것이 목표다.**

**빈 카테고리를 만들지 않는다.** 영상에 없는 type은 배열에 등장하지 않는다 —
튜토리얼이 아니면 `command` 0건이 정상이고, 인터뷰면 `concept`·`comparison` 위주가 된다.

`evidence`는 `claims`와 **완전히 같은 규칙**을 쓴다(`_check_evidence_refs` 공유).
`content`가 비어 있으면 거부된다.

**`verification`도 `claims`와 같다** (v0.3.1) — 기본값 `unaudited`, 감사 후
`verified|disputed|unverifiable`. 표본 감사는 claims와 knowledge_items를 **한 풀에서**
행동 영향도 순으로 뽑는다(`evidence.py --audit-candidates N`):

```
command > setting > action > criterion > prerequisite > warning
> procedure > result > comparison > claim > concept > example
```

잘못 판독된 `command`나 `setting`은 단순 주장 오류보다 실행에서 위험하기 때문이다.
`apply_verdicts`는 `id`로 두 컬렉션을 함께 찾는다(`c*`/`k*` 접두사가 구분).

### `verification.status`

| 값 | 의미 |
|---|---|
| `verified` | 감사가 반박 실패 (MATCH) |
| `disputed` | 감사가 반박 성공 (MISMATCH) — 본문 교정 대상 |
| `unverifiable` | 감사가 판정 불가 |
| `unaudited` | **감사하지 않음** |

`unaudited`를 별도 값으로 둔 이유: 표본 감사는 6건만 하므로 대부분의 주장은 감사되지
않는다. 이를 `verified`와 섞으면 **감사 못 한 것이 통과한 것처럼** 보인다.

### `gaps`

```json
{"start": 350.0, "end": 469.0, "reason": "지도 프레임 공백"}
```

프레임이 60초 이상 없는 구간. 이 구간의 주장은 화면 근거가 약하다는 뜻이다.
실측 2건에서 영상의 결론부가 통째로 이 구간에 들어 있었다.

---

## 불변식 (validate가 강제)

1. `schema_version == "0.3"`
2. `video_type.primary ∈ VIDEO_TYPES`
3. `visual_evidence[].type ∈ EVIDENCE_TYPES`
4. `visual_evidence[].confidence ∈ {high, medium, low}` — **숫자 금지**
5. `visual_evidence[].frame` 비어 있지 않음 **그리고 `provenance.frames.map|zoom`에 실재**
6. `claims[].evidence` 비어 있지 않음
7. `claims[].evidence[].source ∈ {transcript, frame}` — `both` 금지
8. `claims[].evidence[].ref` 비어 있지 않음
9. `source == "frame"`이면 `ref ∈ visual_evidence[].id` (참조 무결성)
10. `source == "transcript"`면 `ref`가 **숫자**이고 `int(ref) < len(segments)` (범위 검사)
11. `claims[].verification.status ∈ VERIFY_STATUS`
12. `knowledge_items[].type ∈ KNOWLEDGE_TYPES`, `content` 비어 있지 않음, `evidence` 규칙 동일

**목표: 모든 claim과 knowledge_item이 실재하는 자막 세그먼트나 포착된 프레임으로 추적
가능해야 한다.** LLM이 그럴듯한 프레임명(`t9999_1024.jpg`)이나 범위 밖 세그먼트 인덱스를
지어내면 거부된다 — v0.2에서는 둘 다 통과했다.

위반은 예외가 아니라 **목록**으로 반환된다 — 한 번에 다 보여줘야 고치는 쪽이 왕복을 덜 한다.
CLI는 목록이 비어 있지 않으면 `INVALID:` 줄을 stderr로 내고 exit 2 한다.

---

## CLI

```bash
python skills/tuto/scripts/evidence.py <cache_dir> --summary
python skills/tuto/scripts/evidence.py <cache_dir> --merge patch.json
python skills/tuto/scripts/evidence.py <cache_dir> --verdicts verdicts.json
python skills/tuto/scripts/evidence.py <cache_dir> --validate
```

`--merge`·`--verdicts`는 **원자적이다** — 사본에 적용해 검증하고, 통과할 때만 저장한다.
exit 2면 `evidence.json`은 **변경되지 않는다**(`REJECTED:` 줄로 명시). 먼저 저장하고
나중에 검증하면 거부된 patch가 파일에 남아 스키마 게이트가 무의미해진다 — E2E 실측에서
실제로 발생했던 결함이다.

**이 CLI가 향후 MCP 툴 표면이다.** `--summary`/`--merge`/`--validate`가 그대로
`get_evidence`/`add_evidence`/`validate_evidence` 툴이 된다. 그래서 파이썬 API가 아니라
프로세스 경계로 만들었다.

---

## 확장 시 규칙

- **열거형에 값을 추가할 때는 이 문서를 먼저 고친다.** 코드만 고치면 정본이 갈라진다.
- **신뢰도를 정량화하고 싶으면 근거부터 만든다.** 지금 파이프라인에는 확률을 산출할 근거가
  없다. 근거 없이 숫자를 넣으면 상위 에이전트가 그 숫자를 신뢰해 잘못된 가중을 한다.
- `merge`는 append 의미론이다(`video_type`만 교체). 빌더와 감사가 나눠 기여하므로
  나중 호출이 앞의 것을 지우면 안 된다.
