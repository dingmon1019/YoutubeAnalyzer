#!/usr/bin/env python
"""/tuto 실행 1건의 토큰 비용을 집계한다.

집계 규약 (yta-watch-benchmark 메모리의 "집계 방법론 철칙"과 동일):
- 세션 jsonl은 API 응답 1개를 콘텐츠 블록 수만큼 중복 기록한다. **message.id로 dedup 필수.**
  (과거 이 dedup을 빠뜨려 4배 과대계상한 사고가 있었다.)
- 실효 토큰(달러가중) = input + 2×cache_write + 0.1×cache_read + 5×output
- 본체(오케스트레이터)와 서브에이전트를 분리 집계한다. 본체가 총비용의 60~82%를
  차지하므로 서브에이전트만 세면 결론이 뒤집힌다.

사용:
    python docs/eval/measure-cost.py --marker KEidtrzVQJk
    python docs/eval/measure-cost.py --marker KEidtrzVQJk --session <session-id>
    python docs/eval/measure-cost.py --list

--marker는 사용자 발화에 등장하는 문자열(보통 video_id)이다. 그 발화 시점부터
--until(또는 파일 끝)까지를 1건의 실행으로 본다.

⚠️ **구간 끝을 지정하지 않으면 실행 이후의 모든 작업이 함께 집계된다.** 같은 세션에서
분석·회고·편집을 이어 했다면 그게 전부 /tuto 비용으로 잡힌다(실측: 3편이 사후 작업 때문에
3,388,990 → 4,070,666으로 부풀었다). 깨끗한 수치를 원하면 **새 세션에서 /tuto만 돌리거나**,
--until로 실행 종료 시점을 지정하라.

⚠️ **버전 간 비용 비교는 구간 규약을 양쪽에 똑같이 적용해야 한다.** 실측(2026-08-12):
"총비용 -27%"라고 기록돼 있던 값은 신버전은 실행 구간만, 구버전은 그보다 넓은 구간으로
잰 비교였다. 양쪽을 실행 구간으로 맞춰 다시 재니 **-11.3%**였다. 또한 `cache_read`는
파이프라인이 아니라 **그 실행 앞에 대화가 얼마나 쌓였는지**에 비례하므로, 세션 후반에 돌린
쪽이 불리하다 — 같은 t1 영상에서 콜당 165,722 → 450,680으로 2.7배가 됐다. 총비용만 보면
개선이 세션 위치에 먹힌다. **개선의 크기는 cache_write로 보고, 총비용은 참고로 본다.**
"""
import argparse, glob, json, os, sys, datetime

PROJECTS = os.path.expanduser("~/.claude/projects")


def eff(u):
    return (u.get("input_tokens", 0)
            + 2 * u.get("cache_creation_input_tokens", 0)
            + 0.1 * u.get("cache_read_input_tokens", 0)
            + 5 * u.get("output_tokens", 0))


def scan(path, lo=None, hi=None):
    """dedup 후 실효 토큰과 구성요소를 반환."""
    seen = set()
    agg = {"in": 0, "cw": 0, "cr": 0, "out": 0}
    calls = 0
    try:
        f = open(path, encoding="utf-8")
    except OSError:
        return 0.0, 0, agg
    with f:
        for line in f:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            ts = o.get("timestamp", "")
            if lo and ts < lo:
                continue
            if hi and ts >= hi:
                continue
            m = o.get("message") or {}
            u = m.get("usage")
            mid = m.get("id")
            if not (u and mid) or mid in seen:
                continue
            seen.add(mid)
            calls += 1
            for k, field in (("in", "input_tokens"), ("cw", "cache_creation_input_tokens"),
                             ("cr", "cache_read_input_tokens"), ("out", "output_tokens")):
                agg[k] += u.get(field, 0)
    total = agg["in"] + 2 * agg["cw"] + 0.1 * agg["cr"] + 5 * agg["out"]
    return total, calls, agg


def user_marks(session_path, marker):
    """마커가 등장하는 사용자 발화의 타임스탬프를 순서대로 반환."""
    out = []
    with open(session_path, encoding="utf-8") as f:
        for line in f:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("type") != "user":
                continue
            c = (o.get("message") or {}).get("content")
            if isinstance(c, str) and marker in c:
                out.append(o.get("timestamp"))
    return out


def to_epoch(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marker", help="실행을 식별할 사용자 발화 내 문자열 (보통 video_id)")
    ap.add_argument("--since", help="구간 시작 ISO 타임스탬프 (--marker 대신 직접 지정)")
    ap.add_argument("--session", help="세션 id (생략 시 마커를 포함한 가장 최근 세션)")
    ap.add_argument("--project", default=None, help="프로젝트 디렉토리명 (생략 시 cwd에서 추론)")
    ap.add_argument("--until", help="구간 끝 ISO 타임스탬프 (생략 시 파일 끝 — 사후 작업이 함께 잡힌다)")
    ap.add_argument("--list", action="store_true", help="프로젝트의 세션 목록만 출력")
    args = ap.parse_args()

    proj = args.project
    if not proj:
        proj = os.path.abspath(os.getcwd()).replace(":", "-").replace(os.sep, "-").replace("/", "-")
    base = os.path.join(PROJECTS, proj)
    if not os.path.isdir(base):
        cands = [d for d in os.listdir(PROJECTS) if "YoutubeAnalayzer" in d]
        if not cands:
            sys.exit(f"프로젝트 디렉토리를 찾을 수 없다: {base}")
        base = os.path.join(PROJECTS, cands[0])

    sessions = sorted(glob.glob(os.path.join(base, "*.jsonl")), key=os.path.getmtime, reverse=True)
    if args.list:
        for s in sessions:
            mt = datetime.datetime.fromtimestamp(os.path.getmtime(s))
            print(f"{os.path.basename(s)[:-6]}  {os.path.getsize(s)/1e6:8.1f}MB  {mt:%Y-%m-%d %H:%M}")
        return
    if not args.marker and not args.since:
        sys.exit("--marker, --since, --list 중 하나가 필요하다")

    target = None
    if args.session:
        target = os.path.join(base, args.session + ".jsonl")
    elif args.marker:
        for s in sessions:
            if user_marks(s, args.marker):
                target = s
                break
    else:
        target = sessions[0]
    if not target or not os.path.exists(target):
        sys.exit(f"세션을 찾지 못했다 (marker={args.marker}, session={args.session})")

    sid = os.path.basename(target)[:-6]
    if args.since:
        lo = args.since
        marks = [lo]
    else:
        marks = user_marks(target, args.marker)
        lo = marks[0]
    hi = args.until

    main_eff, calls, a = scan(target, lo, hi)
    print(f"세션: {sid}")
    print(f"실행 시작: {lo}   (구간 시작)")
    if hi:
        print(f"실행 종료: {hi}")
    else:
        print("실행 종료: (파일 끝)  ⚠️ 실행 이후 같은 세션에서 한 작업이 함께 집계된다")
    print()
    print(f"{'본체(오케스트레이터)':<24}{main_eff:>12,.0f}  ({calls}콜)")
    print(f"{'  ├ input':<24}{a['in']:>12,}")
    print(f"{'  ├ cache_write ×2':<24}{2*a['cw']:>12,.0f}   (raw {a['cw']:,})")
    print(f"{'  ├ cache_read ×0.1':<24}{0.1*a['cr']:>12,.0f}   (raw {a['cr']:,}, 콜당 {a['cr']/max(calls,1):,.0f})")
    print(f"{'  └ output ×5':<24}{5*a['out']:>12,.0f}   (raw {a['out']:,})")

    # 서브에이전트도 **본체와 같은 [lo, hi) 구간으로** 자른다.
    # 과거엔 mtime >= lo로 파일을 고른 뒤 파일 전체를 셌다. 그 방식은 측정 시점에만
    # 우연히 맞는다 — 그 구간 이후에 서브에이전트가 더 돌면 소급 측정이 그걸 전부
    # 끌어온다. 실측(2026-08-12): t1 구간을 나중에 다시 재니 서브에이전트가 46건으로
    # 잡혔다(실제 8건). 종료 시각을 줘도 서브에이전트에는 적용되지 않던 게 원인이다.
    # 서브에이전트 jsonl도 timestamp를 갖고 있으므로 그대로 구간 필터를 건다.
    sub_total = 0.0
    rows = []
    for p in glob.glob(os.path.join(base, sid, "subagents", "*.jsonl")):
        s, n, _ = scan(p, lo, hi)
        if s > 0:
            rows.append((os.path.basename(p)[6:23], s, n))
            sub_total += s
    rows.sort(key=lambda r: -r[1])
    print()
    print(f"서브에이전트 {len(rows)}건")
    for name, s, n in rows:
        print(f"  {name:<24}{s:>12,.0f}  ({n}콜)")

    total = main_eff + sub_total
    print()
    print("=" * 44)
    print(f"{'총계':<24}{total:>12,.0f}")
    if total:
        print(f"{'본체 비중':<24}{main_eff/total*100:>11.1f}%")
    print()
    print("기준선 — v0.1.3 풀 파이프라인, 실행 구간만 (2026-08-12 재측정):")
    print("  PlMpk 5:52·33장  02-10 02:40:09~03:06:30  6,325,853  (본체 81.8%)")
    print("  t1-XA 19:21·41장 08-10 16:27:15~17:00:00  2,821,675  (본체 38.4%)")
    print("  KEidt 7:51·33장  08-11 01:38:41~02:05:00  2,733,694  (본체 51.1%)")
    print("  v0.1.5 t1-XA     08-11 07:34:17~08:01:00  2,503,395  (본체 33.3%)  → v0.1.3 대비 -11.3%")
    print()
    print("  ⚠️ 예전에 t1 3,347,826 / KEidt 3,388,990으로 기록돼 있었다. 서브에이전트 몫은")
    print("     정확히 재현되지만 본체 몫이 재현되지 않는다(콜 수 28→33, 27→30). 종료 시각을")
    print("     실행 끝에 맞춘 위 수치가 재현 가능한 값이다. README의 '총비용 -27%'는 그 옛")
    print("     기준선에 기댄 값이라 -11%로 정정했다.")


if __name__ == "__main__":
    main()
