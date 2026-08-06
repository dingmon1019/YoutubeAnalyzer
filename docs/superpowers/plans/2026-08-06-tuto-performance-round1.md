# tuto 성능개선 라운드 1 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tuto 분석 1회의 달러 등가 실효 토큰 176만→100만 이하, 시간 17.3분→12분 이하 — 산출물 품질 저하 0을 절대 조건으로.

**Architecture:** 파이프라인 구조는 불변. 레버 5개만 정확히 수정한다 — ① 감사 서브에이전트를 Haiku+상위모델 재검으로(SKILL.md), ② stdout UTF-8 강제(common), ③ ffmpeg 프레임 추출 병렬화(frames), ④ 핀포인트 모드 dedup 스킵(zoom), ⑤ signals.json 재사용(analyze). 스펙: `docs/superpowers/specs/2026-08-06-tuto-performance-round1-design.md`.

**Tech Stack:** Python 3 표준 라이브러리만(concurrent.futures 추가), ffmpeg/ffprobe/yt-dlp 외부 바이너리, pytest.

## Global Constraints

- 플랫폼: Windows 11 / PowerShell. 파이썬 명령은 **`python`** (python3 금지 — MS Store 스텁).
- 테스트 실행: 저장소 루트 `D:\Repository\YoutubeAnalayzer`에서 `python -m pytest tests -q`. 기준선 83개 통과, ffmpeg 없으면 synth_clip 테스트는 skip된다.
- 커밋: 저장소 컨벤션 `fix:`/`feat:`/`docs:` + 한국어 한 줄 요약. 모든 커밋 말미에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- 스크립트 간 의존 금지: scripts/*.py는 `common`만 공유한다 (zoom.py의 `_probe_duration` 로컬 복제가 선례). 새 의존을 만들지 말 것.
- 외부 패키지 추가 금지 — 표준 라이브러리만.
- fail-loud: 실패·미달을 조용히 낮추지 않는다. 게이트 미달은 보고 후 중단.
- **품질 절대 조건**: Task 6·7 게이트 통과 전에는 "완료" 선언 금지.
- 벤치마크 캐시: `C:\Users\hwangjs\.yta\cache\zP3i_7xZW7Q\` (video.mp4·subs·info.json·signals.json·guide.md 존재 전제. video.mp4가 LRU로 지워졌으면 Task 7 첫 단계의 analyze 실행이 재다운로드한다).

---

### Task 1: common.utf8_stdout() + main 6개 적용 (스펙 D2)

**Files:**
- Modify: `skills/tuto/scripts/common.py` (import sys 추가 + 함수 추가)
- Modify: `skills/tuto/scripts/analyze.py:261-262`, `zoom.py:118-119`, `transcribe.py:283-284` (기존 부분 가드 교체), `frames.py:90`, `signals.py:131`, `setup.py:49` (가드 신설)
- Test: `tests/test_common.py` (추가)

**Interfaces:**
- Consumes: 없음
- Produces: `common.utf8_stdout() -> None` — 이후 모든 태스크의 스크립트 실행 출력이 UTF-8임을 전제할 수 있다.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_common.py` 말미에 추가:

```python
def test_utf8_stdout_forces_utf8_on_pipe():
    """Windows 파이프에서 stdout이 로케일(cp949)로 인코딩되던 결함의 회귀 테스트 —
    PYTHONUTF8/PYTHONIOENCODING 없이 서브프로세스로 실행해 실제 파이프 환경을 재현한다."""
    import os
    import subprocess
    scripts = Path(__file__).parent.parent / "skills" / "tuto" / "scripts"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    code = (
        f"import sys; sys.path.insert(0, r'{scripts}'); "
        "import common; common.utf8_stdout(); print('한\u2014글')"
    )
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env)
    assert p.returncode == 0, p.stderr
    assert p.stdout.decode("utf-8").strip() == "한\u2014글"


def test_utf8_stdout_ignores_streams_without_reconfigure(monkeypatch):
    """capsys/StringIO처럼 reconfigure가 없는 스트림에서도 예외 없이 통과해야 한다."""
    import io
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    common.utf8_stdout()
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_common.py -q`
Expected: FAIL — `AttributeError: module 'common' has no attribute 'utf8_stdout'`

- [ ] **Step 3: 구현** — `common.py` import 블록에 `import sys` 추가, 파일 말미에:

```python
def utf8_stdout() -> None:
    """stdout/stderr를 UTF-8로 강제한다. Windows에서 파이프로 실행되면 기본 인코딩이
    로케일(cp949)이라 한글·em-dash가 깨진 바이트로 나간다 — errors만 바꾸는 것으로는
    부족하고(과거 결함) encoding까지 지정해야 한다. reconfigure 미지원 스트림(테스트
    캡처 등)은 조용히 무시한다."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
```

- [ ] **Step 4: main 6개 적용** — 각 파일에서:
  - `analyze.py` main 첫 두 줄(`if hasattr(...): sys.stdout.reconfigure(errors="replace")` + 주석)을 `common.utf8_stdout()` 한 줄로 교체
  - `zoom.py` main 첫 두 줄 동일 교체
  - `transcribe.py` main 첫 두 줄 동일 교체
  - `frames.py`·`signals.py`·`setup.py` main의 `ap = argparse.ArgumentParser()` 바로 앞에 `common.utf8_stdout()` 삽입 (세 파일 모두 `import common` 이미 있음)

- [ ] **Step 5: 전체 테스트 통과 확인**

Run: `python -m pytest tests -q`
Expected: 기존 83 + 신규 2 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add skills/tuto/scripts tests/test_common.py
git commit -m "fix: stdout UTF-8 강제 — cp949 파이프 깨짐 근본 수정 (main 6개 일괄)"
```

---

### Task 2: 핀포인트(--timestamps) dedup 스킵 (스펙 D4)

**Files:**
- Modify: `skills/tuto/scripts/zoom.py` main (현행 144-150행 부근 추출 루프)
- Test: `tests/test_zoom.py` (추가)

**Interfaces:**
- Consumes: `frames.extract_frames(video, ts, res, out_dir) -> list[Path]`, `frames.dedup_frames(paths) -> (list, int)` (기존 시그니처 그대로)
- Produces: 동작 계약 — `--timestamps` 모드 출력은 항상 `N kept, 0 dup-dropped`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_zoom.py` 말미에 추가:

```python
def test_timestamps_mode_skips_dedup(synth_clip, tmp_path, monkeypatch, capsys):
    """파킹 1순위 결함의 회귀 테스트: 핀포인트(--timestamps)는 명시 요청 시점이므로
    시각적 근접중복이라도 드롭하면 안 된다 — 1s/2s/3s(전부 파랑 정지)를 요청해도
    3장 모두 유지돼야 한다. (--ranges 모드의 dedup은 test_dedup_drops_static이 보증)"""
    cd = tmp_path / "abc12345678"
    cd.mkdir()
    (cd / "video.mp4").write_bytes(synth_clip.read_bytes())
    monkeypatch.setattr(zoom.common, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(zoom.sys, "argv", ["zoom.py", "abc12345678", "--timestamps", "0:01,0:02,0:03"])

    code = zoom.main()

    out = capsys.readouterr().out
    assert code == 0
    assert "3 kept, 0 dup-dropped" in out
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_zoom.py::test_timestamps_mode_skips_dedup -v`
Expected: FAIL — 현행은 dedup이 정지화면 2장을 드롭해 "1 kept, 2 dup-dropped"

- [ ] **Step 3: 구현** — `zoom.py` main의 추출 루프를 다음으로 교체:

```python
    kept_all, dropped_all, failed_all = [], 0, 0
    pinpoint = bool(args.timestamps)
    for res, ts in sorted(by_res.items()):
        raw = frames.extract_frames(video, ts, res, cd / "frames")
        failed_all += len(ts) - len(raw)
        if pinpoint:
            kept, dropped = raw, 0    # 핀포인트는 명시 요청 시점 — 전량 반환 (스펙 D4)
        else:
            kept, dropped = frames.dedup_frames(raw)
        kept_all.extend(kept)
        dropped_all += dropped
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_zoom.py -q`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add skills/tuto/scripts/zoom.py tests/test_zoom.py
git commit -m "fix: zoom --timestamps 모드는 dedup 건너뜀 — 핀포인트 값 판독 프레임 드롭 결함"
```

---

### Task 3: ffmpeg 프레임 추출·썸네일 병렬화 (스펙 D3)

**Files:**
- Modify: `skills/tuto/scripts/frames.py` (`extract_frames`, `dedup_frames`)
- Test: `tests/test_frames.py` (추가)

**Interfaces:**
- Consumes: `common.run(cmd, timeout)` (기존)
- Produces: `extract_frames`/`dedup_frames` 시그니처·반환 불변. **불변식: 산출 파일 집합·리스트 순서·dedup 결과가 직렬 실행과 동일** (호출부 analyze/zoom 수정 불필요)

- [ ] **Step 1: 실패하는(=불변식 고정) 테스트 작성** — `tests/test_frames.py` 말미에 추가:

```python
def test_extract_frames_parallel_preserves_input_order(synth_clip, tmp_path):
    """병렬화 불변식: 반환 리스트는 입력 타임스탬프 순서를 그대로 따라야 한다
    (dedup_frames의 ref 체인 비교가 순서에 의존한다)."""
    ts = [1.0, 2.0, 3.0, 5.5, 8.0, 9.0]
    out = frames.extract_frames(synth_clip, ts, 512, tmp_path)
    assert [p.name for p in out] == [
        "t0001_512.jpg", "t0002_512.jpg", "t0003_512.jpg",
        "t0005d5_512.jpg", "t0008_512.jpg", "t0009_512.jpg",
    ]


def test_extract_frames_duplicate_timestamp_listed_twice_extracted_once(synth_clip, tmp_path):
    """직렬 시절 의미 보존: 같은 타임스탬프가 두 번 오면 결과 리스트에도 두 번 나타난다.
    병렬화 후에는 같은 출력 파일에 두 워커가 동시에 쓰지 않도록 추출 자체는 1회여야
    한다 (파일 파손 방지) — 결과 리스트 의미는 그대로."""
    out = frames.extract_frames(synth_clip, [1.0, 1.0], 512, tmp_path)
    assert [p.name for p in out] == ["t0001_512.jpg", "t0001_512.jpg"]
```

- [ ] **Step 2: 현행 기준 통과 확인 (회귀 앵커)**

Run: `python -m pytest tests/test_frames.py -q`
Expected: 전부 PASS (직렬 구현도 이 불변식을 만족한다 — 병렬화가 깨뜨리지 않음을 보증하는 앵커)

- [ ] **Step 3: 구현** — `frames.py`: import 블록에 `import os`와 `from concurrent.futures import ThreadPoolExecutor` 추가, `extract_frames`를 다음으로 교체:

```python
MAX_WORKERS = max(1, min(8, (os.cpu_count() or 4) - 1))


def _extract_one(video, t: float, res: int, out_dir: Path):
    p = out_dir / f"{_frame_tag(t)}_{res}.jpg"
    if not p.exists():
        try:
            common.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", video,
                        "-frames:v", "1", "-vf", f"scale={res}:-2", "-q:v", "3", p])
        except RuntimeError:
            # 범위 밖 타임스탬프 등으로 이 한 장이 실패해도 배치 전체를 죽이지 않는다
            return None
    return p if p.exists() else None


def extract_frames(video, timestamps: list, res: int, out_dir) -> list:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # 실측 5.5초/장 직렬이 zoom 5.5분의 원인 — ffmpeg 호출을 병렬화한다. 같은 타임스탬프
    # 중복은 한 번만 추출해(같은 출력 파일 동시 쓰기 방지) 결과 리스트에서 원래 순서·중복을
    # 복원한다. ex.map은 입력 순서를 보존하므로 산출은 직렬과 결정적으로 동일하다.
    unique = list(dict.fromkeys(timestamps))
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = dict(zip(unique, ex.map(
            lambda t: _extract_one(video, t, res, out_dir), unique)))
    return [results[t] for t in timestamps if results[t] is not None]
```

`dedup_frames` 서두에 썸네일 병렬 선계산 추가 (비교 로직은 그대로):

```python
def dedup_frames(paths: list, threshold: float = 2.0) -> tuple:
    if len(paths) > 1:
        # 프레임당 ffmpeg 썸네일도 직렬 병목 — 병렬로 _thumb_cache를 먼저 채운다.
        # 이후 순차 ref-체인 비교는 캐시 적중이라 순서·결과가 직렬과 동일하다.
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            list(ex.map(_thumb, paths))
    kept, ref = [], None
    for p in paths:
        t = _thumb(p)
        if len(t) < 256:
            kept.append(p)
            continue
        if ref is not None:
            diff = sum(abs(a - b) for a, b in zip(ref, t)) / 256
            if diff <= threshold:
                continue
        kept.append(p)
        ref = t
    return kept, len(paths) - len(kept)
```

- [ ] **Step 4: 전체 테스트 통과 + 체감 확인**

Run: `python -m pytest tests -q`
Expected: 전부 PASS. (test_thumb_cache_avoids_recomputation은 fake_run이 스레드에서 호출돼도 카운트 2 유지 — 경로 2개뿐이므로 결정적)

- [ ] **Step 5: 실제 속도 확인 (L3)** — 벤치마크 캐시에 video.mp4가 있으면:

```bash
python -c "import time,sys; sys.path.insert(0,'skills/tuto/scripts'); import frames; t0=time.time(); out=frames.extract_frames(r'C:\Users\hwangjs\.yta\cache\zP3i_7xZW7Q\video.mp4', [float(i*30) for i in range(1,21)], 512, r'C:\Users\hwangjs\AppData\Local\Temp\claude_frames_bench'); print(len(out), 'frames', round(time.time()-t0,1), 's')"
```

Expected: 20장이 직렬(~110초 추정) 대비 수 배 빠르게(<30초) 추출. 결과 출력에 실측치 기록.

- [ ] **Step 6: 커밋**

```bash
git add skills/tuto/scripts/frames.py tests/test_frames.py
git commit -m "feat: 프레임 추출·썸네일 ffmpeg 병렬화 — zoom 5.5분→1분 목표, 산출 결정성 불변"
```

---

### Task 4: signals.json 재사용 (스펙 D5)

**Files:**
- Modify: `skills/tuto/scripts/analyze.py` (`run_pass1`의 210-211행을 헬퍼 호출로, 헬퍼 신설)
- Test: `tests/test_analyze.py` (추가)

**Interfaces:**
- Consumes: `sig_mod.build_signals(info, vid, video_path) -> dict` (기존)
- Produces: `analyze._load_or_build_signals(cd: Path, info: dict, vid: str) -> dict` — sig dict(flags 포함) 반환. run_pass1의 STATUS 출력 계약 불변.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_analyze.py` 말미에 추가 (파일 상단의 sys.path 삽입·`import analyze`는 기존 그대로 사용):

```python
def test_signals_reused_when_fresh(tmp_path, monkeypatch):
    """signals.json이 video.mp4보다 새로우면 활동곡선(전체 영상 디코드) 재계산 없이
    재사용해야 한다 — 캐시 히트 재실행 102초의 원인 제거."""
    import os
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    sigf = tmp_path / "signals.json"
    sigf.write_text('{"activity": {"curve": [], "peaks": []}, "flags": ["reused"]}', encoding="utf-8")
    os.utime(video, (1000, 1000))
    os.utime(sigf, (2000, 2000))

    def boom(*a, **k):
        raise AssertionError("build_signals가 호출되면 안 된다")

    monkeypatch.setattr(analyze.sig_mod, "build_signals", boom)
    sig = analyze._load_or_build_signals(tmp_path, {}, "vid")
    assert sig["flags"] == ["reused"]


def test_signals_rebuilt_when_video_newer(tmp_path, monkeypatch):
    """video.mp4가 더 새로우면(eviction 후 재다운로드) 재계산하고 파일을 갱신해야 한다."""
    import json
    import os
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    sigf = tmp_path / "signals.json"
    sigf.write_text('{"activity": {"curve": [], "peaks": []}, "flags": ["stale"]}', encoding="utf-8")
    os.utime(sigf, (1000, 1000))
    os.utime(video, (2000, 2000))

    fresh = {"activity": {"curve": [], "peaks": []}, "flags": ["fresh"]}
    monkeypatch.setattr(analyze.sig_mod, "build_signals", lambda *a: fresh)
    sig = analyze._load_or_build_signals(tmp_path, {}, "vid")
    assert sig["flags"] == ["fresh"]
    assert json.loads(sigf.read_text(encoding="utf-8"))["flags"] == ["fresh"]


def test_signals_rebuilt_when_corrupt(tmp_path, monkeypatch):
    """mtime이 새로워도 파손·비정형 JSON이면 재계산한다."""
    import os
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    sigf = tmp_path / "signals.json"
    sigf.write_text("{broken", encoding="utf-8")
    os.utime(video, (1000, 1000))
    os.utime(sigf, (2000, 2000))

    fresh = {"activity": {"curve": [], "peaks": []}, "flags": []}
    monkeypatch.setattr(analyze.sig_mod, "build_signals", lambda *a: fresh)
    assert analyze._load_or_build_signals(tmp_path, {}, "vid") == fresh
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_analyze.py -q`
Expected: 신규 3개 FAIL — `_load_or_build_signals` 부재

- [ ] **Step 3: 구현** — `analyze.py`에 헬퍼 추가, `run_pass1`의 두 줄(`sig = sig_mod.build_signals(...)`, `(cd / "signals.json").write_text(...)`)을 `sig = _load_or_build_signals(cd, info, vid)` 한 줄로 교체:

```python
def _load_or_build_signals(cd: Path, info: dict, vid: str) -> dict:
    """signals.json이 video.mp4보다 새로우면 재사용한다 — build_signals의 활동곡선이
    전체 영상을 디코드해 캐시 히트 재실행도 ~100초를 쓰던 것을 없앤다(스펙 D5).
    eviction 후 재다운로드는 video.mp4 mtime이 새로워져 자동 무효화. 파손·비정형
    파일은 재계산한다."""
    sig_f = cd / "signals.json"
    video_f = cd / "video.mp4"
    if sig_f.exists() and video_f.exists() and sig_f.stat().st_mtime >= video_f.stat().st_mtime:
        try:
            sig = json.loads(sig_f.read_text(encoding="utf-8"))
            if isinstance(sig, dict) and "activity" in sig and "flags" in sig:
                return sig
        except (json.JSONDecodeError, OSError):
            pass
    sig = sig_mod.build_signals(info, vid, video_f)
    sig_f.write_text(json.dumps(sig, ensure_ascii=False, indent=1), encoding="utf-8")
    return sig
```

- [ ] **Step 4: 전체 테스트 통과 확인**

Run: `python -m pytest tests -q`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add skills/tuto/scripts/analyze.py tests/test_analyze.py
git commit -m "feat: analyze가 신선한 signals.json 재사용 — 캐시 히트 재실행 ~1.5분 단축"
```

---

### Task 5: SKILL.md 감사 에스컬레이션 (스펙 D1 문서)

**Files:**
- Modify: `skills/tuto/SKILL.md` §5 (표본 감사 절)

**Interfaces:**
- Consumes: 없음
- Produces: 감사 실행 계약 — Task 6·7이 이 절차문 그대로 감사를 수행한다.

- [ ] **Step 1: §5 본문 수정** — 아래 기존 문단을:

> 가이드의 검증형 주장(설정값·버튼명·순서) 중 무작위로 10개(10개 미만이면 전부)를 뽑는다.
> **가이드 본문은 주지 않고** 주장 하나와 근거 프레임만 독립된 Agent 서브에이전트에 보낸다:

다음으로 교체 (프롬프트 블록과 후속 문장은 유지):

> 가이드의 검증형 주장(설정값·버튼명·순서) 중 무작위로 10개(10개 미만이면 전부)를 뽑는다.
> **가이드 본문은 주지 않고** 주장 하나와 근거 프레임만 독립된 Agent 서브에이전트에 보낸다.
> 감사 에이전트는 **`model: "haiku"`로 실행**한다. 판정이 MATCH면 그대로 채택하고,
> **MISMATCH 또는 UNVERIFIABLE이면 그 주장만 기본(세션) 모델의 Agent로 같은 프롬프트를
> 재검**해 재검 결과를 최종 판정으로 삼는다 (비용 절감 레버 — 불확실성은 전부 상위
> 모델로 올라가므로 잔여 리스크는 오수용뿐이며, 이는 오류 주입 시험으로 게이트한다):

- [ ] **Step 2: 스탬프 형식 교체** — 기존:

`📋 표본 감사: 10개 주장 중 9 일치, 1 수정 — 추정 오류율 ~10% (검증 범위: 설정값·버튼명·순서)`

를 다음으로 교체:

`📋 표본 감사: 10개 주장 중 9 일치, 1 수정 — Haiku 10건 판정 + 상위 모델 재검 1건, 추정 오류율 ~10% (검증 범위: 설정값·버튼명·순서)`

- [ ] **Step 3: 정합 확인 (L1)** — SKILL.md에서 "감사"로 검색해 §5 외 참조 문구(예: §4 말미, 실패 시 절)가 새 계약과 모순되지 않는지 읽어서 확인.

- [ ] **Step 4: 커밋**

```bash
git add skills/tuto/SKILL.md
git commit -m "feat: 표본 감사를 Haiku + 상위 모델 재검 에스컬레이션으로 (스펙 D1)"
```

---

### Task 6: 감사 오류 주입 시험 — D1 채택 게이트 (스펙 §5.2)

**Files:** 코드 없음 — 실행 세션에서 Agent 도구로 수행. 결과는 계획 체크박스와 최종 보고에 기록.

**Interfaces:**
- Consumes: Task 5의 감사 절차, 벤치마크 프레임 (`C:\Users\hwangjs\.yta\cache\zP3i_7xZW7Q\frames\`)
- Produces: D1 채택/폴백 판정 (Task 7 감사 방식 결정)

- [ ] **Step 1: 원본 주장 3건을 `model: haiku` Agent로 감사** — 프롬프트는 SKILL.md §5 형식("이 프레임을 Read하고 주장을 반박하라 … MATCH / MISMATCH / UNVERIFIABLE"):
  - O1: "신청자격(공통)은 모집공고일(2026.08.06) 현재 19세 이상인 대한민국 국적을 가진 자이며, 청약통장 가입여부·자산보유액 등에 관계없이 누구나 청약신청 가능하다." — 프레임 `t0358d4_1024.jpg`
  - O2: "임대조건 표에서 38타입 표준형은 보증금 150,000,000원 / 월 임대료 529,000원이고, 선택형3은 보증금 100,000,000원 / 월 임대료 737,000원이다." — 프레임 `t0618_1024.jpg`
  - O3: "청약 접수는 2026.08.12.(수)~08.14.(금) 09:00~17:30이고, 당첨자 발표는 2026.08.21.(금) 16:00이다." — 프레임 `t1406d2_1024.jpg`

Expected: 3건 모두 MATCH

- [ ] **Step 2: 변조 주장 3건을 `model: haiku` Agent로 감사** (값만 틀리게 심음):
  - T1: O2에서 월 임대료를 **592,000원**으로 변조 — 프레임 `t0618_1024.jpg`
  - T2: O3에서 접수 마감을 **08.15.(토)**로 변조 — 프레임 `t1406d2_1024.jpg`
  - T3: "특별공급 소득 3순위(120%) 4인 상한은 **10,652,642원**이다" (진값 10,562,642 자릿수 교환) — 프레임 `t0510d6_1024.jpg`

Expected: 3건 모두 MISMATCH (UNVERIFIABLE도 에스컬레이션되므로 게이트상 허용하되 기록)

- [ ] **Step 3: 판정** —
  - 변조 검출(=MISMATCH 또는 UNVERIFIABLE) 3/3 **그리고** 원본 오탐(MATCH 아님) 0~1건: **Haiku 채택 확정**. 원본 오탐은 에스컬레이션이 흡수하므로 1건까지 허용하되 기록.
  - 변조 검출 미달: `model: "sonnet"`으로 Step 1-2 반복 → 통과 시 SKILL.md의 haiku를 sonnet으로 수정 후 재커밋.
  - Sonnet도 미달: **레버 폐기** — `git revert`로 Task 5 커밋 되돌리고 최종 보고에 명시.

- [ ] **Step 4: 결과 기록** — 6건 판정표(주장·모델·판정·비고)를 최종 보고에 포함. 코드 변경이 있었으면(sonnet 전환/revert) 커밋.

---

### Task 7: E2E 재분석 + 비용·시간 재측정 — 완료 게이트 (스펙 §5.3-5.4)

**Files:**
- 산출: 재분석 guide.md (캐시 디렉토리), 측정 스크립트 `C:\Users\hwangjs\AppData\Local\Temp\claude\...\scratchpad\usage_round1.py` (세션 스크래치패드 — 저장소 밖)
- Modify: `C:\Users\hwangjs\.claude\projects\D--Repository-YoutubeAnalayzer\memory\yta-watch-benchmark.md` (라운드1 결과 추기)

**Interfaces:**
- Consumes: Task 1-6 전부 완료 상태의 저장소 스크립트 (플러그인 캐시 아닌 `skills/tuto/scripts/` 직접 실행)
- Produces: 완료/미달 판정 + 실측 수치

- [ ] **Step 1: 기준선 보존** — 재실행이 guide.md를 덮어쓰므로 먼저 복사:

```bash
cp "C:\Users\hwangjs\.yta\cache\zP3i_7xZW7Q\guide.md" "C:\Users\hwangjs\.yta\cache\zP3i_7xZW7Q\guide-baseline.md"
```

- [ ] **Step 2: 프레임 캐시 비우기** (video.mp4·subs·info.json·signals.json은 유지):

```bash
rm -rf "C:\Users\hwangjs\.yta\cache\zP3i_7xZW7Q\frames"
```

- [ ] **Step 3: analyze 콜드 재실행 + 시간 측정** — **PYTHONUTF8 접두 없이** 실행해 Task 1을 실전 검증:

```bash
python skills/tuto/scripts/analyze.py "https://youtu.be/zP3i_7xZW7Q"
```

검증: (a) 한글 STATUS·자막이 안 깨짐, (b) FRAME 19장 파일명이 기준선과 동일 — `t0001, t0027, t0138, t0210, t0338, t0528, t0618, t0659, t0743, t0811, t0841, t0917, t0957, t1050, t1235, t1342, t1450, t1523, t1609` (전부 `_512.jpg`), (c) 실행 시간 기록 (기준선 154초 — D3·D5 반영치 기대 ~40초 내외).

- [ ] **Step 4: zoom 동일 플랜 재실행 + 시간 측정**:

```bash
python skills/tuto/scripts/zoom.py zP3i_7xZW7Q --ranges "0:44-0:56,3:57-4:08@1024,4:54-5:12@1024,5:28-5:40@1024,5:53-6:03@1024,6:17-6:30@1024,10:24-10:44,12:09-12:20,13:15-13:28,14:06-14:16@1024,14:50-15:04@1024"
```

검증: 출력 `35 kept, 25 dup-dropped` 및 FRAME 파일명 집합이 기준선 35장과 동일 — `t0044d3_512, t0055d1_512, t0357d3_1024, t0358d4_1024, t0454d4_1024, t0510d6_1024, t0528d3_1024, t0539d1_1024, t0553d2_1024, t0554d2_1024, t0602d2_1024, t0617d3_1024, t0618_1024, t0629_1024, t1024d5_512, t1025d5_512, t1026d5_512, t1041d5_512, t1042d5_512, t1043d5_512, t1209d3_512, t1209d8_512, t1210d4_512, t1218d6_512, t1219d2_512, t1219d7_512, t1315d3_512, t1316_512, t1316d6_512, t1326d4_512, t1327_512, t1327d7_512, t1406d2_1024, t1451_1024, t1502d2_1024` (전부 `.jpg`). 시간 기록 (기준선 327초 — 기대 <70초).

- [ ] **Step 5: 가이드 재작성 + 값 대조** — SKILL.md 절차대로 프레임 판독→guide.md 작성 후, `guide-baseline.md`의 `(t=MM:SS)` 인용이 달린 모든 값(금액·날짜·자격 수치)과 신규 guide.md를 항목별 대조. Expected: 전 항목 동일 (차이 발견 시 fail-loud — 원인 규명 전 완료 선언 금지).

- [ ] **Step 6: 표본 감사 10건 — Task 6 확정 방식(haiku 또는 폴백)으로 실행**. Expected: 10/10 일치 + 스탬프에 "Haiku n건 + 재검 m건" 형식 기록.

- [ ] **Step 7: 비용·시간 집계** — 이 턴의 세션 jsonl을 message.id dedup 방법론으로 집계 (세션 스크래치패드의 usage_fixed.py를 phase 경계만 바꿔 재사용; 없으면 동일 로직 재작성 — 핵심: assistant 항목을 `message.id`로 dedup 후 `input + 2×cache_creation + 0.1×cache_read + 5×output` 합산, 서브에이전트 jsonl 별도 합산 후 Haiku분은 단가비 1/15로 가중). 판정: **달러 등가 ≤100만 그리고 총 시간 ≤12분**. 미달 시 수치와 함께 보고하고 중단 (스펙 §6 폴백 논의).

- [ ] **Step 8: 릴리스 + 메모리 갱신** — 게이트 전부 통과 시:
  - 플러그인 버전 범프: `grep -rn '"version"' --include="*.json" .`으로 버전 필드 위치를 찾아(marketplace.json 및 플러그인 매니페스트) `0.1.0`→`0.1.1`로 올리고 커밋:

```bash
git add -A
git commit -m "chore: v0.1.1 — 성능개선 라운드1 (감사 에스컬레이션·UTF-8·병렬화·dedup·signals 재사용)"
```

  - `claude plugin install tuto@yta` 재설치로 플러그인 캐시 갱신.
  - 메모리 `yta-watch-benchmark.md`에 라운드1 실측치(전/후 표) 추기, `yta-post-merge-followups.md`의 파킹 목록에서 해소 항목(핀포인트 dedup, cp949 가드) 제거.

---

## Self-Review 결과

- 스펙 커버리지: D1→Task 5·6, D2→Task 1, D3→Task 3, D4→Task 2, D5→Task 4, §5 게이트→Task 6·7, §2 측정→Task 7 Step 7. 누락 없음.
- 플레이스홀더: 없음 — 전 태스크 실코드·실명령·기대값 명시.
- 타입 일관성: `utf8_stdout()`·`_load_or_build_signals(cd, info, vid)`·`_extract_one(video, t, res, out_dir)` 시그니처가 정의·사용처 일치. `extract_frames`/`dedup_frames` 시그니처 불변으로 호출부 무수정.
