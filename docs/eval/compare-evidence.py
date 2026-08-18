#!/usr/bin/env python
"""개선 전후 evidence.json을 대조해 품질 게이트를 판정한다.

라운드5 스펙 §4의 게이트를 도구화한 것이다. 사람이 눈으로 대조하면 놓친다.

사용:
    python docs/eval/compare-evidence.py --before old/evidence.json --after new/evidence.json
"""
import argparse
import json
import re
import sys
from collections import Counter

KNOWLEDGE_FLOOR = 0.8   # 지식 항목 유지율 하한
WARN_DELTA_MAX = 2      # "⚠️ 화면 확인 필요" 증가 허용치

_ALNUM = re.compile(r"[^0-9A-Za-z가-힣]+")


def _utf8_stdout() -> None:
    """cp949 콘솔에서 한글·⚠️ 출력이 UnicodeEncodeError로 죽는 것을 막는다.
    skills/tuto/scripts/common.py의 utf8_stdout과 같은 처리 — docs/eval 도구는
    모듈 독립성 때문에 common을 임포트하지 않고 최소 복제한다."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _values(ev):
    """중복을 보존한다 — set으로 접으면 같은 값 3건이 1건으로 줄어도 신호가 없다."""
    return [ve.get("value", "") for ve in (ev.get("visual_evidence") or [])
            if isinstance(ve, dict)]


def _warn_count(ev):
    n = 0
    for ve in (ev.get("visual_evidence") or []):
        if isinstance(ve, dict) and "화면 확인 필요" in str(ve.get("value", "")):
            n += 1
    return n


def _looks_like_same_value(a: str, b: str) -> bool:
    """같은 화면 값의 판독이 갈린 것으로 보이는가 (오독 후보)."""
    return a != b and abs(len(a) - len(b)) <= 2 and (a[:6] == b[:6] or a[-6:] == b[-6:])


def _semantic_key(s: str) -> str:
    """서식(공백·개행·구분자)을 걷어낸 비교용 정규형. 값 오독은 영숫자가 달라지는 것이고,
    같은 텍스트를 다르게 직렬화한 것(`—` vs `/`, 빈 줄 유무)은 오독이 아니다.
    실측(2026-08-18): 게이트 FAIL 3건이 전부 이 서식 차이였다."""
    return _ALNUM.sub("", s).lower()


def compare(before: dict, after: dict) -> dict:
    """값 불일치·지식 유지율·경고 증가를 계산하고 게이트 통과 여부를 판정한다.

    값 불일치는 "개선 전 값이 사라졌는데 판독이 갈린 것으로 보이는 값이 새로 생긴" 경우다.
    근접 매칭(near-miss) 쌍이라도 영숫자·한글만 남긴 정규형이 같으면 서식 차이일 뿐
    판독 오류가 아니므로 values_reformatted로 따로 센다(게이트 미대상). 매칭된 새 값은
    두 경우 모두 소비해 하나가 여러 건으로 중복 계상되지 않게 한다. 통째로 사라진 값은
    불일치가 아니라 values_lost로 따로 센다 — 프레임 축소로 인한 예상된 감소와 판독 오류를
    섞으면 게이트가 무엇을 잡았는지 알 수 없다."""
    bc, ac = Counter(_values(before)), Counter(_values(after))
    lost = list((bc - ac).elements())
    pool = list((ac - bc).elements())
    mismatch = 0
    reformatted = 0
    for l in lost:
        for i, g in enumerate(pool):
            if _looks_like_same_value(l, g):
                if _semantic_key(l) == _semantic_key(g):
                    reformatted += 1
                else:
                    mismatch += 1
                pool.pop(i)
                break
    kb = len(before.get("knowledge_items") or [])
    ka = len(after.get("knowledge_items") or [])
    ratio = round(ka / kb, 3) if kb else 1.0
    warn_delta = _warn_count(after) - _warn_count(before)
    return {
        "value_mismatch": mismatch,
        "values_reformatted": reformatted,
        "values_before": len(list(bc.elements())), "values_after": len(list(ac.elements())),
        "values_lost": len(lost) - mismatch - reformatted,
        "knowledge_before": kb, "knowledge_after": ka, "knowledge_ratio": ratio,
        "warn_delta": warn_delta,
        "passed": mismatch == 0 and ratio >= KNOWLEDGE_FLOOR and warn_delta <= WARN_DELTA_MAX,
    }


def main() -> int:
    _utf8_stdout()
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
    print(f"서식 차이    {r['values_reformatted']}건  (참고용, 게이트 아님)")
    print(f"값 소실      {r['values_lost']}건  (참고용, 게이트 아님)")
    print(f"지식 항목    {r['knowledge_before']} → {r['knowledge_after']}  "
          f"유지율 {r['knowledge_ratio']:.0%}  (게이트: {KNOWLEDGE_FLOOR:.0%})")
    print(f"⚠️ 증감      {r['warn_delta']:+}건  (게이트: +{WARN_DELTA_MAX} 이내)")
    print("PASS" if r["passed"] else "FAIL")
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
