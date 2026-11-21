#!/usr/bin/env python3
"""ROS 2 node that bridges Feetech servos <-> topic_based_ros2_control.

It:
* subscribes to `/so101_follower/joint_commands` (sensor_msgs/JointState)
  and writes Goal_Position to the servos.
* publishes `/so101_follower/joint_states` every 20 ms using Present_Position.

Make sure the USB-to-UART adapter of the servo bus is accessible
(e.g. `/dev/ttyUSB0`) and you have permission to open it.
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
import sys
import math
import yaml, pathlib
from ament_index_python.packages import get_package_share_directory

# -----------------------------------------------------------------------------
# Provide lightweight stubs for optional third-party dependencies that the
# Feetech SDK imports but are not strictly required to operate the motors.
# -----------------------------------------------------------------------------
try:
    import deepdiff  # type: ignore
except ImportError:  # create stub
    import types
    deepdiff_stub = types.ModuleType("deepdiff")
    class _DD(dict):
        pass
    deepdiff_stub.DeepDiff = _DD  # type: ignore
    sys.modules["deepdiff"] = deepdiff_stub

try:
    import tqdm  # type: ignore
except ImportError:  # create stub
    import types
    tqdm_stub = types.ModuleType("tqdm")
    def _tqdm(iterable=None, **kwargs):
        return iterable if iterable is not None else []
    tqdm_stub.tqdm = _tqdm  # type: ignore
    sys.modules["tqdm"] = tqdm_stub

# -----------------------------------------------------------------------------

from so101_hw_interface.motors.feetech.feetech import FeetechMotorsBus
from so101_hw_interface.motors import Motor, MotorNormMode

PORT_DEFAULT = "/dev/ttyACM0"

JOINTS = {
    "shoulder_pan": {"id": 1, "model": "sts3215"},
    "shoulder_lift": {"id": 2, "model": "sts3215"},
    "elbow_flex": {"id": 3, "model": "sts3215"},
    "wrist_flex": {"id": 4, "model": "sts3215"},
    "wrist_roll": {"id": 5, "model": "sts3215"},
    "gripper": {"id": 6, "model": "sts3215"},
}

# Default calibration file distributed with the package (can be overridden by
# the ROS parameter "calib_file").
CALIB_FILE = (
    pathlib.Path(get_package_share_directory("so101_hw_interface"))
    / "config/so101_calibration.yaml"
)

class MotorBridge(Node):
    def __init__(self):
        super().__init__("so101_motor_bridge")
        # Declare parameters so they can be overridden from launch/CLI
        self.declare_parameter("port", PORT_DEFAULT)
        self.declare_parameter("calib_file", str(CALIB_FILE))
        self.declare_parameter("require_calibration", False)
        self.stop_on_bus_error = self.declare_parameter("stop_on_bus_error", False).value

        port = self.get_parameter("port").get_parameter_value().string_value
        if not port:
            port = PORT_DEFAULT

        # Build motor objects
        motors = {
            name: Motor(cfg["id"], cfg["model"], MotorNormMode.DEGREES)
            for name, cfg in JOINTS.items()
        }
        self.bus = FeetechMotorsBus(port, motors)

        # Feetech STS3215 resolution: 4096 steps per 2π rad
        self._steps_per_rad = 4096.0 / (2 * math.pi)

        # Load calibration (if file exists) else fall back to first-read capture
        calib_path = pathlib.Path(self.get_parameter("calib_file").get_parameter_value().string_value).expanduser()
        self._home_offsets: dict[str, int] | None = None
        self._limits: dict[str, tuple[int, int]] | None = None
        if calib_path.is_file():
            with open(calib_path, "r", encoding="utf-8") as fp:
                calib = yaml.safe_load(fp)
            self._home_offsets = {j: calib[j]["homing_offset"] for j in JOINTS if j in calib}
            self._limits = {j: (calib[j]["range_min"], calib[j]["range_max"]) for j in JOINTS if j in calib}
            self.get_logger().info(f"Loaded calibration from {calib_path}")
        else:
            self.get_logger().warn(f"Calibration file {calib_path} not found – will capture offsets on first read.")

        if self.get_parameter("require_calibration").value and (
            self._limits is None or self._limits.keys() != JOINTS.keys()
        ):
            raise RuntimeError(f"MoveIt requires calibration for all six joints in {calib_path}")
        if self._limits and any(low > high for low, high in self._limits.values()):
            raise RuntimeError(f"Invalid joint limits in {calib_path}")

        self.joint_states_pub = self.create_publisher(JointState, "so101_follower/joint_states", 10)
        self.joint_commands_sub = self.create_subscription(
            JointState, "so101_follower/joint_commands", self._command_cb, 10
        )

        self.get_logger().info(f"Connecting to Feetech bus on {port} …")
        torque_requested = False
        try:
            self.bus.connect()
            modes = self.bus.sync_read("Operating_Mode", normalize=False)
            if any(modes[name] != 0 for name in JOINTS):
                raise RuntimeError("All SO-101 motors must be in position mode")
            measured = self.bus.sync_read("Present_Position", normalize=False)
            if self._limits:
                outside_range = [
                    f"{name} reads {measured[name]} ticks (allowed {low}–{high})"
                    for name, (low, high) in self._limits.items()
                    if not low <= measured[name] <= high
                ]
                if outside_range:
                    details = ", ".join(outside_range)
                    raise RuntimeError(f"Arm startup refused with calibration {calib_path}. {details}.")
            if self._home_offsets is None:
                self._home_offsets = measured.copy()
            self.current_commands = self._positions_in_radians(measured)
            self.bus.configure_motors()
            # Use acknowledged writes so a motor cannot start with a stale goal.
            for name in JOINTS:
                self.bus.write("Goal_Position", name, measured[name], normalize=False)
            torque_requested = True
            self.bus.enable_torque()
        except Exception:
            if self.bus.is_connected:
                self.bus.disconnect(disable_torque=torque_requested)
            raise
        self.get_logger().info("Motor bus connected and holding measured joint positions.")

        # Timer for periodic read/write (50 Hz)
        self.timer = self.create_timer(0.02, self._timer_cb)

    def _positions_in_radians(self, raw_positions):
        return {
            name: (raw_positions[name] - self._home_offsets.get(name, 0)) / self._steps_per_rad
            for name in JOINTS
        }

    # ---------------------------------------------------------------------
    # Callbacks
    # ---------------------------------------------------------------------
    def _command_cb(self, msg: JointState):
        """Store desired joint positions from topic (rad)."""
        for name, pos in zip(msg.name, msg.position):
            if name in self.current_commands and math.isfinite(pos):
                self.current_commands[name] = pos

    def _timer_cb(self):
        # --- Read present positions
        try:
            raw_positions = self.bus.sync_read("Present_Position", normalize=False)

            positions = self._positions_in_radians(raw_positions)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"sync_read failed: {exc}")
            if self.stop_on_bus_error:
                raise
            return

        # Publish joint states
        js = JointState()
        js.header.stamp = self.get_clock().now().to_msg()
        js.name = list(JOINTS.keys())
        js.position = [positions[n] for n in js.name]
        js.velocity = []
        js.effort = []
        self.joint_states_pub.publish(js)

        # --- Write goal positions
        try:
            # convert desired rad to raw steps relative to home
            raw_goals = {}
            for n, rad in self.current_commands.items():
                home = self._home_offsets.get(n, 0) if self._home_offsets else 0
                raw = home + rad * self._steps_per_rad
                # clamp to limits if available
                if self._limits and n in self._limits:
                    low, high = self._limits[n]
                    raw = max(low, min(high, raw))
                raw_goals[n] = round(raw)
            self.bus.sync_write("Goal_Position", raw_goals, normalize=False)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"sync_write failed: {exc}")
            if self.stop_on_bus_error:
                raise


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def main():  # noqa: D401
    """Entry-point."""
    rclpy.init()
    node = None
    try:
        node = MotorBridge()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if node is not None:
                try:
                    node.bus.disconnect()
                finally:
                    node.destroy_node()
        finally:
            rclpy.try_shutdown()


if __name__ == "__main__":
    main()
