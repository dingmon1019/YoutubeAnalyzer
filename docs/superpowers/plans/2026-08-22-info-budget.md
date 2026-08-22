# 정보량 비례 K 예산 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** K 예산의 닻을 **시간**에서 **측정된 정보량**으로 옮긴다. 같은 10분이라도 플레이리스트
나열은 K가 적게, 고밀도 튜토리얼은 많이 나오게 — 사용자 지시(2026-08-22).

**문제 (실측):** 현행 계약은 천장 `max(30, 분당 2.5)` · 하한 목표 `분당 1.5`로 **시간 비례**다.
시간은 정보량의 대리 지표라 양방향으로 틀린다: ① 저정보 영상(4.6분 프레젠테이션, 자막 58큐)
에게도 천장 30을 주고 하한 7건을 밀어붙여 **부풀리기 압력** ② 고밀도 11.4분 영상은 천장 30이
실재 지식 59건(dense 실측)을 **잘라낸다**. K 29·30·30 천장 포화가 이 증상이었다.

**설계:** 합성 시점에 이미 손에 있는 결정론 신호로 예산을 계산해 디스패치가 숫자로 주입한다.
- 자막 분량(문자수, CJK 비율로 언어 보정 — 한국어는 문자당 정보밀도가 2배 이상)
- V라인 수(화면에 실재하는 값의 양 — v0.16.0에서 신뢰 가능해짐)
- `천장 = max(15, chars/L + V/4)`, `하한 목표 = round(천장 × 0.5)`, L = CJK비율>0.2면 150 아니면 350

**보존 캐시 12영상 보정 결과 ($0, 이미 수행):** maxK(실측 최대 추출량) 대비

| 영상 | 분 | maxK | 현행 천장 | 신 천장 | 신 하한 |
|---|---|---|---|---|---|
| b0HMimUb4f0 | 50.6 | 122 | 127 | 168 | 84 |
| tkkbYCajCjM(ko) | 32.4 | 76 | 81 | 118 | 59 |
| 7MEsgHKQGLg(ko) | 11.4 | **59** | **30 ← 절단** | 59 | 30 |
| kYPAlvnRiiI | 20.1 | 52 | 50 | 111 | 56 |
| pwGeWRlrU10 | 13.0 | 43 | 33 | 77 | **38** |
| 0chZFIZLR_0 | 4.6 | 15 | **30 ← 과다** | 15 | 8 |
| p4_sWV7GUGc(ko) | 5.6 | 14 | 30 | 15 | 8 |
| nHcfoHOW4uA | 1.9 | 13 | 30 | 15 | 8 |

고정보 영상은 천장이 풀리고(30→59·33→77), 저정보 영상은 조여진다(30→15). 하한은 고정보에서만
의미 있게 올라간다(pwGe 19.5→38).

**부풀리기 방어 (스케일 프리모템):** 하한은 **할당량이 아니라 목표**다. 재료가 없으면 미달이
정상이라고 명시하고, 기존 "근거 없는 지식 금지"·"같은 사실 재표현 금지"를 유지한다. 이게 없으면
하한이 날조 유인이 된다.

## Global Constraints
- SKILL <7,000자 · synthesize <2,600자, Windows python, 전체 스위트 PASS,
  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

### Task 1: `--k-budget` + 디스패치 주입 + 계약 재작성
**Files:** skills/tuto/scripts/evidence.py, skills/tuto/SKILL.md, skills/tuto/prompts/synthesize.md,
tests/test_evidence.py(append), tests/test_prompt_contract.py(**기존 단언 대체**), tests/test_skill_contract.py(append)

1. **evidence.py `--k-budget <cache_dir>`**: transcript.json의 segments 텍스트를 이어 붙여 문자수와
   CJK 비율을 재고, cache_dir의 `vision-*.lines`에서 `V\t`로 시작하는 줄을 센다. 위 공식으로
   `KFLOOR n KCEILING m` 한 줄을 stdout에 출력(exit 0). 입력이 없으면(transcript 없음·V 0) 부드럽게
   기본값 `KFLOOR 8 KCEILING 15`. 다른 서브커맨드와 독립적으로 동작해야 한다(fail-soft).
2. **SKILL 5단계**: 합성 디스패치 직전에 `--k-budget`을 호출하고, 그 두 숫자를 디스패치 프롬프트에
   `K 예산: 하한 <n>건 · 천장 <m>건` 형태로 실어 보낸다. 자수 예산이 빠듯하니 문장을 아껴라.
3. **synthesize.md 3항 재작성**: 하드코딩된 "최대 30건과 분당 2.5건 중 큰 쪽"·"분당 1.5건 이상을
   목표" 규칙을 **디스패치가 준 하한·천장을 따르라**로 교체. 못 받았을 때의 폴백(천장 30·하한 없음)
   한 줄. **하한은 목표이지 할당량이 아니다 — 자막·전사에 안 캔 세부(설정값·단계·예시)가 남았으면
   더 캐고, 재료가 없으면 미달인 채로 두어라. 채우려 지어내지 마라**를 명시. 기존 "절차의 단계는
   합치지 마라 — 단계 하나가 K 하나다"·"같은 사실 재표현 쪼개기 금지"는 보존.
4. **테스트**: evidence.py 단위(한국어/영어 픽스처로 L 분기, V 가산, 하한=천장 절반, 빈 입력 폴백,
   실측 회귀 3건 — 7MEs ko 5363자/94V→천장 59, pwGe en 16709자/116V→77, 0chZ en 4333자/0V→15).
   test_prompt_contract.py의 `최대 30건`·`분당 1.5건 이상을 목표`·`TestKnowledgeCeilingHarmonized`
   단언은 이 라운드가 **폐기**한다 — 삭제하지 말고 새 계약 단언으로 교체하고 주석에 폐기 사유
   (시간 비례 → 정보량 비례, 2026-08-22)를 남겨라. SKILL 계약에 `--k-budget` 주입 단언 추가.

TDD, 커밋 1개, 보고서 `.superpowers/sdd/2026-08-22-info-budget/task-1-report.md`.

### Task 2 (controller): v0.17.0 배포 → 게이트 2회
- **고정보 게이트** pwGeWRlrU10(13:02): K **≥40**(하한 38이 작동하는가) · ≤$3.2 · 날조 0
- **저정보 게이트** 0chZFIZLR_0(4:36 프레젠테이션): K가 천장 15 이하로 **자연히 적게** ·
  부풀리기 0(⚠️·근거 없는 K 없음) · ≤$1.5
- 예산 $5, 2연속 실패 시 보류, 개입은 최종 판정 1회.
