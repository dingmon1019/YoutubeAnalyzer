"""오케스트레이터 SKILL.md 계약 정적 검증.

function-agents 라운드에서 solo 실행 문서를 오케스트레이터(본체 무이미지 + 일회용
서브에이전트 판독/합성) 문서로 재배선했다. 판독·합성 세부 규칙(화면 우선·conflict·
⚠️·TSV 레코드 스키마·행동 가능 content)의 정본은 이제 prompts/transcribe.md·
synthesize.md이며, 그쪽 계약은 test_prompt_contract.py가 검증한다. 이 파일은
오케스트레이터 자신의 계약만 검증한다.

지키는 계약: ① watch 대비 차별점 6개, ② 정직성(표본 감사 미실시 명시), ③ 문서 길이
상한(다시 자라는 회귀 방지), ④ 오케스트레이터 전용 계약(본체 무이미지·프롬프트 파일
디스패치·단일 batch from-lines·haiku/sonnet 역할 분리·콜 예산·산출물 미열람)."""
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


# ── 정직성 ──

def test_declares_no_sample_audit():
    assert "표본 감사 미실시" in TEXT


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
    assert "description:" in head
    assert "allowed-tools:" in head


def test_render_and_lines_wired():
    """코드 대체 라운드: 문서 생성은 --render, patch는 --from-lines — LLM이 JSON·문서를
    직접 쓰던 시대의 지시가 남아 있으면 안 된다."""
    assert "--render" in TEXT
    assert "--from-lines" in TEXT
    assert "evidence-patch.json" not in TEXT


def test_no_bare_merge_instructions():
    """리뷰 회귀 가드: 맨 'merge로 ...한다' 지시가 남으면 LLM이 구 JSON 경로로 회귀한다."""
    for phrase in ("merge로 정정", "merge로 보강", "merge로 반영"):
        assert phrase not in TEXT, phrase


def test_render_note_wired():
    assert "--note" in TEXT


class TestOrchestratorContract:
    def test_main_never_reads_images(self):
        assert "이미지" in TEXT and "Read하지 않는다" in TEXT

    def test_dispatches_prompt_files(self):
        assert "prompts/transcribe.md" in TEXT
        assert "prompts/synthesize.md" in TEXT

    def test_vision_returns_zoom_request(self):
        # 본체가 이미지 없이 확대를 결정하는 유일한 통로
        assert "Z:" in TEXT

    def test_single_from_lines_batch(self):
        # vision-*.lines 직접 merge 금지 — id_offset 함정
        assert "vision" in TEXT and "patch.lines" in TEXT

    def test_haiku_vision_sonnet_synthesis(self):
        # run4 실측(2026-08-19): haiku 합성은 날조·오독으로 품질 붕괴 — 합성은
        # 판단 작업이라 sonnet이 하한이다. 이 단언은 그 실측의 회귀 가드다.
        assert '"haiku"' in TEXT and '"sonnet"' in TEXT

    def test_call_budget_present(self):
        assert "12콜" in TEXT

    def test_no_echo_of_artifacts(self):
        assert "echo" in TEXT or "열어보지" in TEXT
