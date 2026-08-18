"""solo SKILL.md 계약 정적 검증.

v0.5.0에서 위임 오케스트레이션 문서를 solo 실행 문서로 전면 교체했다. 이 파일은
그 교체와 함께 재작성됐다(구 테스트 36개 폐기 — 위임 계약 전용이었다).

지키는 계약: ① watch 대비 차별점 6개, ② 콜 수 규율(병렬 Read·단일 Write),
③ 정직성(표본 감사 미실시 명시), ④ 문서 길이 상한(다시 자라는 회귀 방지)."""
from pathlib import Path

SKILL = Path(__file__).parent.parent / "skills" / "tuto" / "SKILL.md"
TEXT = SKILL.read_text(encoding="utf-8")


def test_single_interface():
    assert "/tuto <video-url> [자연어 요청]" in TEXT


def test_continues_user_request_after_analysis():
    assert "분석에서 멈추지 않는다" in TEXT


# ── watch 대비 차별점 6개 (스펙 §1 — 하나라도 빠지면 watch의 복제품이 된다) ──

def test_diff1_machine_evidence():
    assert "evidence.json" in TEXT and "--merge" in TEXT


def test_diff2_screen_first_and_conflict():
    assert "화면 값을 채택" in TEXT or "화면을 우선" in TEXT
    assert "conflict" in TEXT
    assert "⚠️ 화면 확인 필요" in TEXT


def test_diff3_cue_based_zoom():
    assert "여기 보" in TEXT and "지시어" in TEXT


def test_diff4_cross_check():
    assert "--cross-check" in TEXT


def test_diff5_coverage_audit_haiku():
    assert "haiku" in TEXT and "--coverage-input" in TEXT
    assert "이미지" in TEXT and "Read 금지" in TEXT


def test_diff6_cached_followup():
    assert "재실행은 금지" in TEXT or "재실행 금지" in TEXT


# ── 콜 수 규율 (라운드5 실측: 비용은 콜 수 × 상주 컨텍스트) ──

def test_parallel_read_contract():
    assert "한 응답에서 병렬" in TEXT


def test_single_write_contract():
    assert "한 번에 Write" in TEXT


# ── 정직성 ──

def test_declares_no_sample_audit():
    assert "표본 감사 미실시" in TEXT


def test_gaps_are_time_ranges():
    assert "시간 구간 객체만" in TEXT


# ── 길이 상한 (문서가 다시 자라면 매 콜 비용으로 직결된다) ──

def test_skill_doc_stays_small():
    assert len(TEXT) < 7000, f"SKILL.md {len(TEXT)}자 — 7,000자 상한 초과"


def test_frontmatter_present():
    """frontmatter가 없으면 스킬 등록·트리거링이 깨진다 — solo 전환 때 실제로 빠뜨렸던 결함."""
    assert TEXT.startswith("---\n")
    head = TEXT.split("---", 2)[1]
    assert "name: tuto" in head
    assert "argument-hint" in head
    assert "user-invocable: true" in head
