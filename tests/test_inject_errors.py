import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "docs" / "eval"))
import importlib
inj = importlib.import_module("inject-errors")


def _ev():
    return {
        "visual_evidence": [{"id": f"v{i}", "value": f"commit 50d1d8{i} step", "timestamp": float(i)}
                            for i in range(6)],
        "claims": [],
        "knowledge_items": [
            {"id": f"k{i}", "type": t, "content": f"명령 {i}", "timestamp": float(i),
             "evidence": [{"source": "frame", "ref": f"v{i}"}]}
            for i, t in enumerate(["command", "setting", "command", "example", "concept", "example"])
        ],
    }


def test_injects_requested_count_and_reports_them():
    """주입 건수와 보고 목록이 일치해야 시험이 성립한다."""
    ev, injected = inj.inject(_ev(), n=4, seed=7)
    assert len(injected) == 4
    assert all("id" in r and "before" in r and "after" in r for r in injected)


def test_injection_actually_changes_values():
    """보고만 하고 값을 안 바꾸면 시험이 무의미하다."""
    src = _ev()
    ev, injected = inj.inject(json.loads(json.dumps(src)), n=3, seed=1)
    changed = 0
    for rec in injected:
        for ve in ev["visual_evidence"]:
            if ve["id"] == rec["id"]:
                assert ve["value"] == rec["after"] != rec["before"]
                changed += 1
    assert changed == 3


def test_splits_between_high_and_low_priority():
    """표본 상위(command/setting)와 하위(example/concept)에 절반씩 넣어야
    '표본 밖 오류는 못 잡는다'는 가설을 검증할 수 있다."""
    ev, injected = inj.inject(_ev(), n=4, seed=3)
    tiers = {r["tier"] for r in injected}
    assert tiers == {"high", "low"}
    assert sum(1 for r in injected if r["tier"] == "high") == 2
