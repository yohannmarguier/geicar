#!/usr/bin/env python3
"""Simple helper to dump raw *Present_Position* of all SO-101 follower servos.

Usage
-----
ros2 run so101_hw_interface so101_read_steps [--port /dev/ttyACM0]

The script prints a YAML dictionary mapping joint names to their current raw
encoder counts (0-4095).  This is useful when calibrating or debugging the
URDF → servo mapping.
"""
from __future__ import annotations

import argparse
import sys
import yaml

from so101_hw_interface.motor_bridge import FeetechMotorsBus, JOINTS, Motor, MotorNormMode


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> None:  # noqa: D401
    """Entry-point for *so101_read_steps*."""
    parser = argparse.ArgumentParser(
        prog="so101_read_steps",
        description="Read raw Present_Position of all SO-101 follower servos and print as YAML.",
    )
    parser.add_argument(
        "--port",
        default="/dev/ttyACM0",
        help="Serial port to which the Feetech bus is connected (default: /dev/ttyACM0)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Read once and exit. If omitted the script keeps printing every second.",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="Polling rate in Hz when running continuously (default: 1.0)",
    )
    args = parser.parse_args()

    motors = {
        name: Motor(cfg["id"], cfg["model"], MotorNormMode.DEGREES) for name, cfg in JOINTS.items()
    }

    try:
        bus = FeetechMotorsBus(args.port, motors)
        bus.connect()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not connect to bus on {args.port}: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        import time

        def _read_and_print() -> None:
            pos_raw = bus.sync_read("Present_Position", normalize=False)
            print(yaml.safe_dump(pos_raw, sort_keys=False))

        if args.once:
            _read_and_print()
        else:
            period = 1.0 / max(args.rate, 0.01)
            while True:
                start = time.time()
                _read_and_print()
                elapsed = time.time() - start
                time.sleep(max(0.0, period - elapsed))
    finally:
        bus.disconnect(disable_torque=False)


if __name__ == "__main__":
    main()
