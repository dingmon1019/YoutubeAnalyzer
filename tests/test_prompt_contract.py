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
