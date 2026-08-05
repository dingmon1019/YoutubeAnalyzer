import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "tuto" / "scripts"))
import zoom


def test_parse_ranges():
    r = zoom.parse_ranges("3:10-3:50@1024,12:11-12:40")
    assert r[0] == {"start": 190.0, "end": 230.0, "res": 1024}
    assert r[1]["res"] == 512


def test_plan_caps_2fps_and_20_per_range():
    ts = zoom.plan_timestamps([{"start": 0.0, "end": 5.0, "res": 512}])
    assert len(ts) == 10                       # 5초 × 2fps
    ts = zoom.plan_timestamps([{"start": 0.0, "end": 60.0, "res": 512}])
    assert len(ts) == 20                       # 구간 캡


def test_plan_global_cap_60():
    ranges = [{"start": i * 100.0, "end": i * 100.0 + 60.0, "res": 512} for i in range(5)]
    ts = zoom.plan_timestamps(ranges)          # 5구간 × 20 = 100 → 60으로 감축
    assert len(ts) <= 60
    starts = {r["start"] for r in ranges}
    covered = {min(starts, key=lambda s: abs(s - t)) for t, _ in ts}
    assert covered == starts                   # 감축돼도 모든 구간 커버 (P3)


def test_single_timestamps_mode():
    ts = zoom.parse_single("12:34@1024,0:05")
    assert ts == [(754.0, 1024), (5.0, 512)]
