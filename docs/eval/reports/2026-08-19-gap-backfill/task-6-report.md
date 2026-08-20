# Task 6 — gap_zoom_plan 공백 원천을 결정론 계산으로 교체

브랜치 `gap-backfill`. 관련: docs/eval/reports/2026-08-19-gap-backfill.md,
docs/superpowers/plans/2026-08-19-gap-backfill.md.

## 동기(실측)

v0.10.1 재실측에서 보강 단계가 미발동했다. 트리거가 `evidence.json`의 `gaps`
(합성 LLM이 기록)에 의존하는데 이 기록이 실행마다 0~16건으로 흔들린다. 공백은
산술이다 — `provenance.frames`의 map+zoom 프레임 타임스탬프를 정렬하고 0초와
`video.duration`을 양끝에 붙여 인접 간격 >60초를 공백으로 계산하면 결정론적이다.

## 변경

`skills/tuto/scripts/evidence.py`:

- 신규 `_frame_gap_source(ev)`: `provenance.frames`(map+zoom)에서 유효한 `t`만
  모아 `{0.0} ∪ 프레임 타임스탬프 ∪ {duration}`을 정렬하고, 인접 쌍 중
  `b - a > 60`인 구간만 공백으로 반환한다. `duration`은 `ev["video"]["duration"]`을
  쓰되 없거나 0이면 마지막 프레임 타임스탬프로 방어한다(그마저 없으면 0.0 → 공백 없음).
- `gap_zoom_plan()`이 `ev.get("gaps")` 대신 `_frame_gap_source(ev)`를 입력으로 쓰도록
  교체. 이후 로직(길이 내림차순 정렬 · <180s 1점/≥180s 2점 · activity 피크 조준 ·
  45초 격리 · ceil/floor 마진 · 상한 16)은 전부 불변.
- `ev["gaps"]`(정직 보고용 G 레코드, `video.md`의 "누락 후보" 절이 그대로 씀)는 이
  계산과 무관 — 다른 코드 경로에는 영향 없음.
- CLI 문구·SKILL.md 트리거 조건("출력이 비면 건너뛴다")은 무변경 — `gap_zoom_plan`이
  빈 리스트를 반환하는 조건(모든 인접 간격 ≤60초)이 그대로 유효하다.

## 테스트 (사전 선언 예외: 함수 입력 계약 변경)

기존 `TestGapZoomPlan` · `TestGapZoomPlanActivity`는 `{"gaps": [...]}` 딕셔너리를
직접 입력으로 썼다 — 새 계약에서는 무의미하므로 픽스처를 프레임 기반으로 갱신했다.
신규 헬퍼 `_frames_ev(ts, duration)`으로 동일한 공백 구간을 만드는 프레임 배치를
재현했다(예: 공백 60~160 → frames t=60·t=160, duration=160).

갱신한 기존 테스트(기대값 불변, 픽스처만 교체):

- `test_short_gap_one_midpoint`, `test_long_gap_two_points`, `test_cap_prefers_long_gaps`
- `test_peak_beats_midpoint`, `test_long_gap_two_peaks_with_separation`,
  `test_zero_curve_falls_back_to_midpoint`, `test_none_curve_keeps_legacy`,
  `test_margin_excludes_gap_edges`, `test_fractional_gap_margin_uses_ceil_floor`
  (버퍼 프레임 t=60.0 추가 — 0~100.5 구간이 별도 공백으로 잡히지 않게 방어)
- `test_gap_plan_falls_back_on_encoding_corrupt_signals_json` (CLI 레벨)

제거: `test_non_dict_gap_skipped` — 구 입력 계약(`ev["gaps"]`의 비-dict 원소 방어) 전용
테스트라 프레임 기반 입력에서는 대응 개념이 없다.

신규 테스트 2건(요구사항 ①②):

- `test_triggers_even_when_llm_gaps_empty` — ① 회귀 가드: `ev["gaps"] = []`(LLM이
  공백을 하나도 기록하지 않은 상태)이어도 프레임이 성기면(t=60, t=160, duration=160)
  여전히 `["01:50@1024"]`가 나온다. 이번 결함(트리거가 LLM 기록에 의존)의 직접 가드.
- `test_no_gaps_empty` — ② 프레임이 조밀(전 간격 ≤60초: 30/60/90, duration=120)하면
  빈 리스트.

## 검증

**L1 (전체 스위트)**: `python -m pytest tests/ -q`

```
325 passed
EXIT=0
```

(`git stash`로 확인한 작업 전 수집 테스트 325건과 동일 — `test_non_dict_gap_skipped` 제거
1건, `test_triggers_even_when_llm_gaps_empty` 신규 1건으로 순변화 0)

**L3 (실캐시)**: `~/.yta/cache/b0HMimUb4f0-v0100-gb`

- 사전 확인: `evidence.json`의 `ev["gaps"]`(LLM 기록) = **8건**, `video.duration` =
  3038.0s, `provenance.frames`: map 25개 · zoom 21개.
- `_frame_gap_source(ev)` (신규 프레임 기반 계산) = **27구간** — LLM이 기록한 8건과
  무관하게 산출됨. 프레임 provenance만으로 계산되므로 이 캐시를 다시 읽어도 항상
  27구간이 나온다(결정론).
- CLI 실행: `evidence.py "<cache_dir>" --gap-plan`

  ```
  40:05@1024,43:23@1024,49:34@1024,50:29@1024,37:22@1024,36:39@1024,45:40@1024,
  14:35@1024,16:08@1024,17:16@1024,32:12@1024,01:05@1024,08:35@1024,10:01@1024,
  11:06@1024,44:43@1024
  ```

  → **16개 지점**, 비어있지 않음. 27구간(길이 내림차순) 중 상한 16으로 정상 절단.
- 대조: 옛 로직(`ev["gaps"]` 8건 기반)을 그대로 재현하면 상한 적용 전 15개 스펙이
  나온다(이번 캐시는 우연히 gaps가 비어있지 않았음). 핵심은 이번 실행값이 아니라
  — 새 로직이 "0~16건으로 흔들리는 LLM 기록"이라는 변동성 자체를 계산 경로에서
  제거했다는 것이다: 같은 캐시를 몇 번 다시 읽어도 27구간·16지점은 항상 동일하다.

## 커밋

1개 커밋 `fix(evidence): gap_zoom_plan 공백 산출을 LLM 기록에서 프레임 결정론 계산으로 교체`.
갱신 테스트명은 커밋 메시지 본문에 나열.
