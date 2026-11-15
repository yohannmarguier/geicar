"""ROS 2 service controlled dance demo; no motion on startup by default."""

import math
import time

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

from .bus import FeetechBus, SimulatedBus
from .motion import targets_at, within_limits


class DanceNode(Node):
    def __init__(self):
        super().__init__("so_arm101")
        defaults = {
            "port": "/tmp/so101",
            "baudrate": 1_000_000,
            "motor_ids": [1, 5],
            "amplitudes_ticks": [200, 240],
            "frequency_hz": 0.08,
            "duration_seconds": 12.5,
            "update_rate_hz": 10.0,
            "speed": 200,
            "acceleration": 10,
            "minimum_tick": 128,
            "maximum_tick": 3967,
            "dry_run": False,
            "start_on_launch": False,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)
        values = {name: self.get_parameter(name).value for name in defaults}
        self.motor_ids = list(values["motor_ids"])
        self.amplitudes = list(values["amplitudes_ticks"])
        self.frequency = values["frequency_hz"]
        self.duration = values["duration_seconds"]
        self.speed = values["speed"]
        self.acceleration = values["acceleration"]
        self.minimum_tick = values["minimum_tick"]
        self.maximum_tick = values["maximum_tick"]
        self.dry_run = values["dry_run"]
        self._validate(values)

        self.bus = (
            SimulatedBus(self.motor_ids)
            if self.dry_run
            else FeetechBus(values["port"], values["baudrate"])
        )
        try:
            initial_positions = self.bus.read_positions(self.motor_ids)
        except Exception:
            self.bus.close()
            raise
        self.active = False
        self.start_ticks = []
        self.started_at = 0.0
        self.steps = 0
        self.observed_min = []
        self.observed_max = []
        self.create_service(Trigger, "~/start", self._start)
        self.create_service(Trigger, "~/stop", self._stop)
        self.create_timer(1.0 / values["update_rate_hz"], self._step)
        self.get_logger().info(f"Current raw motor ticks: {initial_positions}")
        self.get_logger().info("Ready. Call /so_arm101/start to dance; /so_arm101/stop to hold.")
        if values["start_on_launch"]:
            started, message = self.start_dance()
            if not started:
                self.get_logger().error(f"Dance was not started: {message}")

    def _validate(self, values):
        if not self.motor_ids or len(self.motor_ids) != len(self.amplitudes):
            raise ValueError("motor_ids and amplitudes_ticks need equal, nonzero lengths")
        if len(set(self.motor_ids)) != len(self.motor_ids) or any(
            motor_id not in range(1, 6) for motor_id in self.motor_ids
        ):
            raise ValueError("motor_ids must be distinct SO-101 body motors 1 through 5")
        if any(not 1 <= amplitude <= 256 for amplitude in self.amplitudes):
            raise ValueError("amplitudes_ticks must each be 1 through 256")
        if not math.isfinite(self.frequency) or not 0.05 <= self.frequency <= 0.5:
            raise ValueError("frequency_hz must be 0.05 through 0.5")
        if not math.isfinite(self.duration) or not 0 < self.duration <= 15:
            raise ValueError("duration_seconds must be greater than zero and at most 15")
        if not math.isfinite(values["update_rate_hz"]) or not 2 <= values["update_rate_hz"] <= 20:
            raise ValueError("update_rate_hz must be 2 through 20")
        if not 1 <= self.speed <= 200 or not 0 <= self.acceleration <= 50:
            raise ValueError("speed must be 1-200 and acceleration 0-50")
        if not 0 <= self.minimum_tick < self.maximum_tick <= 4095:
            raise ValueError("tick limits must be ordered within 0 through 4095")

    def start_dance(self):
        if self.active:
            return False, "Already dancing"
        try:
            start_ticks = self.bus.read_positions(self.motor_ids)
        except Exception as exc:
            return False, f"Cannot read motor positions: {exc}"
        if not within_limits(
            start_ticks, self.amplitudes, self.minimum_tick, self.maximum_tick
        ):
            return False, "Current position is too close to a configured tick limit"
        try:
            self.bus.enable_motion(
                self.motor_ids, start_ticks, self.speed, self.acceleration
            )
        except Exception as exc:
            return False, f"Cannot enable motor torque: {exc}"
        self.start_ticks = start_ticks
        self.observed_min = start_ticks.copy()
        self.observed_max = start_ticks.copy()
        self.started_at = time.monotonic()
        self.steps = 0
        self.active = True
        self.get_logger().info(f"Dance started from raw ticks {start_ticks}")
        return True, "Dance started"

    def stop_dance(self):
        if not self.active:
            return False, "Already stopped"
        self.active = False
        try:
            current = self.bus.read_positions(self.motor_ids)
            self.bus.write_positions(
                self.motor_ids, current, self.speed, self.acceleration
            )
        except Exception as exc:
            self.get_logger().error(f"Could not command a position hold: {exc}")
            return False, f"Stopped sending dance targets; position hold failed: {exc}"
        self.get_logger().info("Dance stopped; holding measured position")
        self.get_logger().info(
            f"Observed raw tick ranges: {list(zip(self.observed_min, self.observed_max))}"
        )
        return True, "Holding measured position"

    def _start(self, request, response):
        response.success, response.message = self.start_dance()
        return response

    def _stop(self, request, response):
        response.success, response.message = self.stop_dance()
        return response

    def _step(self):
        if not self.active:
            return
        elapsed = time.monotonic() - self.started_at
        if elapsed >= self.duration:
            self.stop_dance()
            return
        targets = targets_at(
            self.start_ticks, self.amplitudes, self.frequency, elapsed
        )
        try:
            self.bus.write_positions(
                self.motor_ids, targets, self.speed, self.acceleration
            )
            self.steps += 1
            if self.steps % 5 == 0:
                observed = self.bus.read_positions(self.motor_ids)
                self.observed_min = [min(a, b) for a, b in zip(self.observed_min, observed)]
                self.observed_max = [max(a, b) for a, b in zip(self.observed_max, observed)]
            if self.dry_run and self.steps % 10 == 0:
                self.get_logger().info(f"Dry-run raw targets: {targets}")
        except Exception as exc:
            self.active = False
            self.get_logger().error(f"Dance halted after bus error: {exc}")

    def shutdown(self):
        self.stop_dance()
        try:
            self.bus.disable_torque(self.motor_ids)
        except Exception as exc:
            self.get_logger().error(f"Could not disable motor torque: {exc}")
        self.bus.close()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = DanceNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.shutdown()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
