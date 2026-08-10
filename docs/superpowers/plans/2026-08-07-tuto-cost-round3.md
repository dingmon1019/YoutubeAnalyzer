# tuto 비용절감 라운드 3 구현 계획 (본체 티어링)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 가이드 빌더를 Sonnet Agent로 위임(하이브리드 티어링)해 분석 1회 비용 104만→≤70만(목표 ~45만) — 품질 비저하는 G3 게이트가 심판, 미달 시 즉시 철회.

**Architecture:** 코드 변경은 zoom.py 소품질 3건뿐. 티어링은 SKILL.md §4의 절차 개정(오케스트레이터=세션 모델이 판정·감사·응답, 빌더=Sonnet이 프레임 판독·가이드 작성). 스펙: `docs/superpowers/specs/2026-08-07-tuto-cost-round3-design.md`.

**Tech Stack:** Python 표준 라이브러리, pytest, Agent 위임(model: "sonnet").

## Global Constraints

- Windows 11, `python` 명령, 테스트 `python -m pytest tests -q` (기준선 98 passed).
- 절대 조건: G3 게이트 — 값 전량 동일·감사 통과·비용 ≤700,000(달러가중, message.id dedup)·서사 육안 기록. 미달 시 SKILL.md §4 원복 + 실측 스펙 추기.
- 커밋: `fix:`/`feat:`/`docs:` 한국어 한 줄 + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- 기존 테스트·독스트링 무수정(append-only), fail-loud.
- 벤치마크 캐시: `C:\Users\hwangjs\.yta\cache\zP3i_7xZW7Q\` (guide-baseline.md가 값 대조 기준).

---

### Task 1: zoom.py 소품질 3건 (스펙 T3)

**Files:**
- Modify: `skills/tuto/scripts/zoom.py` (crop 분기)
- Test: `tests/test_zoom.py` (추가)

**Interfaces:**
- Consumes: 기존 `_CROP_SPEC`·crop 분기 (라운드2 산출)
- Produces: CLI 계약 추가 — 스펙 >5건 ERROR exit 1 / ffmpeg 실패 시 평문 ERROR+부분 파일 삭제+exit 1 / 동시 플래그 시 stderr NOTE 후 crop만

- [ ] **Step 1: 실패하는 테스트 3개 작성** — `tests/test_zoom.py` 말미:

```python
def test_crop_mode_caps_at_five_specs(tmp_path, monkeypatch, capsys):
    """SKILL.md의 '영상당 크롭 ≤5회' 산문 상한을 코드로 배선 — 6건 이상이면 fail-loud."""
    cd = tmp_path / "abc12345678"
    (cd / "frames").mkdir(parents=True)
    specs = ",".join(f"f{i}.jpg@0,0,10,10" for i in range(6))
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.sys, "argv", ["zoom.py", "abc12345678", "--crop", specs])
    assert zoom.main() == 1
    assert "ERROR" in capsys.readouterr().err


def test_crop_mode_ffmpeg_failure_fails_loud_and_removes_partial(synth_clip, tmp_path, monkeypatch, capsys):
    """크롭 ffmpeg 실패는 traceback이 아니라 평문 ERROR — 부분 파일도 남기지 않는다."""
    cd = tmp_path / "abc12345678"
    (cd / "frames").mkdir(parents=True)
    src = cd / "frames" / "t0001_512.jpg"
    subprocess.run(["ffmpeg", "-y", "-ss", "1", "-i", str(synth_clip),
                    "-frames:v", "1", "-vf", "scale=512:-2", str(src)],
                   capture_output=True, check=True)

    def boom(cmd, timeout=600):
        dst = Path(str(cmd[-1]))
        dst.write_bytes(b"partial")          # ffmpeg가 부분 파일을 남긴 상황 재현
        raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(zoom.common, "run", boom)
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.sys, "argv",
                        ["zoom.py", "abc12345678", "--crop", "t0001_512.jpg@0,0,10,10"])
    assert zoom.main() == 1
    assert "ERROR" in capsys.readouterr().err
    assert not (cd / "frames" / "t0001_512c0_0_10_10.jpg").exists()


def test_crop_with_ranges_prints_note(synth_clip, tmp_path, monkeypatch, capsys):
    """--crop과 --ranges 동시 지정은 무언 무시 대신 stderr NOTE — fail-loud 관례."""
    cd = tmp_path / "abc12345678"
    (cd / "frames").mkdir(parents=True)
    src = cd / "frames" / "t0001_512.jpg"
    subprocess.run(["ffmpeg", "-y", "-ss", "1", "-i", str(synth_clip),
                    "-frames:v", "1", "-vf", "scale=512:-2", str(src)],
                   capture_output=True, check=True)
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.sys, "argv",
                        ["zoom.py", "abc12345678", "--crop", "t0001_512.jpg@0,0,50,50",
                         "--ranges", "0:01-0:05"])
    assert zoom.main() == 0
    err = capsys.readouterr().err
    assert "NOTE" in err and "--crop" in err
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/test_zoom.py -q` / Expected: 신규 3개 FAIL

- [ ] **Step 3: 구현** — `zoom.py` crop 분기 수정:

```python
    if args.crop:
        if args.ranges or args.timestamps:
            print("NOTE: --crop 지정 시 --ranges/--timestamps는 무시됩니다", file=sys.stderr)
        specs = _CROP_SPEC.findall(args.crop)
        leftover = _CROP_SPEC.sub("", args.crop).strip(",").strip()
        if not specs or leftover:
            print(f"ERROR: --crop 형식 오류: {args.crop!r} "
                  f"(형식: 파일명@x,y,w,h[,파일명@x,y,w,h...])", file=sys.stderr)
            return 1
        if len(specs) > 5:
            print(f"ERROR: --crop 스펙 {len(specs)}건 — 영상당 5회 이내로 제한"
                  f" (SKILL.md 검증 규칙)", file=sys.stderr)
            return 1
        out_paths = []
        for name, x, y, w, h in specs:
            src = cd / "frames" / name
            if not src.exists():
                print(f"ERROR: 크롭 원본 없음: {src}", file=sys.stderr)
                return 1
            dst = src.with_name(f"{src.stem}c{x}_{y}_{w}_{h}.jpg")
            if not dst.exists():
                try:
                    common.run(["ffmpeg", "-y", "-i", src, "-vf",
                                f"crop={w}:{h}:{x}:{y}", "-q:v", "3", dst])
                except RuntimeError as e:
                    dst.unlink(missing_ok=True)      # 부분 파일 영구 재사용 방지
                    print(f"ERROR: 크롭 실패: {name} — {e}", file=sys.stderr)
                    return 1
            out_paths.append(dst)
        print(f"zoom: {len(out_paths)} cropped")
        frames.report(out_paths)
        return 0
```

(기존 분기와의 차이: NOTE 선두 추가, 5건 캡, try/except+unlink. 나머지 동일 유지.)

- [ ] **Step 4: 전체 테스트 + 커밋**

Run: `python -m pytest tests -q` / Expected: 98 + 3 = 101 passed

```bash
git add skills/tuto/scripts/zoom.py tests/test_zoom.py
git commit -m "fix: zoom --crop 코드 캡·부분파일 방어·동시 플래그 NOTE — 라운드2 이연분"
```

---

### Task 2: SKILL.md §4 가이드 빌더 위임 (스펙 T1)

**Files:**
- Modify: `skills/tuto/SKILL.md` §4

**Interfaces:**
- Consumes: Task 1의 crop 캡(빌더 지시문이 참조)
- Produces: 절차 계약 — Task 3의 G3 E2E가 이 절차문 그대로 수행

- [ ] **Step 1: §4 서두 개정** — 현재 §4("## 4. 가이드 초안 → 검증 패스")의 서두 문장
  "`<cache_dir>/guide.md`를 작성한다. 형식:" 을 다음 블록으로 교체한다
  (형식 목록과 검증 규칙 3개는 그대로 유지 — 빌더 프롬프트에 전문 인용된다):

> 가이드 작성은 **`model: "sonnet"` Agent(가이드 빌더)에 위임**한다 (비용 티어링 — 스펙
> R3 T1. 값 판독력은 감사 실측으로 검증된 티어이며, 품질은 §5 감사와 값 대조가 심판한다).
> 빌더 프롬프트에 다음을 담는다:
> - 캐시 디렉토리 경로와 **kept FRAME 경로 전부**(지도+확대), analyze 보고서 저장 파일
>   경로(오케스트레이터가 패스1 출력을 파일로 저장해 두고 경로를 넘긴다 — 자막·챕터·
>   DESC_TIMESTAMPS가 빌더의 텍스트 증거다)
> - 아래 "형식" 목록과 "검증 규칙" 3개의 **전문**
> - 재확대 수단: `python "<SKILL_DIR>/scripts/zoom.py" <id> --crop "<프레임>@x,y,w,h"`
>   (호출당 5건 이내 — 코드 캡 있음)
> - 산출 계약: `<cache_dir>/guide.md` 작성(감사 스탬프 자리는 "(표본 감사 후 기입)") 후
>   **최종 응답으로 §5 규칙에 맞는 표본 주장 후보 6건**(서식·상태 변화 ≥1건, 해당 범주
>   부재 시 "서식변화 주장 없음" 명시)을 주장 1문장+근거 프레임 절대경로로 반환
>
> 빌더가 산출 계약을 위반하면(guide.md 미생성·섹션 누락·후보 미반환) **1회 재지시**하고,
> 재실패 시 오케스트레이터가 직접 작성한다(위임 철회 — 감사 스탬프에 명시).
> 오케스트레이터는 빌더 완료 후 guide.md의 형식(헤더·요약·스텝·스탬프 자리)을 확인하고
> §5 감사로 진행한다. 감사 MISMATCH의 가이드 교정은 오케스트레이터가 수행한다.
>
> `<cache_dir>/guide.md` 형식:

- [ ] **Step 2: 정합 확인 (L1)** — "빌더", "sonnet", "표본" 검색으로 §5(표본 뽑기 주체가
  빌더 후보를 받아 오케스트레이터가 감사 파견하는 흐름), §7(응답 주체=오케스트레이터)과
  모순 없는지 확인. §5 첫 문장 "…중 6개를 뽑되"는 "빌더가 반환한 후보 6건을 사용하되,
  후보가 §5 규칙에 어긋나면 오케스트레이터가 직접 재표집한다"로 교체.

- [ ] **Step 3: 커밋**

```bash
git add skills/tuto/SKILL.md
git commit -m "feat: SKILL.md §4 가이드 빌더 sonnet 위임 — 하이브리드 티어링 (스펙 R3 T1)"
```

---

### Task 3: G3 게이트 E2E 실측 (스펙 T2 — 실행 태스크, 컨트롤러 수행)

**Files:** 코드 없음. 결과는 렛저·스펙 추기.

- [ ] **Step 1: 콜드 준비** — `rm -rf "C:\Users\hwangjs\.yta\cache\zP3i_7xZW7Q\frames"` 후
  analyze 실행, 출력 전문을 파일로 저장(빌더 입력용), zoom 동일 플랜(라운드1·2와 같은
  ranges 문자열) 실행, FRAME 35장 집합 md5가 기준선과 동일한지 확인.
- [ ] **Step 2: 빌더 파견** — Task 2의 §4 절차 그대로 `model: "sonnet"` Agent에 위임
  (프레임 54장 경로+보고서 파일+형식·검증 규칙 전문+산출 계약). 완료 후 guide.md 형식 확인.
- [ ] **Step 3: 값 대조** — 빌더 guide.md의 `(t=)` 인용 값 전부를 guide-baseline.md와 대조
  (별도 대조 에이전트 또는 오케스트레이터). **하나라도 다르면 즉시 G3 실패 → Step 6 철회.**
- [ ] **Step 4: 감사** — 빌더가 반환한 후보 6건으로 가치 감사(Sonnet+크롭, MISMATCH는
  세션 모델 재검) + 커버리지 감사 1건. 교정 발생 시 오케스트레이터가 가이드 수정. 스탬프 기입.
- [ ] **Step 5: 비용·서사** — 빌더+감사 에이전트들의 달러가중 실효 토큰 합산(sonnet 1/5)
  ≤ 700,000 확인. 빌더 가이드 vs 기준선 가이드 구조·요약 육안 비교 1회 기록(명백한 퇴행
  여부).
- [ ] **Step 6: 판정** — 4항 전부 통과 시 채택 확정·렛저 기록. 미달 시: Task 2 커밋 revert
  + 스펙 §T2에 실측치 추기 커밋 + fail-loud 보고 (G2 선례).

---

### Task 4: 릴리스 v0.1.3 + 메모리

**Files:**
- Modify: `.claude-plugin/plugin.json:3` (`"0.1.2"` → `"0.1.3"`)
- Modify: 메모리 `yta-watch-benchmark.md`(라운드3 실측), `yta-post-merge-followups.md`(상태)

- [ ] **Step 1: 게이트 확인** — Task 3 판정 + `python -m pytest tests -q` 최종 PASS.
- [ ] **Step 2: 범프 커밋** — `chore: v0.1.3 — 비용절감 라운드3 (가이드 빌더 sonnet 티어링)`
  (G3 실패로 철회됐다면 버전 범프는 zoom 소품질만 반영하는 메시지로 조정).
- [ ] **Step 3: 플러그인 갱신** — `claude plugin update tuto@yta`.
- [ ] **Step 4: 메모리 갱신** — 실측치(성공/철회 불문)와 다음 라운드 후보 정리.

---

## Self-Review 결과

- 스펙 커버리지: T1→Task 2, T2→Task 3, T3→Task 1, 게이트→Task 3·4. 누락 없음.
- 플레이스홀더 없음 — 테스트·구현·§4 대체 문구 전문 수록.
- 타입 일관성: crop 분기 코드가 라운드2 최종형(_CROP_SPEC·leftover 검사) 위에 증분으로
  정의됨. Task 3의 감사 절차는 라운드2 확정 프로토콜을 참조(변경 없음).
