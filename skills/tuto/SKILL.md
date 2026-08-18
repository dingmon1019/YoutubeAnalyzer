---
name: tuto
description: AI가 사용자 대신 유튜브 영상을 보고, 자막과 화면(슬라이드·UI·표·차트·설정값·코드)을 함께 판독해 근거 추적되는 지식으로 만든다. 모든 값은 프레임·타임스탬프로 추적 가능하고 해시·수치는 교차 대조, 누락은 커버리지 감사로 검출한다. 산출물은 evidence.json(기계용)과 video.md(사람용)다. "영상 분석해줘", "이 영상 설명해줘", "영상에서 알려주는 방법을 우리 프로젝트에 적용해줘", "화면에 나온 설정값·명령어 정리", "이 튜토리얼 따라해줘", "영상 핵심 주장과 근거", "영상 내용 질문할게" 요청 시 사용. 영상 링크 단순 공유나 추천 요청에는 쓰지 않는다.
argument-hint: "<video-url> [자연어 요청]"
allowed-tools: Bash, Read, Write, AskUserQuestion, Agent
user-invocable: true
---

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
않는다 — 위임은 같은 컨텍스트를 이중 청구한다(실측: 위임 구조 $9.96 → solo $2.91).

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
- 지도가 60초 이상 비는 구간이 있으면 1곳 추가하되 **반드시 1024로** — 아무도 못 본 화면은
  "읽을 텍스트가 없다"고 확정할 수 없다 (실측: 미관측 지점을 512로 찍어 값 오류 3건이 난 전례)

**3. 확대.** `zoom.py <id> --timestamps "1:05@1024,..."` **1회 호출** (1024 최대 4장,
총 6장) → 출력을 `<cache_dir>/zoom-out.txt`로 저장 →
`evidence.py "<cache_dir>" --add-frames "<cache_dir>/zoom-out.txt"` → 새 프레임을
**한 응답에서 병렬** Read. 판독이 흐리면 `zoom.py <id> --crop "<프레임>@x,y,w,h"` **1회만**.

**4. evidence.** `<cache_dir>/patch.lines`를 **한 번에 Write** (TAB 구분, 첫 필드가
레코드 종류 T/V/K/C/G) →
`evidence.py "<cache_dir>" --from-lines "<cache_dir>/patch.lines"`. 확장 결과는 기존
`--merge` 검증 게이트를 그대로 탄다. exit 2면 stderr의 INVALID를 보고 1회 수정.

```
T	tutorial	high	근거 한 줄
V	ui	132.0	t0212_1024.jpg	high	화면에서 읽은 문자열 그대로
K	command	88.0	v1;t12	pip install -U yt-dlp
C	132.0	v1;t12	주장 한 문장	conflict=16배=>16.3x
G	350.0	469.0	지도 공백
```

`V`의 id는 등장 순서대로 v1..vN이 **자동 부여**된다 — 너는 id를 쓰지 않는다. `K`/`C`의
근거 필드는 `;` 구분 로컬 참조만 쓴다(`v#`=frame, `t#`=transcript, 예: `v1;t12`). `C`의
5번째 필드(conflict, 선택)는 `conflict=자막값=>화면값` 형식. 값 안의 탭·개행은 스페이스로
치환한다.

규칙 — 어길 시 merge가 거부한다:
- 화면에서 또렷이 읽히지 않는 값은 쓰지 않는다. 불확실하면 `⚠️ 화면 확인 필요 (t=MM:SS)`. 추측 금지.
- 자막값 ≠ 화면값이면 **화면을 우선**하고 conflict 필드에 둘 다 적는다.
- `K`의 마지막 필드(content)는 행동 가능한 수준으로("Add Python to PATH를 체크한다").
  type: concept·procedure·action·command·setting·prerequisite·result·criterion·warning·example·comparison. 영상에 있는 것만.
- `t#` ref는 pass1 보고서 자막 인덱스(0부터).
- **`gaps`는 시간 구간 객체만** — 산문 노트는 video.md의 `## 누락 후보`로. `G` 레코드 외 형식 금지.
- `verification.status`는 확장 시 자동으로 `unaudited`가 붙는다 — 네가 쓰지 않는다.

**5. 교차 대조.** `evidence.py "<cache_dir>" --cross-check` — 해시·수치 판독이 갈린
자리를 비용 0으로 찾는다. CROSSCHECK가 나오면 해당 프레임만 다시 보고, 보정 라인을
`patch.lines`에 써서 `--from-lines`로 정정한다. 보정 라인의 `v#`는 이번 배치에서 새로
쓰는 V만 가리킨다 — 기존 프레임을 근거로 쓰려면 `t#` 자막 참조를 쓰거나 해당 화면을 새
V로 다시 등재한다. CROSSCHECK 줄 수(발견 건수)를 기억해 둔다 — 7단계 `--cross-flags`에
넣는다(정정을 반영했어도 발견 건수를 기록한다 — 판독 오류가 있었다는 사실 자체가 기록
가치다).

**6. 커버리지 감사 (유일한 서브에이전트, `model: "haiku"`).**
`evidence.py "<cache_dir>" --coverage-input` 출력 + `pass1-report.txt` 경로를 주고
"이 영상을 안 본 에이전트가 작업하려면 알아야 하는데 digest에 없는 지식"을 묻는다.
**프롬프트에 이미지 Read 금지를 명시한다** — 자막·digest 텍스트만으로 판단시킨다.
반환된 누락 후보는 자막으로 재확인해 **명백한 것만** `--from-lines`로 보강한다(1회 한정).
보강한 항목 수를 기억해 둔다 — 7단계 `--coverage-added`에 넣는다.
자막이 없는 영상(STATUS flags의 no transcript)은 이 단계를 생략하고
`--render --note "커버리지 감사 생략 — 자막 없음"`으로 명시한다 — 체크리스트의 원천이 없다.

**7. video.md — 코드가 생성한다.**
`evidence.py "<cache_dir>" --render --cross-flags <5단계 flag 수> --coverage-added <6단계 보강 수>`
문서는 evidence.json의 결정론적 렌더링이며 "표본 감사 미실시" 명시를 포함한다.
네가 문서를 다시 쓰거나 Edit하지 마라 — 고칠 것이 있으면 evidence를 고치고 다시 render한다.

**8. 응답.** 요약(영상유형·핵심 지식·⚠️ 건수) + 두 산출물 경로. 자연어 요청이 있었으면
**곧바로 이어서 수행한다.**

## 콜 수 규율 — 비용의 지배 요인

`cache_read`는 콜마다 이전 컨텍스트 전체를 재청구한다(실측: 순차 Read 41콜 $3.26 vs
병렬 4콜 $0.47). **프레임은 한 응답에서 병렬 Read, 문서는 한 번에 Write.** 독립된 셸
명령은 `&&`로 연쇄하고, 같은 스크립트의 플래그는 한 호출에 결합한다(예: zoom 추출과
`--add-frames`는 `&&`로, `--from-lines`와 `--cross-check`는
`evidence.py "<cache_dir>" --from-lines patch.lines --cross-check` 한 호출로 —
`--from-lines`가 저장한 결과에 이어서 교차 대조가 돈다). **`--coverage-input`과
`--render`는 절대 한 호출에 묶지 마라** — 사이에 커버리지 감사와 보강이 있고, 같은
호출에서는 `--render`가 먼저 실행된다. 전체 20콜 이내를 목표로 하되, 초과했더라도 남은
단계를 생략하지 말고 완주한다 — 콜 절약보다 산출물 완결이 우선이다.

## 후속 질문

이미 분석된 영상은 `<cache_dir>/evidence.json`으로 먼저 답한다. **analyze.py 재실행은 금지.**
근거가 부족할 때만 `zoom.py --timestamps`로 보충하고 `--from-lines`로 반영한다.
`video.mp4 evicted` 오류면 재분석이 필요함을 알린다.

## 실행형 요청 시

영상 명령을 맹목 실행하지 않는다: 환경 점검 → 호환성 확인 → 적용 → 검증.
`evidence.json`의 `prerequisite`·`setting`·`command`를 현재 환경과 대조한 뒤 적용한다.
위험 명령(`curl | bash`·삭제·`sudo`)은 세션의 안전 정책을 따른다.

## 실패 시

다운로드 실패는 평문으로 있는 그대로 보고하고 재시도 루프를 돌지 않는다(1회 자동 폴백은
스크립트가 한다). 모든 flags·WARNING은 사용자 보고에 그대로 반영한다.
