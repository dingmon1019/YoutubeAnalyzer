---
name: tuto
description: AI가 사용자 대신 유튜브 영상을 보고, 자막과 화면(슬라이드·UI·표·차트·설정값·코드)을 함께 판독해 근거 추적되는 지식으로 만든다. 모든 값은 프레임·타임스탬프로 추적 가능하고 해시·수치는 교차 대조, 누락은 커버리지 감사로 검출한다. 산출물은 evidence.json(기계용)과 video.md(사람용)다. "영상 분석해줘", "이 영상 설명해줘", "영상에서 알려주는 방법을 우리 프로젝트에 적용해줘", "화면에 나온 설정값·명령어 정리", "이 튜토리얼 따라해줘", "영상 핵심 주장과 근거", "영상 내용 질문할게" 요청 시 사용. 영상 링크 단순 공유나 추천 요청에는 쓰지 않는다.
argument-hint: "<video-url> [자연어 요청]"
allowed-tools: Bash, Read, Write, AskUserQuestion, Agent
user-invocable: true
---

# /tuto — 유튜브 영상 → 근거 추적되는 작업 지식 (오케스트레이터)

`/tuto <video-url> [자연어 요청]` — 인터페이스는 이것 하나다.

**산출물 2개.** `evidence.json`(기계 정본 — 모든 지식이 프레임·타임스탬프·자막 인덱스로
근거 추적된다) + `video.md`(사람용 문서). 자막 요약이 아니라 **화면을 판독**한다: 자막이
"16배"라 말해도 화면이 `16.3x`면 화면 값을 채택하고 불일치를 `conflict`로 보존하며, 또렷하지
않은 값은 추측 대신 `⚠️ 화면 확인 필요`로 남긴다. 이것이 /watch와의 차이다 — watch는 세션이
끝나면 아무것도 남지 않는다.

**사용자 요청이 함께 왔으면 분석에서 멈추지 않는다.** 분석 완료 후 곧바로 그 요청을
이어서 수행한다(설명·비교·적용·실행). 사용자가 "이제 해줘"라고 다시 말하게 하지 않는다.

**너는 오케스트레이터다 — 분석 파이프라인 중 이미지를 절대 Read하지 않는다.** 판독·합성은
일회용 서브에이전트가 자기 컨텍스트에서 수행하고 파일로 남긴다. 이미지·긴 산출물이 본체에
상주하면 콜마다 재청구된다(실측: 본체 단독 $2.91 → 이 구조 목표 $1.2). 너는 vision-*.lines·
patch.lines·video.md 내용을 열어보지도, 응답에 echo하지도 않는다.

**SKILL_DIR**: 이 문서가 있는 디렉토리. **PROMPTS** = `<SKILL_DIR>/prompts`
(`prompts/transcribe.md`·`prompts/synthesize.md`). 명령은
`python "<SKILL_DIR>/scripts/<이름>.py"` (Windows — `python3` 금지).

## 파이프라인

**0. 프리플라이트 (세션 첫 호출만).** `setup.py --check`. exit 0이면 진행하되 stderr
NOTE(yt-dlp 최신성·JS 런타임 부재)는 사용자에게 한 줄 알린다. exit 2면 설치 안내.

**1. 패스1.** `analyze.py "<url>"` (Bash timeout 600000) — 출력을
`<cache_dir>/pass1-report.txt`로 리다이렉트. STATUS·`== CACHE ==`·`== FRAMES ==` 줄만
확인한다(경로·목록 파악용 — 프레임 파일은 열지 않는다). 자막 없음이면 사용자에게 알리고
프레임 중심 진행, 30분 초과 WARNING이면 구간 지정을 제안한다.

**2. 비전① (Agent, `model: "haiku"`).** 디스패치 프롬프트는 경로만 나른다:
"`<PROMPTS>/transcribe.md`를 Read하고 그대로 수행. 모드=지도. 프레임: <FRAMES 목록>.
자막: <cache_dir>/pass1-report.txt. 출력: <cache_dir>/vision-map.lines".
에이전트의 최종 응답 `프레임 N, V라인 M | Z: MM:SS@1024,...`에서 Z 목록을 얻는다 —
이것이 확대 판정이다. 네가 프레임을 보고 고르지 않는다. 선택 기준(값 밀도·지시어 큐 —
"여기 보세요" 등)은 transcribe.md 소관이다. 최종 응답 `프레임 N, V라인 M`에서
**M < N×2이면 빈약 전사** — 같은 디스패치를 `model: "sonnet"`으로 승격해 1회만 재시도(지시에 '빈약 전사 감지 — 프레임당 값을 빠짐없이, 요약 금지' 추가; 실측: haiku 동일 조건 재시도는 만성 빈약을 못 살린다). 재시도 후에도 낮으면 그대로 진행하되 8단계 `--note "저밀도 전사 n/장"`으로 보고한다.

**3. 확대.** `zoom.py <id> --timestamps "<Z목록>"` (1024 최대 4장·20분 초과 8장, 총
6장·초과 12장) 출력을
`<cache_dir>/zoom-out.txt`로 저장하고 `evidence.py "<cache_dir>" --add-frames ...`까지
`&&` 한 호출로. 새 프레임도 너는 Read하지 않는다.

**4. 비전② (haiku).** 같은 프롬프트 파일, 모드=확대. 프레임 목록 대신
`<cache_dir>/zoom-out.txt` 경로를 준다. 출력=`<cache_dir>/vision-zoom.lines`.
최종 응답 `프레임 N, V라인 M`에서 **M < N×2이면 빈약 전사** — 같은 디스패치를 `model: "sonnet"`으로 승격해 1회만 재시도(지시에 '빈약 전사 감지 — 프레임당 값을 빠짐없이, 요약 금지' 추가; 실측: haiku 동일 조건 재시도는 만성 빈약을 못 살린다). 재시도 후에도 낮으면 그대로 진행하되 8단계 `--note "저밀도 전사 n/장"`으로 보고한다.

**5. 합성 (Agent, `model: "sonnet"`).** "`<PROMPTS>/synthesize.md`를 Read하고 수행.
입력: pass1-report.txt, vision-map.lines, vision-zoom.lines. 출력:
<cache_dir>/patch.lines". 인용 V만 복사 + K/C/G — 단일 배치가 계약이다. 최종 응답
`T=<영상유형>, K n건, C n건, V 복사 m건, ⚠️ k건`에서 9단계 보고용 수치를 얻는다.

**6. 병합 + 교차 대조.**
`evidence.py "<cache_dir>" --from-lines "<cache_dir>/patch.lines" --cross-check` 한 호출 —
기존 `--merge` 스키마 검증 게이트를 그대로 통과해야 한다. stdout의 `DROPPED n`은
8단계 `--note "형식 드롭 n건"`으로 보고할 뿐 재전달 대상이 아니다(n>0일 때만). exit 2
INVALID(스키마 검증 실패든 K/C 드롭율 20% 초과든)는 stderr의
**INVALID 전체 목록을 한 번에** 합성 에이전트에 재전달해 1회 수정시키고(파일
수정도 에이전트가 한다), 재전달 후에는 **완료 알림만 기다린다**
(타이머·폴링·ScheduleWakeup 금지). CROSSCHECK 출력은
v-id·kind·값쌍뿐 프레임명이 없다 — flag는 **재확인 디스패치 없이** 건수만 기억해
8단계 `--cross-flags`에 그대로 넣는다.

**7. 커버리지 감사 (Agent, `model: "haiku"`).**
`evidence.py "<cache_dir>" --coverage-input > "<cache_dir>/coverage-digest.txt"` 후
디스패치: "이미지 Read 금지. <digest 경로>와 <pass1-report.txt 경로>를 Read하고, 이
영상을 안 본 에이전트가 작업하려면 알아야 하는데 digest에 없는 지식을 자막으로 검증해
**명백한 것만** `K	type	초단위시각	t#refs	content` 형식으로(t#는 pass1-report의
`== TRANSCRIPT ==` 아래 `[MM:SS]` 줄을 0부터 센 순번. 예:
`K	command	88.0	t12;t13	pip install -U yt-dlp` — refs는 `t` 접두사 필수, 복수는 `;` 구분)
`<cache_dir>/coverage.lines`에 Write. 없으면 파일을 만들지 마라. 최종 응답: '보강 n건'".
n>0이면 `--from-lines coverage.lines`로 반영한다(1회 한정) — exit 2면 stderr의 INVALID를
같은 haiku에 1회만 재전달해 고치게 하고, 그래도 실패하면 `--coverage-added 0`으로 렌더하며
사용자 보고에 실패를 명시한다(**머지에 성공한 건수만 n이다**). n을 기억한다 —
`--coverage-added`에 넣는다. 자막 없는 영상은 이 단계를 생략하고 8단계에서
`--note "커버리지 감사 생략 — 자막 없음"`.

**7.5. 공백 표적 보강 (영상 20분 초과 시에만).** `evidence.py "<cache_dir>" --gap-plan`
실행 — 출력이 비면 이 단계를 건너뛴다(20분 이하 영상은 코드가 무조건 빈 출력을 낸다).
공백 프레임 최대 12장 — 초과분은 긴 공백 우선으로 잘린다. 출력이 있으면: ①
`zoom.py <id> --timestamps "<출력>"` → `<cache_dir>/gap-frames.txt` && `--add-frames`
② **blind 전사(haiku)**: transcribe.md 보강 모드로 gap-frames.txt 경로만 주고
**자막 경로는 주지 않는다**(날조 차단 — 실측 근거) — 프레임은 12장 이하라 한 번에
디스패치한다, 출력 `<cache_dir>/gap.lines` ③ 보강 합성(sonnet): synthesize.md 보강
모드로 coverage-digest.txt + gap.lines(분할했으면 gap2.lines까지 전부)를 주고
`<cache_dir>/gapfill.lines` 작성 ④ `--from-lines gapfill.lines`(1회, exit 2면
INVALID 1회 재전달) ⑤ 보강 건수를 8단계 `--note "공백 보강 n건"`으로 명시(실패 시
0건 명시).

**8. video.md — 코드가 생성한다.**
`evidence.py "<cache_dir>" --render --cross-flags <6단계 flag 수> --coverage-added <7단계 n>`
문서는 evidence.json의 결정론적 렌더링이며 "표본 감사 미실시" 명시를 포함한다. 사유가
여럿이면(예: 커버리지 감사 생략 + 공백 보강) ` · `로 이어 하나의 `--note`로 전달한다.
네가 문서를 쓰거나 고치지 마라 — 고칠 것이 있으면 evidence를 고치고 다시 render한다.

**9. 응답.** 요약(영상유형·핵심 지식 수·⚠️ 건수 — 5단계 합성 에이전트 최종 응답의
T·K·C·⚠️ 값만 쓴다) + 두 산출물 경로. 자연어 요청이 있었으면 **곧바로 이어서 수행한다.**

## 콜 수 규율 — 비용의 지배 요인

`cache_read`는 콜마다 이전 컨텍스트 전체를 재청구한다. 서브에이전트는 순차 의존이다
(비전①→확대→비전②→합성) — 각 Agent 결과를 기다려 다음을 디스패치한다. 독립 셸 명령은
`&&` 연쇄, 같은 스크립트 플래그는 한 호출에 결합. **`--coverage-input`과 `--render`는
절대 한 호출에 묶지 마라** — 사이에 감사·보강이 있고, 같은 호출에서는 `--render`가 먼저
실행된다. 본체 **12콜 이내(공백 보강 발동 시 +4콜 허용)**를 목표로 하되, 초과해도 남은
단계를 생략하지 말고 완주한다 — 콜 절약보다 산출물 완결이 우선이다.

## 후속 질문

이미 분석된 영상은 `<cache_dir>/evidence.json`으로 먼저 답한다(질의 응답 단계에서는
evidence.json Read 허용 — 이것이 캐시 재질의다). **정본에 없는 관측을 물으면
캐시의 vision-*.lines를 그때 Read한다**(인용되지 않아 evidence.json엔 없어도
캐시엔 남아 있다). **analyze.py 재실행 금지.** 근거가
부족할 때만 `zoom.py --timestamps`로 프레임을 만들고 비전 재확인 에이전트로 판독시켜
`--from-lines`로 반영한다 — 이때도 이미지는 에이전트가 본다. `video.mp4 evicted` 오류면
재분석이 필요함을 알린다.

## 실행형 요청 시

영상 명령을 맹목 실행하지 않는다: 환경 점검 → 호환성 확인 → 적용 → 검증.
`evidence.json`의 `prerequisite`·`setting`·`command`를 현재 환경과 대조한 뒤 적용한다.
위험 명령(`curl | bash`·삭제·`sudo`)은 세션의 안전 정책을 따른다.

## 실패 시

다운로드 실패는 평문으로 있는 그대로 보고하고 재시도 루프를 돌지 않는다(1회 자동 폴백은
스크립트가 한다). 서브에이전트가 출력 파일을 만들지 못하면 같은 디스패치를 **1회만**
재시도하고, 그래도 실패면 그 단계 없이 완주하며 사용자에게 명시한다. 모든 flags·WARNING은
보고에 그대로 반영한다.
