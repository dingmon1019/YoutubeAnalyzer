#!/usr/bin/env python
"""evidence.json에 의도적 판독 오류를 주입한다 (감사 검출력 측정용).

라운드5 스펙 §3.2. R2의 주입 오류 시험과 같은 방법이다.
표본 감사가 뽑을 상위 항목(command/setting)과 뽑지 않을 하위 항목(example/concept)에
절반씩 넣어, "표본 밖 오류는 애초에 못 잡는다"는 가설을 함께 검증한다.

사용:
    python docs/eval/inject-errors.py --src evidence.json --out injected.json --n 6
"""
import argparse
import copy
import json
import random
import sys

HIGH = ("command", "setting", "action", "criterion")
LOW = ("example", "concept", "comparison", "result")


def _utf8_stdout() -> None:
    """cp949 콘솔에서 한글 출력이 UnicodeEncodeError로 죽는 것을 막는다.
    skills/tuto/scripts/common.py의 utf8_stdout과 같은 처리 — docs/eval 도구는
    모듈 독립성 때문에 common을 임포트하지 않고 최소 복제한다."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _corrupt(value: str, rnd: random.Random) -> str:
    """숫자 한 자리를 바꾸거나, 없으면 문자열 끝에 자리 하나를 덧붙인다."""
    digits = [i for i, c in enumerate(value) if c.isdigit()]
    if digits:
        i = rnd.choice(digits)
        new = str((int(value[i]) + 1) % 10)
        return value[:i] + new + value[i + 1:]
    return value + "0"


def inject(ev: dict, n: int = 6, seed: int = 0):
    """상위/하위 티어에 절반씩 오류를 주입하고 주입 기록을 반환한다."""
    rnd = random.Random(seed)
    ve_by_id = {v["id"]: v for v in ev.get("visual_evidence") or [] if isinstance(v, dict)}
    tiers = {"high": [], "low": []}
    for k in ev.get("knowledge_items") or []:
        t = k.get("type")
        refs = [e.get("ref") for e in (k.get("evidence") or [])
                if isinstance(e, dict) and e.get("source") == "frame"]
        refs = [r for r in refs if r in ve_by_id]
        if not refs:
            continue
        if t in HIGH:
            tiers["high"].append((k, refs[0]))
        elif t in LOW:
            tiers["low"].append((k, refs[0]))
    injected = []
    # n이 홀수면 상위 쪽에 나머지 1건을 준다 (n//2를 양쪽에 그대로 쓰면
    # 홀수 n에서 총 주입 건수가 n보다 1건 부족해진다).
    counts = {"high": (n + 1) // 2, "low": n // 2}
    for tier in ("high", "low"):
        pool = tiers[tier]
        rnd.shuffle(pool)
        for k, ref in pool[:counts[tier]]:
            ve = ve_by_id[ref]
            before = str(ve.get("value", ""))
            after = _corrupt(before, rnd)
            ve["value"] = after
            injected.append({"id": ref, "knowledge_id": k.get("id"), "tier": tier,
                             "before": before, "after": after})
    return ev, injected


def main() -> int:
    _utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    with open(a.src, encoding="utf-8") as f:
        ev = json.load(f)
    ev, injected = inject(copy.deepcopy(ev), a.n, a.seed)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(ev, f, ensure_ascii=False, indent=1)
    print(json.dumps(injected, ensure_ascii=False, indent=1), file=sys.stderr)
    print(f"injected {len(injected)} errors → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
