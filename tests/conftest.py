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


@pytest.fixture(autouse=True)
def _stub_ocr_extract(monkeypatch):
    """테스트는 기본적으로 실 OCR 서브프로세스를 부르지 않는다 — zoom/analyze에
    ocr.report가 배선되면서 기존 추출 테스트가 조용히 실 winocr 호출을 하게 된
    회귀의 차단막. OCRTXT 동작을 검증하는 테스트는 자체 monkeypatch로 이 스텁을 덮는다."""
    import ocr
    monkeypatch.setattr(ocr, "extract_batch", lambda paths: {})
