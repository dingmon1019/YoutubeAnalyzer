# Download Hardening (즉시 적용 5건) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-08-14 실측 평가에서 확인된 즉시 적용 결함 5건을 고친다 — 다운로드 403 대응(JS 런타임 탐지 + android 폴백 1회), traceback 금지 관례 이행, 자막 HTML 엔티티 정규화, SKILL.md gaps 정의 명문화.

**Architecture:** 파이프라인 구조는 불변. JS 런타임 탐지를 common.py(유일한 공유 모듈)에 두고 setup.py(프리플라이트 NOTE)와 analyze.py(다운로드 명령 구성)가 함께 쓴다. 다운로드 실패는 "재시도 루프"가 아니라 **방법 전환 1회**(android player client)로만 복구하고, 폴백 사용 사실은 NOTE로 stdout에 남긴다(조용한 폴백 금지). 최종 실패는 traceback 대신 평문 ERROR + exit 4.

**Tech Stack:** Python 3.11+ / pytest / yt-dlp / 기존 스크립트 5종(common·setup·analyze·transcribe·SKILL.md)

## 범위 제외 (이미 HEAD에 반영됨 — 구현 금지)

- visual-coverage `kind` 허용값 명시 → SKILL.md 174행에 이미 있음
- 자막 전용 항목의 감사 절차 → SKILL.md §5 "근거가 transcript뿐인 항목이면 세그먼트 원문을 준다"로 이미 있음
- 감사 후보 형식 변경 → 이미 `--audit-candidates` 스크립트 방식으로 전환됨
- 감사 복수 프레임·해시 교차 대조 → **조건부 항목** (오류 주입 시험 게이트 필요, 이 계획 범위 아님)
- 영상 간 취합 계층 → 반려됨 (관심사 분리 위반)

## Global Constraints

- Windows 우선: 실행 명령은 `python` (`python3` 금지), 경로는 `Path` 사용
- fail-loud: 조용한 폴백 금지 — 폴백·이상 흔적은 NOTE/flags로 stdout에 남긴다; **traceback을 사용자에게 노출하지 않는다** (design §9)
- 모듈 독립성: 스크립트 간 상호 임포트 금지 — 공유는 `common.py`만 (기존 관례)
- 재시도 루프 금지 (design §9 218행) — 허용되는 것은 **방법 전환 1회**뿐
- 테스트는 append-only: 기존 테스트·독스트링 무수정
- 단위 테스트는 네트워크 없이 통과해야 한다 (yt-dlp 실호출 금지 — monkeypatch)
- 커밋 스타일: `fix(<모듈>): <요약>` 한국어 본문, 끝에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 작업 브랜치: `git checkout -b hardening-round4 master`

## 기준점 (전체 수용 기준 — 전 태스크 완료 후 확인)

1. `python -m pytest tests/ -q` 전체 통과 (기존 224개 + 신규 ≥8개, 실패 0) — L2
2. 폴백은 정확히 1회: 두 번째 실패는 그대로 전파됨을 테스트가 증명
3. 다운로드 실패 시 사용자 노출 traceback 0건 (RuntimeError·TimeoutExpired 모두 평문)
4. NOTE 없는 조용한 폴백 0건 (폴백 테스트가 stdout NOTE를 assert)
5. `--check`는 JS 런타임 부재 시 stderr NOTE를 내되 exit 0 유지 (기존 stale NOTE 선례와 동일 계약)
6. SKILL.md 계약 테스트(gaps 정의) 통과
7. (선택, 네트워크 L3) 403이 났던 실측 영상 `https://youtu.be/tukOm3Afd8s`의 캐시 삭제 후 `python skills/tuto/scripts/analyze.py <url>` 재실행 → 폴백 NOTE와 함께 성공, 또는 평문 ERROR로 종료

---

### Task 1: common.detect_js_runtime()

**Files:**
- Modify: `skills/tuto/scripts/common.py` (파일 끝에 함수 추가, import에 `shutil` 추가)
- Test: `tests/test_common.py` (append)

**Interfaces:**
- Produces: `common.detect_js_runtime() -> str` — `"deno" | "node" | "bun" | ""`. Task 2·3이 소비한다.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_common.py` 끝에 append:

```python
def test_detect_js_runtime_prefers_deno(monkeypatch):
    """yt-dlp EJS는 deno만 기본 활성이므로 deno를 최우선 탐지한다."""
    monkeypatch.setattr(common.shutil, "which",
                        lambda name: "/fake/" + name if name in ("deno", "node") else None)
    assert common.detect_js_runtime() == "deno"


def test_detect_js_runtime_falls_back_to_node_then_empty(monkeypatch):
    monkeypatch.setattr(common.shutil, "which",
                        lambda name: "/fake/node" if name == "node" else None)
    assert common.detect_js_runtime() == "node"
    monkeypatch.setattr(common.shutil, "which", lambda name: None)
    assert common.detect_js_runtime() == ""
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_common.py -q -k js_runtime`
Expected: FAIL — `AttributeError: module 'common' has no attribute 'shutil'` (또는 `detect_js_runtime` 부재)

- [ ] **Step 3: 최소 구현** — `common.py` import 블록에 `import shutil` 추가 후 파일 끝에:

```python
def detect_js_runtime() -> str:
    """yt-dlp EJS용 JS 런타임 탐지. yt-dlp는 deno만 기본 활성이라 deno가 있으면 플래그가
    필요 없고, node/bun은 다운로드 명령에 --js-runtimes로 명시해야 쓰인다. 없으면 ""
    — 2026-08-14 실측: 런타임 부재 시 YouTube 다운로드가 HTTP 403으로 즉사했다."""
    for rt in ("deno", "node", "bun"):
        if shutil.which(rt):
            return rt
    return ""
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_common.py -q`
Expected: 전체 PASS (기존 테스트 포함)

- [ ] **Step 5: Commit**

```bash
git add skills/tuto/scripts/common.py tests/test_common.py
git commit -m "feat(common): JS 런타임 탐지 헬퍼 — yt-dlp EJS 403 대응의 공용 기반"
```

---

### Task 2: setup.py 프리플라이트에 JS 런타임 NOTE

**Files:**
- Modify: `skills/tuto/scripts/setup.py:28-46` (`check_env`) 및 `:60-73` (`main`의 `--check` 분기)
- Test: `tests/test_setup.py` (append)

**Interfaces:**
- Consumes: `common.detect_js_runtime()` (Task 1)
- Produces: `check_env()` 반환 dict에 `"js_runtime": str` 키 추가. `--check`는 런타임 부재 시 stderr NOTE + exit 0 (기존 stale NOTE와 동일 계약 — SKILL.md §0이 이미 "stderr NOTE를 사용자에게 알린다"로 처리한다).

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_setup.py` 끝에 append:

```python
def test_check_env_reports_js_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(yta_setup.common, "CONFIG_FILE", tmp_path / ".env")
    monkeypatch.setattr(yta_setup.common, "detect_js_runtime", lambda: "node")
    r = yta_setup.check_env()
    assert r["js_runtime"] == "node"


def test_check_prints_note_when_no_js_runtime(monkeypatch, tmp_path, capsys):
    """실측(2026-08-14): JS 런타임 부재로 다운로드가 403 즉사했는데 --check는 exit 0으로
    통과시켰다. stale NOTE 선례(F6)와 같은 계약으로 — exit 0 유지 + stderr 경고."""
    monkeypatch.setattr(yta_setup.common, "CONFIG_FILE", tmp_path / ".env")
    monkeypatch.setattr(yta_setup, "check_env", lambda: {
        "status": "ready", "missing": [], "ytdlp_version": "2026.07.04",
        "ytdlp_stale": False, "js_runtime": "", "has_groq_key": False,
        "has_faster_whisper": False, "config_file": str(tmp_path / ".env"),
    })
    monkeypatch.setattr(yta_setup.sys, "argv", ["setup.py", "--check"])
    code = yta_setup.main()
    err = capsys.readouterr().err
    assert "JS runtime" in err and "403" in err
    assert code == 0


def test_check_silent_when_js_runtime_present(monkeypatch, tmp_path, capsys):
    """음성 회귀 가드: 런타임이 있으면 여전히 완전 침묵 + exit 0."""
    monkeypatch.setattr(yta_setup.common, "CONFIG_FILE", tmp_path / ".env")
    monkeypatch.setattr(yta_setup, "check_env", lambda: {
        "status": "ready", "missing": [], "ytdlp_version": "2026.07.04",
        "ytdlp_stale": False, "js_runtime": "deno", "has_groq_key": False,
        "has_faster_whisper": False, "config_file": str(tmp_path / ".env"),
    })
    monkeypatch.setattr(yta_setup.sys, "argv", ["setup.py", "--check"])
    code = yta_setup.main()
    out, err = capsys.readouterr()
    assert out == "" and err == "" and code == 0
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_setup.py -q -k js_runtime`
Expected: FAIL — `KeyError: 'js_runtime'` / NOTE 미출력

- [ ] **Step 3: 최소 구현**
  - `check_env()` 반환 dict에 `"js_runtime": common.detect_js_runtime(),` 한 줄 추가.
  - `main()`의 `--check` ready 분기, 기존 stale NOTE 블록 **아래**에:

```python
            if not r["js_runtime"]:
                # 실측(2026-08-14): 런타임 부재 시 유튜브 다운로드가 403으로 즉사 —
                # 설치 자체는 끝난 상태이므로 exit 0은 유지하고 stderr에만 남긴다(F6 선례).
                print(
                    "NOTE: no JS runtime for yt-dlp (deno/node/bun) — YouTube downloads "
                    "may fail with HTTP 403. install: winget install DenoLand.Deno",
                    file=sys.stderr,
                )
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_setup.py -q`
Expected: 전체 PASS (기존 4개 + 신규 3개)

- [ ] **Step 5: Commit**

```bash
git add skills/tuto/scripts/setup.py tests/test_setup.py
git commit -m "fix(setup): 프리플라이트가 JS 런타임 부재를 탐지 — 403 즉사를 사전 경고"
```

---

### Task 3: analyze.py 다운로드 명령 구성 + android 폴백 1회

**Files:**
- Modify: `skills/tuto/scripts/analyze.py:136-176` (`download()` — 미디어 다운로드 명령을 헬퍼로 분리)
- Test: `tests/test_analyze.py` (append)

**Interfaces:**
- Consumes: `common.detect_js_runtime()` (Task 1), `common.run()`
- Produces: `_media_cmd(url, video_f, cd, sub_langs, js_rt="", android=False) -> list` — Task 4의 평문 오류 처리와 독립. `download()` 동작: 1차 실패 시 android client로 **정확히 1회** 재시도 + stdout NOTE, 2차 실패는 전파.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_analyze.py` 끝에 append:

```python
def test_media_cmd_flags(tmp_path):
    """js_rt가 node/bun일 때만 --js-runtimes를 넣는다(deno는 yt-dlp 기본 활성이라 불필요)."""
    cmd = analyze._media_cmd("URL", tmp_path / "v.mp4", tmp_path, "en", js_rt="node")
    assert "--js-runtimes" in cmd and cmd[cmd.index("--js-runtimes") + 1] == "node"
    cmd = analyze._media_cmd("URL", tmp_path / "v.mp4", tmp_path, "en", js_rt="deno")
    assert "--js-runtimes" not in cmd
    cmd = analyze._media_cmd("URL", tmp_path / "v.mp4", tmp_path, "en", android=True)
    assert "--extractor-args" in cmd
    assert cmd[cmd.index("--extractor-args") + 1] == "youtube:player_client=android"
    assert "--no-playlist" in cmd  # 기존 플래그 보존


def test_download_falls_back_to_android_once(tmp_path, monkeypatch, capsys):
    """실측(2026-08-14, tukOm3Afd8s): 403이 android client 전환 1회로 풀렸다.
    재시도 루프 금지 관례에 따라 방법 전환은 정확히 1회, 흔적은 NOTE로 남는다."""
    cd = tmp_path
    (cd / "info.json").write_text('{"language": "en"}', encoding="utf-8")
    calls = []

    def fake_run(cmd, timeout=600):
        calls.append([str(c) for c in cmd])
        if len(calls) == 1:
            raise RuntimeError("command failed (1): yt-dlp ...\nHTTP Error 403: Forbidden")

    monkeypatch.setattr(analyze.common, "run", fake_run)
    monkeypatch.setattr(analyze.common, "detect_js_runtime", lambda: "node")
    analyze.download("https://youtu.be/x0000000000", cd)
    assert len(calls) == 2
    assert "youtube:player_client=android" in calls[1]
    assert "NOTE" in capsys.readouterr().out  # 조용한 폴백 금지


def test_download_second_failure_propagates(tmp_path, monkeypatch):
    """폴백은 1회뿐 — 두 번째 실패는 그대로 전파돼 fail-loud 경로(Task 4)로 간다."""
    cd = tmp_path
    (cd / "info.json").write_text('{"language": "en"}', encoding="utf-8")

    def always_fail(cmd, timeout=600):
        raise RuntimeError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(analyze.common, "run", always_fail)
    monkeypatch.setattr(analyze.common, "detect_js_runtime", lambda: "")
    with pytest.raises(RuntimeError):
        analyze.download("https://youtu.be/x0000000000", cd)
```

(파일 상단에 `import pytest`가 없으면 추가한다 — 기존 import 블록은 건드리지 않고 아래에 append.)

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_analyze.py -q -k "media_cmd or fallback or propagates"`
Expected: FAIL — `_media_cmd` 부재

- [ ] **Step 3: 최소 구현** — `download()`의 미디어 다운로드 블록(현재 163-174행)을 다음으로 교체하고, 함수 위에 헬퍼 추가:

```python
def _media_cmd(url, video_f, cd, sub_langs, js_rt: str = "", android: bool = False) -> list:
    """미디어+자막 yt-dlp 명령 구성. deno는 yt-dlp가 자동 사용하므로 node/bun만 명시한다."""
    cmd = ["yt-dlp", url]
    if js_rt in ("node", "bun"):
        cmd += ["--js-runtimes", js_rt]
    if android:
        cmd += ["--extractor-args", "youtube:player_client=android"]
    cmd += [
        "-f", "bv*[height<=720]+ba/b[height<=720]", "--merge-output-format", "mp4",
        "-o", str(video_f),
        "--write-subs", "--write-auto-subs", "--sub-langs", sub_langs,
        "--sub-format", "vtt", "-o", f"subtitle:{cd / 'subs'}",
        "--no-playlist", "--no-progress",
    ]
    return cmd
```

`download()` 안:

```python
    if not video_f.exists():
        # 2단계: 실제 미디어 + 자막. language는 1단계(또는 기존 info.json)에서 확인한 값.
        sub_langs = _sub_langs_for(info.get("language"), info)
        js_rt = common.detect_js_runtime()
        try:
            common.run(_media_cmd(url, video_f, cd, sub_langs, js_rt), timeout=1800)
        except RuntimeError as e:
            # 재시도 루프가 아니라 방법 전환 1회다(§9 재시도 금지와 구분). 실측(2026-08-14):
            # 403 2건 모두 android client 전환 1회로 해소. 조용한 폴백 금지 — NOTE를 남겨
            # 패스1 보고서에 실리게 한다.
            print(f"NOTE: media download failed once — retrying with android player client "
                  f"({str(e).splitlines()[-1][:120]})")
            common.run(_media_cmd(url, video_f, cd, sub_langs, js_rt, android=True),
                       timeout=1800)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_analyze.py -q`
Expected: 전체 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/tuto/scripts/analyze.py tests/test_analyze.py
git commit -m "fix(analyze): 403 시 android client로 방법 전환 1회 + JS 런타임 자동 지정"
```

---

### Task 4: analyze.py 실패를 평문으로 (traceback 금지)

**Files:**
- Modify: `skills/tuto/scripts/analyze.py:288-303` (`main()`)
- Test: `tests/test_analyze.py` (append)

**Interfaces:**
- Consumes: Task 3의 `download()` (실패 시 RuntimeError 전파)
- Produces: `main()`이 RuntimeError·subprocess.TimeoutExpired를 잡아 stdout에 `=== YTA PASS1: FAILED ===` + `ERROR:` 평문, stderr에 한 줄 미러 후 **exit 4**. traceback 없음. (SKILL.md §실패 시의 "평문으로 있는 그대로 보고" 계약 + design §9 traceback 금지 이행)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_analyze.py` 끝에 append:

```python
def test_main_reports_download_failure_as_plain_text(monkeypatch, capsys):
    """design §9: traceback 금지. 실측(2026-08-14)에서는 403이 raw traceback으로 터졌다 —
    평문 ERROR + exit 4 + 403 힌트로 바뀌어야 한다."""
    monkeypatch.setattr(analyze, "run_pass1",
                        lambda url: (_ for _ in ()).throw(
                            RuntimeError("command failed (1): yt-dlp ...\nHTTP Error 403: Forbidden")))
    monkeypatch.setattr(analyze.sys, "argv", ["analyze.py", "https://youtu.be/x0000000000"])
    code = analyze.main()
    out, err = capsys.readouterr()
    assert code == 4
    assert "=== YTA PASS1: FAILED ===" in out and "ERROR:" in out
    assert "403" in out and "Traceback" not in out and "Traceback" not in err
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_analyze.py -q -k plain_text`
Expected: FAIL — RuntimeError가 그대로 전파됨

- [ ] **Step 3: 최소 구현** — `main()`의 `return run_pass1(args.url)`을 교체 (파일 상단 import에 `import subprocess` 추가):

```python
    try:
        return run_pass1(args.url)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        # design §9 fail-loud: traceback 금지 — 원인 요약과 다음 행동만 평문으로.
        # stdout은 pass1-report.txt로 리다이렉트될 수 있어 stderr에도 한 줄 미러한다.
        msg = str(e)[:600]
        print("=== YTA PASS1: FAILED ===")
        print(f"ERROR: {msg}")
        if "403" in msg:
            print("HINT: JS 런타임(deno/node) 부재 가능 — setup.py --check의 NOTE 확인. "
                  "일시적 차단일 수 있으니 잠시 후 재실행도 유효하다.")
        print(f"ERROR: pass1 failed — {msg.splitlines()[-1][:160]}", file=sys.stderr)
        return 4
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_analyze.py -q`
Expected: 전체 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/tuto/scripts/analyze.py tests/test_analyze.py
git commit -m "fix(analyze): 다운로드 실패를 평문 ERROR+exit 4로 — traceback 금지 관례 이행"
```

---

### Task 5: transcribe.py HTML 엔티티 정규화

**Files:**
- Modify: `skills/tuto/scripts/transcribe.py:31-51` (`parse_vtt`) — import에 `import html` 추가
- Test: `tests/test_transcribe.py` (append)

**Interfaces:**
- Produces: `parse_vtt()`가 `&nbsp;`·`&amp;` 등 HTML 엔티티를 실제 문자로 정규화(비분리 공백은 일반 공백으로). 하류(dedup·video.md 인용)는 무수정.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_transcribe.py` 끝에 append:

```python
def test_parse_vtt_unescapes_html_entities():
    """실측(2026-08-14, 0chZFIZLR_0): 자막의 &nbsp;가 그대로 남아 video.md 인용까지
    전파될 뻔했다. 엔티티는 마크업 잔재이지 '원문 오타 보존' 대상이 아니다."""
    vtt = ("WEBVTT\n\n"
           "00:01.000 --> 00:03.000\n"
           "To sum it up, git merge&nbsp;&nbsp;gives &amp; keeps\n")
    cues = transcribe.parse_vtt(vtt)
    assert len(cues) == 1
    assert "&nbsp;" not in cues[0]["text"] and "&amp;" not in cues[0]["text"]
    assert "\xa0" not in cues[0]["text"]          # 비분리 공백도 일반 공백으로
    assert "gives & keeps" in cues[0]["text"]
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_transcribe.py -q -k unescape`
Expected: FAIL — `&nbsp;`가 텍스트에 남음

- [ ] **Step 3: 최소 구현** — import 블록에 `import html` 추가, `parse_vtt()`의 46행을:

```python
            clean = html.unescape(_INLINE.sub("", line)).replace("\xa0", " ").strip()
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_transcribe.py -q`
Expected: 전체 PASS (기존 dedup·collapse 테스트 포함 — 회귀 없음)

- [ ] **Step 5: Commit**

```bash
git add skills/tuto/scripts/transcribe.py tests/test_transcribe.py
git commit -m "fix(transcribe): VTT의 HTML 엔티티(&nbsp; 등)를 실제 문자로 정규화"
```

---

### Task 6: SKILL.md gaps 정의 한 줄 + 계약 테스트

**Files:**
- Modify: `skills/tuto/SKILL.md` (§4 evidence-patch 예시 코드펜스 직후, 현재 266행 부근 — `**\`knowledge_items\`** —` 문단 **앞**)
- Test: `tests/test_skill_contract.py` (append)

**Interfaces:**
- Produces: SKILL.md에 gaps 의미를 못박는 계약 문구. 코드 변경 없음(스키마는 이미 올바르게 거부한다 — 문서만 부족).

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_skill_contract.py` 끝에 append:

```python
# ── gaps 정의 (2026-08-14 실측: 빌더 3명 중 2명이 gaps에 산문 노트를 넣어 merge 거부) ──

def test_skill_defines_gaps_as_time_ranges_not_notes():
    """예시 JSON 한 줄만으로는 부족했다 — gaps가 시간 구간 객체 전용이며 산문 노트는
    '누락 후보'로 가야 한다는 명시 문구가 있어야 한다."""
    assert "시간 구간 객체만" in TEXT
    assert "누락 후보" in TEXT
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_skill_contract.py -q -k gaps`
Expected: FAIL — 문구 부재

- [ ] **Step 3: SKILL.md에 문구 추가** — evidence-patch 예시 코드펜스 닫힘(```) 바로 아래에:

```markdown
**`gaps`는 시간 구간 객체만 담는다** — `{"start": 초, "end": 초, "reason": "..."}` 형식.
"확인 못 한 것" 산문 노트는 gaps가 아니라 `video.md`의 `## 누락 후보` 절에 적는다.
문자열을 넣으면 `--merge`가 exit 2로 거부한다 (실측 2026-08-14: 빌더 3명 중 2명이 이
함정에 걸렸다 — 예시만으로는 부족했다).
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_skill_contract.py -q`
Expected: 전체 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/tuto/SKILL.md tests/test_skill_contract.py
git commit -m "docs(skill): gaps는 시간 구간 객체 전용임을 명문화 — 빌더 함정 예방"
```

---

### Task 7: 버전 범프 + 전체 게이트

**Files:**
- Modify: `.claude-plugin/plugin.json` (`"version": "0.3.2"` → `"0.3.3"`)
- Modify: `README.md:14` (버전 배지 `0.3.2` → `0.3.3`)

**Interfaces:**
- Consumes: Task 1~6 전부 완료 상태
- Produces: 마켓플레이스가 새 버전을 인식해 `claude plugin update tuto@yta`로 배포 가능

- [ ] **Step 1: 전체 테스트 게이트**

Run: `python -m pytest tests/ -q`
Expected: 전체 PASS, 실패 0 (기준점 1)

- [ ] **Step 2: 버전 범프** — plugin.json의 version을 `0.3.3`으로, README 배지의 `version-0.3.2-blue`를 `version-0.3.3-blue`로 수정

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/plugin.json README.md
git commit -m "chore(release): v0.3.3 — download hardening (403 폴백·평문 오류·엔티티 정규화)"
```

- [ ] **Step 4: (선택, 네트워크 L3) 실측 재현** — 기준점 7:

```bash
python skills/tuto/scripts/analyze.py --cleanup
python skills/tuto/scripts/analyze.py "https://youtu.be/tukOm3Afd8s"
```

Expected: 성공(폴백 시 NOTE 줄 포함) 또는 `=== YTA PASS1: FAILED ===` 평문 — 어느 쪽이든 traceback 0

- [ ] **Step 5: master 병합·푸시·플러그인 갱신은 사용자 확인 후** — `git checkout master && git merge --ff-only hardening-round4 && git push origin master` → `claude plugin marketplace update yta && claude plugin update tuto@yta`

---

## Self-Review 결과

- 범위 대조: 즉시 적용 5건 = Task 3·2(다운로드 견고화 2건), Task 4(평문 오류), Task 5(엔티티), Task 6(gaps 문구) — 전부 커버. Task 1은 2·3의 공용 기반, Task 7은 배포 게이트.
- 타입 일관성: `detect_js_runtime()->str`(Task 1)을 Task 2·3이 같은 시그니처로 소비. `_media_cmd(...)->list`는 Task 3에서 정의·테스트.
- 플레이스홀더 없음: 전 태스크에 실제 코드·실행 명령·기대 결과 명시.
- 주의: `tests/test_analyze.py`의 기존 import에 `pytest`가 이미 있으면 중복 추가하지 않는다. Task 3 Step 3의 교체 대상 행 번호는 HEAD(e93bf96) 기준이다.
