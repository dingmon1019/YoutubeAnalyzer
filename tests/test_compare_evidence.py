import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "docs" / "eval"))
import importlib
compare = importlib.import_module("compare-evidence")


def _ev(values, knowledge=3):
    return {"visual_evidence": [{"id": f"v{i}", "value": v} for i, v in enumerate(values)],
            "knowledge_items": [{"id": f"k{i}", "content": "x"} for i in range(knowledge)],
            "claims": []}


def test_detects_value_mismatch(tmp_path):
    """같은 화면 값이 개선 전후로 달라지면 게이트 위반이다."""
    a = tmp_path / "a.json"; b = tmp_path / "b.json"
    a.write_text(json.dumps(_ev(["50d1d83 base", "pick 2739708"])), encoding="utf-8")
    b.write_text(json.dumps(_ev(["50d1c83 base", "pick 2739708"])), encoding="utf-8")
    r = compare.compare(json.loads(a.read_text(encoding="utf-8")),
                        json.loads(b.read_text(encoding="utf-8")))
    assert r["value_mismatch"] == 1
    assert r["passed"] is False


def test_passes_when_values_kept_and_knowledge_above_threshold(tmp_path):
    """값이 같고 지식 항목이 80% 이상이면 통과한다."""
    before = _ev(["50d1d83 base"], knowledge=10)
    after = _ev(["50d1d83 base"], knowledge=8)
    r = compare.compare(before, after)
    assert r["value_mismatch"] == 0
    assert r["knowledge_ratio"] == 0.8
    assert r["passed"] is True


def test_fails_when_knowledge_drops_too_far():
    """지식 항목이 80% 미만으로 떨어지면 게이트 위반이다."""
    r = compare.compare(_ev(["x"], knowledge=10), _ev(["x"], knowledge=7))
    assert r["passed"] is False


def test_warn_delta_over_threshold_fails_gate():
    """⚠️ 화면 확인 필요가 +3건이면 게이트 위반 (허용치 +2)."""
    before = {"visual_evidence": [{"id": "v1", "value": "ok"}],
              "knowledge_items": [{"id": "k1"}]}
    after = {"visual_evidence": [{"id": "v1", "value": "ok"},
                                 {"id": "v2", "value": "⚠️ 화면 확인 필요 (t=01:00)"},
                                 {"id": "v3", "value": "⚠️ 화면 확인 필요 (t=02:00)"},
                                 {"id": "v4", "value": "⚠️ 화면 확인 필요 (t=03:00)"}],
             "knowledge_items": [{"id": "k1"}]}
    r = compare.compare(before, after)
    assert r["warn_delta"] == 3
    assert r["passed"] is False


def test_duplicate_values_collapse_is_visible():
    """같은 값 3건이 1건으로 줄면 values_lost로 드러나야 한다 (set 붕괴 결함 회귀)."""
    before = {"visual_evidence": [{"id": f"v{i}", "value": "50d1d83 base"} for i in range(3)],
              "knowledge_items": [{"id": "k1"}]}
    after = {"visual_evidence": [{"id": "v1", "value": "50d1d83 base"}],
             "knowledge_items": [{"id": "k1"}]}
    r = compare.compare(before, after)
    assert r["values_lost"] == 2


def test_one_new_value_is_not_counted_twice():
    """새 값 하나가 사라진 값 여러 건과 짝지어져 중복 계상되면 안 된다."""
    before = {"visual_evidence": [{"id": "v1", "value": "commit 3f4a625x"},
                                  {"id": "v2", "value": "commit 3f4a625y"}],
              "knowledge_items": [{"id": "k1"}]}
    after = {"visual_evidence": [{"id": "v1", "value": "commit 3f4a625z"}],
             "knowledge_items": [{"id": "k1"}]}
    r = compare.compare(before, after)
    assert r["value_mismatch"] == 1
