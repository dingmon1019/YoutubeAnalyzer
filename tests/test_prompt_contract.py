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

    def test_copies_all_v_lines(self):
        assert "그대로 전부 복사" in SYNTHESIZE

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
    # 3레버 라운드(2026-08-19): 상한 없는 추출이 절감분을 소비하는 회귀 차단
    def test_knowledge_cap_present(self):
        assert "최대 30건" in SYNTHESIZE


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

    def test_knowledge_cap_scales(self):
        assert "최대 30건" in SYNTHESIZE   # 기존 계약 유지
        assert "분당" in SYNTHESIZE        # 비례 조항


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
    # 긴 영상 밀도는 목표·하한이 있어야 나온다
    def test_long_video_has_floor_target(self):
        assert "분당 1.5건 이상을 목표" in SYNTHESIZE
