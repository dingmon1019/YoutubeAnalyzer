# Contributing to tuto

Thanks for helping improve `tuto`.

The most valuable contributions are **real tutorial failure cases**. If a video contains a setting, button, number, or operation that `tuto` misses or misreads, please report it with enough evidence to reproduce the problem.

## Good bug reports

Please include:

- a public YouTube URL
- the approximate timestamp
- the expected result
- the actual result
- your operating system
- Python, Claude Code, and tuto versions when relevant

Do not include API keys, credentials, private videos, or confidential material.

The [tutorial failure template](.github/ISSUE_TEMPLATE/tutorial_failure.md) is the best starting point when the problem is tied to a specific video.

## Development setup

The Python tests require Python 3.11+ and pytest. Tests that exercise real frame extraction also use ffmpeg/ffprobe; they are skipped when ffmpeg is not available.

Install the runtime tools using the commands appropriate for your system:

```bash
pip install -U yt-dlp pytest
```

```bash
# Windows
winget install Gyan.FFmpeg

# macOS
brew install ffmpeg
```

Run the regression suite from the repository root:

```bash
python -m pytest tests -q
```

If Claude Code is installed, you can also validate the plugin manifest locally:

```bash
claude plugin validate .
```

## Pull requests

1. Keep changes focused.
2. Add or update tests for behavioral changes.
3. Run the existing test suite before opening a pull request.
4. Explain the failure mode your change fixes.
5. Prefer measurable improvements over prompt-only claims.

Changes that alter extraction, auditing, or orchestration behavior should ideally include a regression case. Documentation-only changes should still verify every referenced command and repository path.

## Useful contribution areas

- macOS and Linux validation
- caption/screen disagreement cases
- missed-step detection
- audit false positives
- performance regressions
- token-cost regressions
- documentation and installation fixes

## Design principle

When evidence is unclear, prefer an explicit unresolved result over a confident guess.
