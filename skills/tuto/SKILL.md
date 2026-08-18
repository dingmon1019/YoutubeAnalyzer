# /tuto — 유튜브 영상 → 근거 추적되는 작업 지식 (solo)

`/tuto <video-url> [자연어 요청]` — 인터페이스는 이것 하나다.

**산출물 2개.** `evidence.json`(기계 정본 — 모든 지식이 프레임·타임스탬프·자막 인덱스로
근거 추적된다) + `video.md`(사람용 문서). 자막 요약이 아니라 **화면을 판독**한다: 자막이
"16배"라 말해도 화면이 `16.3x`면 화면 값을 채택하고 불일치를 `conflict`로 보존한다.
이것이 /watch와의 차이다 — watch는 세션이 끝나면 아무것도 남지 않는다.

**사용자 요청이 함께 왔으면 분석에서 멈추지 않는다.** 분석 완료 후 곧바로 그 요청을
이어서 수행한다(설명·비교·적용·실행). 사용자가 "이제 해줘"라고 다시 말하게 하지 않는다.

**SKILL_DIR**: 이 문서가 있는 디렉토리. 명령은 `python "<SKILL_DIR>/scripts/<이름>.py"`
(Windows — `python3` 금지).

## 파이프라인 — 전부 네가 직접 한다

서브에이전트는 **6단계의 haiku 커버리지 감사 1건뿐**이다. 판독·추출·문서화를 위임하지
않는다 — 위임은 같은 컨텍스트를 이중 청구한다(실측: 위임 구조 $9.96 → solo 목표 $1.2).

**0. 프리플라이트 (세션 첫 호출만).** `setup.py --check`. exit 0이면 진행하되 stderr에
NOTE가 있으면(yt-dlp 최신성·JS 런타임 부재 등) 사용자에게 한 줄 알린다. exit 2면 설치
안내를 전달한다.

**1. 패스1.** `analyze.py "<url>"` (Bash timeout 600000) — 보고서를
`<cache_dir>/pass1-report.txt`로 파일 리다이렉트한다(파이프 조기 종료 금지). STATUS 줄
확인: 자막 없음이면 사용자에게 알리고 프레임 중심 진행, 30분 초과 WARNING이면 구간 지정을
제안한다. `== CACHE ==` 줄이 `<cache_dir>`다.

**2. 지도 판독 + 확대 판정.** `== FRAMES ==`의 지도 프레임 전량을 **한 응답에서 병렬**
Read하고, 같은 응답에서 확대 지점을 판정한다:
- 읽을 텍스트(터미널·설정·표·코드·슬라이드 본문)가 있는 화면 중 **값 밀도 상위 3~4곳**을 1024로
- 자막 **지시어** 큐 시점 우선 — "여기 보세요"·"이렇게"·"클릭"·"설정"·"입력"·"이 값" /
  "look here"·"click"·"this setting"·"type in"
- 지도가 60초 이상 비는 구간이 있으면 1곳 추가 (결론·요약부가 거기 숨는다)

**3. 확대.** `zoom.py <id> --timestamps "1:05@1024,..."` **1회 호출** (1024 최대 4장,
총 6장) → 출력을 `<cache_dir>/zoom-out.txt`로 저장 →
`evidence.py "<cache_dir>" --add-frames "<cache_dir>/zoom-out.txt"` → 새 프레임을
**한 응답에서 병렬** Read. 판독이 흐리면 `zoom.py <id> --crop "<프레임>@x,y,w,h"` **1회만**.

**4. evidence.** `<cache_dir>/evidence-patch.json`을 **한 번에 Write** →
`evidence.py "<cache_dir>" --merge <patch>`. exit 2면 stderr의 INVALID를 보고 1회 수정.

```json
{"video_type": {"primary": "tutorial", "confidence": "high", "basis": "..."},
 "visual_evidence": [{"type": "ui", "value": "화면 문자열 그대로 (오타도 그대로)",
   "timestamp": 132.0, "frame": "t0212_1024.jpg", "confidence": "high"}],
 "claims": [{"claim": "한 문장", "timestamp": 132.0,
   "evidence": [{"source": "frame", "ref": "v1"}, {"source": "transcript", "ref": "12"}],
   "conflict": {"transcript": "16배", "screen": "16.3x"},
   "verification": {"status": "unaudited"}}],
 "knowledge_items": [{"type": "command", "content": "pip install -U yt-dlp",
   "timestamp": 88.0, "evidence": [{"source": "frame", "ref": "v2"}]}],
 "gaps": [{"start": 350.0, "end": 469.0, "reason": "지도 공백"}]}
```

규칙 — 어길 시 merge가 거부한다:
- 화면에서 또렷이 읽히지 않는 값은 쓰지 않는다. 불확실하면 `⚠️ 화면 확인 필요 (t=MM:SS)`. 추측 금지.
- 자막값 ≠ 화면값이면 **화면을 우선**하고 `conflict`에 둘 다 적는다.
- `knowledge_items.content`는 행동 가능한 수준("Add Python to PATH를 체크한다").
  type: concept·procedure·action·command·setting·prerequisite·result·criterion·warning·example·comparison. 영상에 있는 것만.
- `transcript` ref는 pass1 보고서 자막 인덱스(0부터). `source: "both"`는 없다.
- **`gaps`는 시간 구간 객체만** — 산문 노트는 video.md의 `## 누락 후보`로.
- `verification.status`는 전부 `unaudited`로 둔다.

**5. 교차 대조.** `evidence.py "<cache_dir>" --cross-check` — 해시·수치 판독이 갈린
자리를 비용 0으로 찾는다. CROSSCHECK가 나오면 해당 프레임만 다시 보고 값을 확정해 merge로 정정한다.

**6. 커버리지 감사 (유일한 서브에이전트, `model: "haiku"`).**
`evidence.py "<cache_dir>" --coverage-input` 출력 + `pass1-report.txt` 경로를 주고
"이 영상을 안 본 에이전트가 작업하려면 알아야 하는데 digest에 없는 지식"을 묻는다.
**프롬프트에 이미지 Read 금지를 명시한다** — 자막·digest 텍스트만으로 판단시킨다.
반환된 누락 후보는 자막으로 재확인해 **명백한 것만** merge로 보강한다(1회 한정).

**7. video.md — 한 번에 Write.** Edit 반복 금지(고칠 게 있으면 전체 재작성). 구조는
영상에 맞춰 자율 구성하되 필수 요소:
- 헤더: 제목·URL·길이·자막 출처·영상유형 + **"표본 감사 미실시 — 근거는 프레임·자막으로
  추적 가능하나 독립 검증되지 않음"**
- 모든 값·명령어에 `(t=MM:SS)` 근거, "화면 확인"/"자막 근거만" 구분, 불일치 병기
- `## 누락 후보`, `## 검증 스탬프`(교차 대조 결과 + 커버리지 보강 건수)

**8. 응답.** 요약(영상유형·핵심 지식·⚠️ 건수) + 두 산출물 경로. 자연어 요청이 있었으면
**곧바로 이어서 수행한다.**

## 콜 수 규율 — 비용의 지배 요인

`cache_read`는 콜마다 이전 컨텍스트 전체를 재청구한다(실측: 순차 Read 41콜 $3.26 vs
병렬 4콜 $0.47). **프레임은 한 응답에서 병렬 Read, 문서는 한 번에 Write, 전체 15콜 이내.**

## 후속 질문

이미 분석된 영상은 `<cache_dir>/evidence.json`으로 먼저 답한다. **analyze.py 재실행은 금지.**
근거가 부족할 때만 `zoom.py --timestamps`로 보충하고 merge로 반영한다.
`video.mp4 evicted` 오류면 재분석이 필요함을 알린다.

## 실행형 요청 시

영상 명령을 맹목 실행하지 않는다: 환경 점검 → 호환성 확인 → 적용 → 검증.
`evidence.json`의 `prerequisite`·`setting`·`command`를 현재 환경과 대조한 뒤 적용한다.
위험 명령(`curl | bash`·삭제·`sudo`)은 세션의 안전 정책을 따른다.

## 실패 시

다운로드 실패는 평문으로 있는 그대로 보고하고 재시도 루프를 돌지 않는다(1회 자동 폴백은
스크립트가 한다). 모든 flags·WARNING은 사용자 보고에 그대로 반영한다.
