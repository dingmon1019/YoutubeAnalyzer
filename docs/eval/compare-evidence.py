#!/usr/bin/env python
"""개선 전후 evidence.json을 대조해 품질 게이트를 판정한다.

라운드5 스펙 §4의 게이트를 도구화한 것이다. 사람이 눈으로 대조하면 놓친다.

사용:
    python docs/eval/compare-evidence.py --before old/evidence.json --after new/evidence.json
"""
import argparse
import json
import sys

KNOWLEDGE_FLOOR = 0.8   # 지식 항목 유지율 하한
WARN_DELTA_MAX = 2      # "⚠️ 화면 확인 필요" 증가 허용치


def _values(ev):
    return {ve.get("value", "") for ve in (ev.get("visual_evidence") or [])
            if isinstance(ve, dict)}


def _warn_count(ev):
    n = 0
    for ve in (ev.get("visual_evidence") or []):
        if isinstance(ve, dict) and "화면 확인 필요" in str(ve.get("value", "")):
            n += 1
    return n


def compare(before: dict, after: dict) -> dict:
    """값 불일치·지식 유지율·경고 증가를 계산하고 게이트 통과 여부를 판정한다.

    값 불일치는 "개선 전 값이 사라졌는데 편집거리가 가까운 다른 값이 생긴" 경우로 센다.
    단순 누락(값이 통째로 사라짐)은 지식 유지율 쪽에서 잡히므로 여기서 이중 계상하지 않는다."""
    bv, av = _values(before), _values(after)
    lost, gained = bv - av, av - bv
    mismatch = 0
    for l in lost:
        for g in gained:
            if l != g and abs(len(l) - len(g)) <= 2 and (l[:6] == g[:6] or l[-6:] == g[-6:]):
                mismatch += 1
                break
    kb = len(before.get("knowledge_items") or [])
    ka = len(after.get("knowledge_items") or [])
    ratio = round(ka / kb, 3) if kb else 1.0
    warn_delta = _warn_count(after) - _warn_count(before)
    return {
        "value_mismatch": mismatch,
        "values_before": len(bv), "values_after": len(av),
        "knowledge_before": kb, "knowledge_after": ka, "knowledge_ratio": ratio,
        "warn_delta": warn_delta,
        "passed": mismatch == 0 and ratio >= KNOWLEDGE_FLOOR and warn_delta <= WARN_DELTA_MAX,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    a = ap.parse_args()
    with open(a.before, encoding="utf-8") as f:
        before = json.load(f)
    with open(a.after, encoding="utf-8") as f:
        after = json.load(f)
    r = compare(before, after)
    print(f"값 항목      {r['values_before']} → {r['values_after']}")
    print(f"값 불일치    {r['value_mismatch']}건  (게이트: 0)")
    print(f"지식 항목    {r['knowledge_before']} → {r['knowledge_after']}  "
          f"유지율 {r['knowledge_ratio']:.0%}  (게이트: {KNOWLEDGE_FLOOR:.0%})")
    print(f"⚠️ 증감      {r['warn_delta']:+}건  (게이트: +{WARN_DELTA_MAX} 이내)")
    print("PASS" if r["passed"] else "FAIL")
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
