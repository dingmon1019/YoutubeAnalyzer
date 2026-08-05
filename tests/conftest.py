import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))

FFMPEG = shutil.which("ffmpeg")


@pytest.fixture(scope="session")
def synth_clip(tmp_path_factory):
    """11秒 合成クリップ: 0-5s 静止(青) → 5-6s 変化(ノイズ) → 6-11s 静止(赤)."""
    if not FFMPEG:
        pytest.skip("ffmpeg not on PATH")
    out = tmp_path_factory.mktemp("clip") / "synth.mp4"
    filt = (
        "color=blue:s=320x240:d=5[a];"
        "testsrc2=s=320x240:d=1[b];"
        "color=red:s=320x240:d=5[c];"
        "[a][b][c]concat=n=3:v=1:a=0"
    )
    subprocess.run(
        [FFMPEG, "-y", "-filter_complex", filt, "-r", "10", str(out)],
        check=True, capture_output=True,
    )
    return out
