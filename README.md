# yta — 유튜브 튜토리얼 분석 (`/tuto`)

유튜브 튜토리얼 영상(≤30분, 한/영)을 신호 가중 2패스로 분석해 따라하기 스텝 가이드·요약·
Q&A 상태를 만드는 개인용 Claude Code 플러그인입니다.

## 요구사항

- Python 3.11 이상 (Windows 기준 `python` 사용, `python3` 아님)
- ffmpeg / ffprobe — 예: `winget install Gyan.FFmpeg`
- yt-dlp — 예: `pip install -U yt-dlp`
- 선택: `pip install faster-whisper` — Groq API 실패 시 로컬 ASR 폴백용

설치 상태는 `/tuto`를 세션에서 처음 호출할 때 `scripts/setup.py --check`가 자동으로 확인하고,
빠진 항목이 있으면 설치 명령을 안내합니다.

## 설정

`~/.config/yta/.env`에 값을 채웁니다 (첫 실행 시 아래 내용으로 빈 템플릿이 자동 생성됩니다).

```
# yta 설정 — 값을 채우면 저장 즉시 적용
# Groq Whisper (자막 없는 영상용, console.groq.com/keys)
GROQ_API_KEY=
# 캐시에 video.mp4를 유지할 최대 영상 수 (LRU)
CACHE_MAX_VIDEOS=10
```

`GROQ_API_KEY`가 비어 있으면 로컬 faster-whisper로, 그마저 없으면 프레임 중심 분석으로
자동 폴백합니다.

## 사용법

```
/tuto <video-url>
/tuto <video-url> <질문>
```

질문을 함께 주면 가이드를 만든 뒤 그 질문에 먼저 답합니다. 같은 세션의 후속 질문은
재다운로드 없이 캐시된 프레임·자막으로 답합니다.

## 캐시

분석 산출물은 `~/.yta/cache/<video_id>/`에 쌓입니다 (video.mp4, audio.mp3, info.json,
transcript.json, signals.json, frames/, zoom-plan.json, guide.md). `CACHE_MAX_VIDEOS`를
넘으면 가장 오래된 영상부터 video.mp4/audio.mp3만 LRU로 지우고 메타데이터·가이드는 남깁니다.

캐시를 전부 지우려면:

```
python skills/tuto/scripts/analyze.py --cleanup
```

## 스펙 · 플랜

- 설계 스펙: [`docs/superpowers/specs/2026-08-05-youtube-tutorial-analyzer-design.md`](docs/superpowers/specs/2026-08-05-youtube-tutorial-analyzer-design.md)
- 구현 플랜: [`docs/superpowers/plans/2026-08-05-yta-tuto-plugin.md`](docs/superpowers/plans/2026-08-05-yta-tuto-plugin.md)
- 오케스트레이션 계약: [`skills/tuto/SKILL.md`](skills/tuto/SKILL.md)
