"""SKILL.md 계약 정적 검증.

프롬프트 층은 단위 테스트로 동작을 잡을 수 없다. 그래서 **계약 문구가 실제로 존재하는지**를
검사한다 — 리팩터링 중에 조용히 사라지는 것을 막는 회귀 테스트다.

여기서 잡으려는 회귀는 실제로 있었던 것들이다:
- v0.3에서 "자연어 요청 수행은 이 스킬의 책임이 아니다"가 UX를 끊어 분석 후 종료됐다
- 커버리지 감사가 video.md 제목을 대조해 adaptive 문서에서 무력해졌다
- 표본 감사가 claims만 봐서 실행 위험이 큰 knowledge_items가 검증 밖에 있었다
"""
import re
from pathlib import Path

import pytest

SKILL = Path(__file__).parent.parent / "skills" / "tuto" / "SKILL.md"
TEXT = SKILL.read_text(encoding="utf-8")


def _section(title: str) -> str:
    """`## <title>`부터 다음 `## `까지."""
    m = re.search(rf"^## {re.escape(title)}.*?$(.*?)(?=^## )", TEXT, re.M | re.S)
    assert m, f"섹션을 찾지 못했다: {title}"
    return m.group(1)


# ── ① 자연어 요청 continuation ─────────────────────────────────────────────

def test_skill_declares_single_request_interface():
    assert "/tuto <video-url> [자연어 요청]" in TEXT
    assert "argument-hint" in TEXT


def test_skill_requires_continuing_the_original_request():
    """분석 후 종료하지 말고 원래 요청을 이어서 수행하라는 계약이 있어야 한다."""
    assert "분석에서 멈추지 않는다" in TEXT
    assert "원래 요청을 이어서 수행한다" in TEXT


def test_skill_forbids_asking_user_to_repeat_the_request():
    assert "다시 말해야 하는 구조를 만들지 않는다" in TEXT


def test_skill_does_not_reintroduce_user_facing_modes():
    """COMPARE/APPLY/EXECUTE 같은 새 모드를 만들지 않는다."""
    assert "새 모드를 만들지 않는다" in TEXT
    for mode in ("--compare", "--apply", "--execute", "--learn"):
        assert mode not in TEXT, f"사용자-facing 모드가 도입됐다: {mode}"


def test_skill_keeps_role_separation():
    assert "eyes + video understanding" in TEXT
    assert "reasoning + hands" in TEXT


def test_execution_requests_keep_the_safety_chain():
    sec = _section("실행형 요청 시 (호출한 에이전트 대상 안내)")
    for step in ("환경 점검", "호환성", "결과 검증"):
        assert step in sec, f"실행 안전 흐름에서 빠짐: {step}"
    assert "curl | bash" in sec


# ── ② 커버리지 감사: evidence 기준 ─────────────────────────────────────────

def test_coverage_audit_targets_evidence_not_headings():
    sec = _section("5. 표본 감사 (Agent 서브에이전트, 독립 컨텍스트)")
    assert "심판 대상은 `video.md` 제목이 아니라 `evidence.json`이다" in sec
    assert "claims[].claim + knowledge_items[].content" in sec


def test_coverage_audit_uses_coverage_input_command():
    assert "--coverage-input" in TEXT, "커버리지 대조 입력 생성 명령이 문서에 없다"


def test_coverage_audit_orders_source_then_evidence_then_document():
    sec = _section("5. 표본 감사 (Agent 서브에이전트, 독립 컨텍스트)")
    assert "`소스 → evidence` 먼저, `evidence → video.md` 나중" in sec


def test_coverage_audit_forbids_empty_categories():
    sec = _section("5. 표본 감사 (Agent 서브에이전트, 독립 컨텍스트)")
    assert "빈 범주를 억지로 만들지 마라" in sec


def test_coverage_findings_are_reverified_before_merge():
    sec = _section("5. 표본 감사 (Agent 서브에이전트, 독립 컨텍스트)")
    assert "바로 추가하지 않는다" in sec


# ── ③ 표본 감사: knowledge_items 포함 ──────────────────────────────────────

def test_sample_audit_covers_knowledge_items():
    sec = _section("5. 표본 감사 (Agent 서브에이전트, 독립 컨텍스트)")
    assert "`knowledge_items`까지다" in sec


def test_sample_audit_uses_priority_command():
    assert "--audit-candidates" in TEXT


def test_sample_audit_keeps_sampling_principle():
    sec = _section("5. 표본 감사 (Agent 서브에이전트, 독립 컨텍스트)")
    assert "모든 항목을 감사하지 않는다" in sec


def test_sample_audit_withholds_document_body():
    sec = _section("5. 표본 감사 (Agent 서브에이전트, 독립 컨텍스트)")
    assert "본문은 주지 않고" in sec, "확증 편향 차단 원칙이 사라졌다"


def test_sample_audit_keeps_escalation():
    sec = _section("5. 표본 감사 (Agent 서브에이전트, 독립 컨텍스트)")
    assert "MISMATCH 또는 UNVERIFIABLE" in sec


# ── 보존 검사: v0.3 강점이 살아 있는가 ─────────────────────────────────────

@pytest.mark.parametrize("marker", [
    "evidence patch를 먼저 만들고 그다음 문서를 쓴다",   # 순서 고정
    "오케스트레이터는 프레임을 Read하지 않는다",          # 비용 티어링
    "지도 프레임으로 덮이지 않은 지점은 무조건 1024",     # 해상도 규칙
    "프레임 공백",                                        # gap detection
    "`source: \"both\"`는 없다",                          # 출처 분리
    "누락 방지 질문",                                     # adaptive 문서 계약
    "영상을 미리 정한 문서 템플릿에 밀어 넣지 않는다",    # 템플릿 금지
])
def test_v03_strengths_are_preserved(marker):
    assert marker in TEXT, f"v0.3 강점이 사라졌다: {marker}"


def test_no_stale_v02_outputs_as_current():
    """guide.md/insight.md는 호환 안내로만 등장해야 하고 산출물로 지시되면 안 된다."""
    for line in TEXT.splitlines():
        if "guide.md" in line or "insight.md" in line:
            assert ("더 이상" in line or "호환" in line), \
                f"v0.2 산출물이 현행처럼 적혀 있다: {line.strip()[:80]}"


# ── v0.3.2: 구식 builder audit 계약이 다시 들어오지 않는지 ─────────────────

def test_builder_does_not_select_audit_candidates():
    """빌더가 표본 감사 후보를 반환하던 v0.2 계약은 제거됐다.

    같은 LLM이 "무엇을 뽑을지"와 "무엇을 검증할지"를 둘 다 정하면 독립성이 없고,
    후보 누락만으로 불필요한 재지시가 발생했다. 선정은 --audit-candidates가 한다."""
    for stale in ("표본 주장 후보 6건", "후보 미반환", "표본 주장 후보"):
        assert stale not in TEXT, f"구식 builder audit 계약이 되살아났다: {stale}"


def test_builder_responsibility_is_three_steps():
    sec = _section("4. 근거 추출 → evidence.json → video.md")
    assert "빌더의 책임은 위 3단계까지다" in sec


def test_audit_candidate_selection_is_delegated_to_script():
    assert "--audit-candidates" in TEXT


# ── v0.3.2: 시각 관측 (visual coverage) ────────────────────────────────────

def test_reading_agent_produces_visual_coverage():
    """관측은 §2 판독 에이전트가 만든다 — 이미 프레임을 읽고 있어 추가 비용이 없고,
    빌더와 독립이라 coverage source로서 의미가 있다."""
    sec = _section("2. 확대 계획 판정 → zoom-plan.json (판독 에이전트 위임)")
    assert "visual-coverage.json" in sec
    assert "추가 판독 비용은 사실상 0" in sec


def test_visual_observation_is_existence_signal_not_value():
    sec = _section("2. 확대 계획 판정 → zoom-plan.json (판독 에이전트 위임)")
    assert "값 판독이 아니라 존재 확인" in sec


def test_visual_observation_must_not_be_inferred_from_captions():
    """자막에서 유추해 만들면 자막 기반 감사와 같은 것을 두 번 보는 셈이라 사각지대가 남는다."""
    sec = _section("2. 확대 계획 판정 → zoom-plan.json (판독 에이전트 위임)")
    assert "자막에서 유추해 만들지 마라" in sec


def test_coverage_audit_consumes_visual_observations():
    sec = _section("5. 표본 감사 (Agent 서브에이전트, 독립 컨텍스트)")
    assert "VISUAL OBSERVATIONS" in sec
    assert "존재 신호이지 값의 정본이 아니다" in sec


def test_coverage_survives_missing_observations():
    sec = _section("5. 표본 감사 (Agent 서브에이전트, 독립 컨텍스트)")
    assert "관측 파일이 없으면 digest만 나온다" in sec


def test_audit_stamp_covers_knowledge_not_only_claims():
    assert "고위험 지식·주장" in TEXT, "감사 스탬프가 claims만 의미하는 표현으로 남아 있다"


# ── gaps 정의 (2026-08-14 실측: 빌더 3명 중 2명이 gaps에 산문 노트를 넣어 merge 거부) ──

def test_skill_defines_gaps_as_time_ranges_not_notes():
    """예시 JSON 한 줄만으로는 부족했다 — gaps가 시간 구간 객체 전용이며 산문 노트는
    '누락 후보'로 가야 한다는 명시 문구가 있어야 한다."""
    assert "시간 구간 객체만" in TEXT
    assert "누락 후보" in TEXT


# ── 본체 모델 티어 (2026-08-18 실측: 본체 opus가 전체 비용의 56%, $7.20) ──

def test_skill_recommends_sonnet_for_orchestrator():
    """본체는 프레임을 읽지 않고 조율만 하므로 상위 모델이 불필요하다는 안내가 있어야 한다."""
    assert "본체(오케스트레이터) 모델" in TEXT
    assert "sonnet" in TEXT


# ── 콜 수 통제 (2026-08-18 실측: 빌더 41콜 $3.26 vs 판독 4콜 $0.47) ──

def test_skill_requires_parallel_frame_reads():
    """프레임을 순차로 Read하면 콜마다 이전 컨텍스트가 재청구된다 — 병렬 지시가 있어야 한다."""
    assert "한 번에 병렬로 Read" in TEXT


def test_skill_forbids_repeated_edit_on_video_md():
    """video.md를 Edit으로 여러 번 고치면 콜 수가 늘어난다 — 한 번에 Write 계약."""
    assert "video.md는 한 번에 Write" in TEXT


def test_skill_caps_coverage_audit_frame_reads():
    """커버리지 감사가 자율적으로 프레임 15장을 열어 $0.58을 썼다 — 상한이 있어야 한다."""
    assert "프레임은 3장 이내" in TEXT
