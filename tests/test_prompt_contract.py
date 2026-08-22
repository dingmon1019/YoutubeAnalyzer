# -*- coding: utf-8 -*-
"""프롬프트 파일 계약 — 함수형 서브에이전트 구조의 지시문은 파일이 정본이다.

본체 SKILL.md가 아니라 이 파일들이 판독·합성 규칙을 나른다. 문구가 사라지면
서브에이전트 행동 계약이 깨지므로 테스트로 고정한다.
"""
from pathlib import Path

PROMPTS = Path(__file__).resolve().parents[1] / "skills" / "tuto" / "prompts"
TRANSCRIBE = (PROMPTS / "transcribe.md").read_text(encoding="utf-8")
SYNTHESIZE = (PROMPTS / "synthesize.md").read_text(encoding="utf-8")


class TestTranscribeContract:
    def test_parallel_read_required(self):
        assert "병렬 Read" in TRANSCRIBE

    def test_verbatim_no_guess(self):
        assert "그대로" in TRANSCRIBE
        assert "추측 금지" in TRANSCRIBE

    def test_uncertain_marker(self):
        assert "⚠️ 화면 확인 필요" in TRANSCRIBE

    def test_zoom_request_format(self):
        # 지도 모드가 확대 요청을 최종 응답으로 돌려주는 것이 본체 무이미지의 전제다
        assert "Z:" in TRANSCRIBE
        assert "1024" in TRANSCRIBE

    def test_recheck_mode_exists(self):
        assert "재확인" in TRANSCRIBE

    def test_one_line_final_response(self):
        assert "최종 응답" in TRANSCRIBE

    def test_v_record_format(self):
        assert "V\t" in TRANSCRIBE or "V<TAB>" in TRANSCRIBE

    def test_length_cap(self):
        assert len(TRANSCRIBE) < 3500


class TestSynthesizeContract:
    def test_no_image_read(self):
        assert "이미지 Read 금지" in SYNTHESIZE

    def test_screen_first_conflict(self):
        assert "conflict=" in SYNTHESIZE
        assert "우선" in SYNTHESIZE

    def test_copies_cited_v_lines_only(self):
        # 선별 등재 Task 2: 하류 곱수 제거 — "V 전부 복사" 계약을 "인용 V만 복사"로
        # 축소했다(구 test_copies_all_v_lines의 "그대로 전부 복사" 단언은 이 축소와
        # 직접 충돌해 갱신한다 — Global Constraints의 사전 선언 예외).
        assert "인용 V만 복사" in SYNTHESIZE
        assert "인용하지 않은 관측은" in SYNTHESIZE
        assert "캐시에 남아" in SYNTHESIZE

    def test_refs_syntax(self):
        assert "v#" in SYNTHESIZE and "t#" in SYNTHESIZE

    def test_record_kinds(self):
        for kind in ("T\t", "K\t", "C\t", "G\t"):
            assert kind in SYNTHESIZE, kind

    def test_knowledge_types(self):
        assert "command" in SYNTHESIZE and "setting" in SYNTHESIZE

    def test_actionable_no_fabrication(self):
        assert "행동 가능한" in SYNTHESIZE
        assert "근거 없는 지식 금지" in SYNTHESIZE

    def test_no_padding(self):
        # code-render 실측 교훈: 절감분을 추출 부풀림이 소비한다
        assert "쪼개지 마라" in SYNTHESIZE

    def test_length_cap(self):
        assert len(SYNTHESIZE) < 3500

    def test_gap_record_is_time_range_only(self):
        # G 레코드는 시간 구간(초 단위 시작·끝)만 — 산문 노트는 스키마가 거부한다
        # (구 test_gaps_are_time_ranges 계약 승계: SKILL.md에서 이동 후 누락되었던 것을 보강)
        assert "G\t" in SYNTHESIZE
        assert "산문 노트 금지" in SYNTHESIZE
        assert "초 단위" in SYNTHESIZE


class TestSingleWriteContract:
    # 구 test_single_write_contract 승계: "한 번에 Write" 계약은 TRANSCRIBE·SYNTHESIZE
    # 양쪽 모두가 지킨다 — 순차 Write는 콜마다 컨텍스트를 재청구한다.
    def test_transcribe_writes_output_once(self):
        assert "한 번에 Write" in TRANSCRIBE

    def test_synthesize_writes_output_once(self):
        assert "한 번에 Write" in SYNTHESIZE


class TestParallelReadContract:
    # 구 test_parallel_read_contract 승계: SYNTHESIZE도 입력 파일 전부를 병렬 Read해야
    # 한다 — TRANSCRIBE의 병렬 Read는 test_parallel_read_required가 이미 검증한다.
    def test_synthesize_reads_inputs_in_parallel(self):
        assert "병렬 Read" in SYNTHESIZE


class TestVisionRichnessContract:
    # 실측 교훈(2026-08-19): V 43→10 빈약화가 하류의 자막 의존 오독을 낳았다
    def test_one_value_per_v_line(self):
        assert "값 하나당 V 한 줄" in TRANSCRIBE


class TestTranscriptOnlyValueContract:
    # 실측 오독 2건(settings.js·preferredNotChannel)의 공통 기전 차단
    def test_transcript_only_values_get_warning(self):
        assert "자막에서만 나온 구체값" in SYNTHESIZE
        assert "⚠️ 화면 확인 필요" in SYNTHESIZE


class TestExtractionCapContract:
    # 3레버 라운드(2026-08-19): 상한 없는 추출이 절감분을 소비하는 회귀 차단.
    # 폐기(정보량 비례 K 예산, 2026-08-22): 고정 "최대 30건"은 시간 비례 설계의
    # 잔재라 이 라운드가 폐기한다 — 천장은 이제 --k-budget이 계산해 디스패치가
    # 주입하고, "최대 30건"은 그 값을 못 받았을 때의 폴백 문구로만 남는다.
    def test_knowledge_cap_present(self):
        assert "폴백은 천장 30건" in SYNTHESIZE


class TestNoAutocorrectContract:
    # 실측(2026-08-19): haiku 비전이 축약 명령 키를 온전한 단어로 펴 읽어 4회 연속 오독
    def test_no_abbreviation_expansion(self):
        assert "축약어를 펴지 마라" in TRANSCRIBE


class TestConfidenceVocabularyContract:
    # 실전 버그(2026-08-19, 32분 영상): 프롬프트가 'med'를 안내해 스키마 게이트가
    # V 10건을 거부 — 프롬프트 어휘는 evidence.py 스키마 정본과 일치해야 한다
    def test_confidence_matches_schema(self):
        assert "high|medium|low" in TRANSCRIBE
        assert "|med|" not in TRANSCRIBE


class TestProportionalBudgetContract:
    # 실측(2026-08-19): 고정 상한이 32분 영상 밀도를 1/3로 깎음
    def test_zoom_scales_with_duration(self):
        assert "20분 초과" in TRANSCRIBE   # 지도 모드: 긴 영상은 확대 6~8곳

    # 폐기(정보량 비례 K 예산, 2026-08-22): "최대 30건"·"분당" 비례는 시간을 정보량의
    # 대리 지표로 쓴 설계였다 — 이제 K 천장·하한은 자막 문자수·V라인 수 기반
    # --k-budget이 산출해 디스패치가 주입한다. 새 계약: SYNTHESIZE가 그 주입값을
    # 따르라고 명시하는지 검증한다.
    def test_knowledge_cap_scales(self):
        assert "디스패치가 주는" in SYNTHESIZE
        assert "K 예산" in SYNTHESIZE


class TestZoomLeverContract:
    # 리뷰 F2(2026-08-19): "확대 레버"가 문구상 상한만 올라가고 실제 선택 기준은 그대로면
    # 레버가 작동하지 않는다 — 항목별 개수도 20분 초과 시 함께 올라가야 하고
    # (6곳+2곳=상한 6~8곳과 합이 맞는다), 판정 근거가 명시돼야 한다.
    def test_density_pick_count_scales(self):
        assert "상위 3~4곳(영상 20분 초과면 6곳)" in TRANSCRIBE

    def test_gap_pick_count_scales(self):
        assert "구간 1곳(초과면 2곳)" in TRANSCRIBE

    def test_transcribe_states_duration_basis(self):
        assert "STATUS duration=" in TRANSCRIBE

    def test_synthesize_states_duration_basis(self):
        assert "STATUS duration=" in SYNTHESIZE


class TestKnowledgeFloorContract:
    # 실측(2026-08-19, v0.9.0 run1): "분당 2.5건까지"는 천장일 뿐 — 모델이 40건에서 멈춤.
    # 긴 영상 밀도는 목표·하한이 있어야 나온다.
    # 폐기(정보량 비례 K 예산, 2026-08-22): "분당 1.5건 이상을 목표"는 시간 비례
    # 하한이었다 — 이제 하한은 --k-budget이 계산해 디스패치가 주입하고, 그 하한이
    # "할당량이 아니라 목표"임을 프롬프트가 명시하는지로 계약을 바꾼다(부풀리기 방어).
    def test_long_video_has_floor_target(self):
        assert "하한은 목표이지 할당량이 아니다" in SYNTHESIZE


class TestBlindTranscribeContract:
    # 실측(2026-08-19): 자막 문맥이 날조의 재료 — CORS 화면에서 main.py 20줄을 지어냄
    def test_blind_mode_no_transcript(self):
        assert "자막 경로가 주어지지 않으면" in TRANSCRIBE
        assert "찾지 마라" in TRANSCRIBE


class TestGapBackfillReviewFixes:
    # Task 2 리뷰 F2(Important): 절차 1 "자막 파일을 Read한다"가 무조건문이면 blind
    # 모드에서도 haiku가 자막을 능동 검색할 소지가 있다 — 조건절로 명시해야 한다.
    def test_transcript_read_conditional_on_path_given(self):
        assert "경로가 주어진 경우만" in TRANSCRIBE

    # Task 2 리뷰 F1(Critical): 합성 입력이 gap.lines 하나로 고정되면 12장 초과 분할 시
    # 2번째 배치(gap2.lines)가 무통보 누락된다 — synthesize.md는 gap*.lines 전부를 받아야 한다.
    def test_synthesize_accepts_all_gap_batches(self):
        assert "gap*.lines 전부" in SYNTHESIZE


class TestStepGranularityContract:
    # 실측(2026-08-21, kYP 본게이트): "쪼개지 마라"가 따라하기 절차의 단계 병합으로
    # 과잉 작동 — VidIQ 연결 4단계가 뭉개져 유지율 71%. 재현 가능성 우선 명시.
    def test_steps_are_not_merged(self):
        assert "단계는 합치지 마라" in SYNTHESIZE
        assert "재현 가능성이 우선" in SYNTHESIZE


class TestDensitySelfCheckContract:
    # 전사 밀도 안정화 Task 1(2026-08-21): 임계 2.0/장 실측 확정(빈약 실행 전부
    # <1.6, 건강 실행 전부 ≥2.1) — Write 전 자가 점검으로 훑고 지나간 전사를 감지한다.
    def test_self_check_before_write(self):
        assert "Write 전에 세라" in TRANSCRIBE

    def test_self_check_threshold(self):
        assert "프레임 수 × 2" in TRANSCRIBE

    def test_self_check_remediation(self):
        assert "각 프레임을 다시 개별로 보며 빠뜨린 값을 보충한 뒤" in TRANSCRIBE


class TestVisionTypeEnumStrengthenedContract:
    # 전사 밀도 안정화 Task 1b(2026-08-21): 실측 게이트에서 haiku가 enum 밖
    # `diagram`을 17건 출력해 merge가 전량 거부됐다 — type 줄에 목록 밖 단어
    # 금지를 강화한다(evidence.py가 별칭으로 흡수하지만 애초에 덜 내야 싸다).
    def test_out_of_enum_word_forbidden(self):
        assert "목록 밖 단어" in TRANSCRIBE
        assert "diagram" in TRANSCRIBE

    def test_diagram_graph_map_to_chart_guidance(self):
        assert "다이어그램" in TRANSCRIBE and "그래프" in TRANSCRIBE


class TestKnowledgeCeilingHarmonized:
    # 천장 조화(density-cure 2차, 2026-08-21): 실측 3회(K 29·30·30)가 전부 "최대
    # 30건" 천장에 붙어 있었다 — 20분 이하 영상에서 K≥40 목표는 계약상 도달 불가
    # 였다. >20분에만 있던 분당 2.5 비례를 전 영상 max(30, 분당2.5)로 조화했었다.
    # 폐기(정보량 비례 K 예산, 2026-08-22): 시간(분당) 비례 자체가 정보량의 대리
    # 지표라 양방향으로 틀렸다 — 저정보 영상엔 과다, 고정보 영상엔 절단(보존 캐시
    # 12영상 보정 실측). max(30, 분당2.5) 조화안을 전량 폐기하고 자막 문자수·V라인
    # 수 기반 --k-budget으로 교체한다. 새 계약: 천장·하한이 디스패치 주입값을
    # 따른다는 문구와 미주입 시 폴백 문구가 SYNTHESIZE에 남아 있는지 검증한다.
    def test_ceiling_follows_dispatch_injected_budget(self):
        assert "디스패치가 주는" in SYNTHESIZE
        assert "K 예산: 하한" in SYNTHESIZE

    def test_fallback_when_budget_not_given(self):
        assert "못 받았으면" in SYNTHESIZE
        assert "폴백은 천장 30건" in SYNTHESIZE


class TestScreenGroundingContract:
    # 근거 인용 감지 라운드(2026-08-22): pwGeWRlrU10 실측 — 화면 확대 프레임(217s)이
    # `Size: 25`를 보여줬는데도 정본은 자막의 "30"을 그대로 실었다(V 10건 복사 +
    # 인용 0건). `V 복사 m건`만으로는 "복사했지만 인용 안 함"을 구분 못 하므로
    # `V 인용 j건`을 별도 필드로 추가하고, 화면 구체값은 자막 유무와 무관하게
    # 등재 의무로 명시한다.
    def test_response_reports_cited_v_count_separately(self):
        assert "V 복사 m건" in SYNTHESIZE
        assert "V 인용 j건" in SYNTHESIZE

    def test_concrete_screen_values_must_be_registered(self):
        assert "구체값" in SYNTHESIZE
        assert "설정값·UI 라벨·수치·파일명" in SYNTHESIZE
        assert "자막이 말하지 않아도 K로 등재" in SYNTHESIZE

    def test_screen_adopted_on_conflict_for_concrete_values(self):
        assert "화면을 채택" in SYNTHESIZE

    def test_floor_not_filled_by_transcript_only(self):
        assert "하한을 자막만으로 채우지 마라" in SYNTHESIZE
