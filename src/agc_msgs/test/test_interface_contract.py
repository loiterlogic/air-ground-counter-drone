import subprocess
from pathlib import Path

import pytest

# 契约 #messages 规定的 9 个消息（字段与顺序**不得变更**）。
#
# 2026-11-08 用户裁定 Q7/Q28：新增第 10 个 `ObstacleFootprintArray`（足迹点）。
# 2026-11-11（ADR-0042）：新增第 11 个 `PerceptionCellMeta`（逐格元数据）。
# 它**不改动**上面 9 个的任何字段或顺序，故不违反契约；本清单同时守护新旧两类：
#   * 前 9 个 = 契约冻结集（golden 逐行比对，任何漂移即红）；
#   * 第 10 个 = 新增消息（同样冻结，防止有人事后改字段而不改 golden）。
MESSAGES = [
    "AgcTaskState",
    "AirObservationArray",
    "ObstacleObservation",
    "ObstacleFootprintArray",
    "ObstacleTrack",
    "ObstacleTrackArray",
    "PerceptionCellMeta",
    "SensorObservation",
    "TargetObservation",
    "TargetTrack",
    "TargetTrackArray",
]

GOLDEN_DIR = Path(__file__).parent / "golden"


def _interface_show(name: str) -> str:
    result = subprocess.run(
        ["ros2", "interface", "show", f"agc_msgs/msg/{name}"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize("name", MESSAGES)
def test_interface_contract(name: str) -> None:
    """ros2 interface show 输出须与冻结 golden 逐行一致。"""
    golden = (GOLDEN_DIR / f"{name}.txt").read_text(encoding="utf-8")
    actual = _interface_show(name)
    assert actual.strip() == golden.strip(), (
        f"{name} 接口与 golden 不一致：\n"
        f"--- golden ---\n{golden}\n--- actual ---\n{actual}"
    )
