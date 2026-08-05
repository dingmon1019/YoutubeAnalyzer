import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import frames


def test_extract_frames_names_and_count(synth_clip, tmp_path):
    out = frames.extract_frames(synth_clip, [1.0, 8.0], 512, tmp_path)
    assert len(out) == 2
    assert out[0].name == "t0001_512.jpg" and out[0].exists()
    assert out[1].name == "t0008_512.jpg"


def test_dedup_drops_static(synth_clip, tmp_path):
    # 1s,2s,3s = 전부 파랑 정지 → 2장 드롭. 8s = 빨강 → 유지
    out = frames.extract_frames(synth_clip, [1.0, 2.0, 3.0, 8.0], 512, tmp_path)
    kept, dropped = frames.dedup_frames(out)
    assert dropped == 2
    assert [p.name for p in kept] == ["t0001_512.jpg", "t0008_512.jpg"]
