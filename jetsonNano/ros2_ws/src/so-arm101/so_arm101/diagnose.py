"""Read SO-101 motor status, with an optional bounded response check."""

import argparse
import time

from .bus import FeetechBus


def status(bus, motor_id):
    position = bus.read_positions([motor_id])[0]
    return {
        "position_ticks": position,
        "goal_ticks": bus.read_register(motor_id, 42, 2) & 0x7FFF,
        "operating_mode": bus.read_register(motor_id, 33),
        "phase": bus.read_register(motor_id, 18),
        "torque_enabled": bus.read_register(motor_id, 40),
        "acceleration": bus.read_register(motor_id, 41),
        "speed": bus.read_register(motor_id, 46, 2),
        "torque_limit": bus.read_register(motor_id, 48, 2),
        "voltage_v": bus.read_register(motor_id, 62) / 10.0,
        "status_flags": bus.read_register(motor_id, 65),
        "moving": bus.read_register(motor_id, 66),
    }


def step_response(bus, motor_id, offset_ticks, seconds, speed, acceleration):
    before = status(bus, motor_id)
    print(f"before: {before}", flush=True)
    if before["status_flags"] != 0:
        raise RuntimeError("Motor reports a fault; no step command sent")
    if before["voltage_v"] < 4.0:
        raise RuntimeError("Motor voltage is below 4.0 V; no step command sent")
    target = before["position_ticks"] + offset_ticks
    if not 128 <= target <= 3967:
        raise RuntimeError("Target outside conservative tick bounds; no step command sent")

    samples = []
    voltages = []
    bus.enable_motion([motor_id], [before["position_ticks"]], speed, acceleration)
    try:
        bus.write_positions([motor_id], [target], speed, acceleration)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            time.sleep(0.1)
            samples.append(bus.read_positions([motor_id])[0])
            voltages.append(bus.read_register(motor_id, 62) / 10.0)
    finally:
        try:
            bus.write_positions(
                [motor_id], [before["position_ticks"]], speed, acceleration
            )
            return_deadline = time.monotonic() + 5.0
            while time.monotonic() < return_deadline:
                if abs(bus.read_positions([motor_id])[0] - before["position_ticks"]) <= 12:
                    break
                time.sleep(0.1)
        finally:
            bus.disable_torque([motor_id])

    excursion = max(abs(sample - before["position_ticks"]) for sample in samples)
    print(f"target={target} samples={samples} max_excursion_ticks={excursion} "
          f"minimum_voltage_v={min(voltages)}", flush=True)
    after = status(bus, motor_id)
    print(f"after: {after}", flush=True)
    if abs(after["position_ticks"] - before["position_ticks"]) > 12:
        raise RuntimeError("Motor did not return near its starting position")
    if excursion < abs(offset_ticks) / 2:
        raise RuntimeError("Motor followed less than half the commanded step")
    print("PASS: motor followed at least half the commanded step", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/tmp/so101")
    parser.add_argument("--baudrate", type=int, default=1_000_000)
    parser.add_argument("--motor-id", type=int, default=5)
    parser.add_argument("--step-ticks", type=int, default=0)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--speed", type=int, default=30)
    parser.add_argument("--acceleration", type=int, default=10)
    args = parser.parse_args()
    if args.motor_id not in range(1, 6):
        parser.error("motor-id must be a body motor, 1 through 5")
    if abs(args.step_ticks) > 128:
        parser.error("step-ticks must be between -128 and 128")
    if not 0 < args.seconds <= 5:
        parser.error("seconds must be greater than zero and at most 5")
    if not 1 <= args.speed <= 200 or not 0 <= args.acceleration <= 50:
        parser.error("speed must be 1-200 and acceleration 0-50")

    bus = FeetechBus(args.port, args.baudrate)
    try:
        if args.step_ticks:
            step_response(
                bus, args.motor_id, args.step_ticks, args.seconds,
                args.speed, args.acceleration,
            )
        else:
            print(status(bus, args.motor_id), flush=True)
    finally:
        bus.close()


if __name__ == "__main__":
    main()
