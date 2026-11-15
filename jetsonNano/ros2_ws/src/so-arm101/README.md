# SO-101 dance demo

This ROS 2 Humble package controls a **powered SO-101 follower** through its
Feetech STS3215 serial bus. Its small demo moves the base (`shoulder_pan`, motor
ID 1) and wrist roll (motor ID 5) in opposite, smooth waves for 12.5 seconds.
The gripper is never commanded. The package is deliberately separate from the
vehicle startup launch file and does not implement litter collection or a
general arm controller.

The folder is named `so-arm101` as requested. The ROS package and Python module
are named `so_arm101` because ROS package names use underscores rather than
hyphens.

## Dependencies and hardware

- Ubuntu 22.04 with ROS 2 Humble, `rclpy`, and `std_srvs`.
- The official `ftservo-python-sdk` 2.0.1 Python package and `pyserial`.
- A powered SO-101 follower with six configured STS3215 motors. The demo uses
  IDs 1 and 5, matching the standard SO-101 follower mapping. Confirm your arm
  variant, motor IDs, calibration, power supply, and clear working area before
  allowing motion. The script does **not** calibrate the arm or discover its
  mechanical limits.
- On macOS Docker Desktop, start the [serial bridge](../../../../docker/ros2/README.md#so-101-arm-connected-to-the-mac)
  first. It provides `/tmp/so101` in the Jetson development container. On the
  real Jetson, use that board's actual serial path (often `/dev/ttyACM0`) and
  device permissions; the Mac bridge is only for local development.

From the repository root, rebuild the Docker image after adding this package:

```sh
docker compose build raspberry
```

In the Jetson container, build from its own workspace root:

```sh
colcon build --packages-select so_arm101
source install/local_setup.bash
ros2 pkg executables so_arm101
```

On the Jetson target, install `ftservo-python-sdk==2.0.1` into the same Python
environment as ROS 2 and use the board's workspace build guide. The Docker
image installs the SDK and serial dependency for local development.

## Try it without moving hardware

Run this in a normal Jetson development shell. `dry_run` uses a simulated bus
with starting positions of 2048 raw ticks; `start_on_launch` runs one dance:

```sh
ros2 run so_arm101 dance_node --ros-args \
  -p dry_run:=true -p start_on_launch:=true
```

The node logs the starting positions and sampled target positions, then stops
after 12.5 seconds. Press Ctrl-C to stop early. This verifies ROS package
discovery, parameter handling, and the motion sequence without opening a port.

## Run with the follower arm

Start the Mac serial bridge and enter the Jetson shell as described above. With
the powered arm mounted, clear of obstacles, and near the middle of each joint's
range, run:

```sh
ros2 run so_arm101 dance_node --ros-args -p port:=/tmp/so101
```

Starting the node opens the port and reads the selected motor positions. It does
not command motion. Starting a dance checks position mode, supply voltage and
protection flags, writes each motor's measured position as its goal, then
enables torque. From another ROS shell in the same ROS domain, request one dance:

```sh
ros2 service call /so_arm101/start std_srvs/srv/Trigger '{}'
```

Or, for a one-command run after checking the arm, add
`-p start_on_launch:=true` to the node command. To interrupt a dance, press
Ctrl-C in the node terminal or call:

```sh
ros2 service call /so_arm101/stop std_srvs/srv/Trigger '{}'
```

The node reads current motor positions before starting and refuses to run if
its planned offsets would leave the configured raw tick range. The two targets
stay within 200 and 240 ticks of their measured starting positions, respectively
(about 18° at the base and 21° at the wrist). The wave frequency is 0.08 Hz and
commands are sent at 10 Hz. On a normal stop
or completion, it reads and commands the current positions to hold them. On a
serial error, it stops sending dance targets and reports the error; the motors
may retain their last goal. Use the arm's physical power control if a software
stop cannot reach it. On node exit, torque is disabled; support the arm if it
could sag under its own weight. A completed dance holds its final position.

For read-only motor status, run `ros2 run so_arm101 diagnose --port /tmp/so101`
in the bridged Jetson shell. For a bounded wrist response test, run:

```sh
ros2 run so_arm101 diagnose --port /tmp/so101 --step-ticks 100 --speed 120
```

This enables torque at the measured position, requests a 100-tick wrist step,
measures motion and voltage, requests the starting position again, then disables
torque. It fails if the motor moves less than 50 ticks or ends more than 12 ticks
from its start. Keep the arm clear and supported.

## ROS interface and configuration

Node name: `/so_arm101`. Services: `/so_arm101/start` and `/so_arm101/stop`,
both `std_srvs/srv/Trigger`. There are no topics, actions, or coordinate frames
in this demo. Positions are **raw motor encoder ticks**, not joint angles.

| Parameter | Default | Meaning |
| --- | --- | --- |
| `port` | `/tmp/so101` | Linux serial path. |
| `baudrate` | `1000000` | Servo bus bits per second; the Mac host bridge must match. |
| `motor_ids` | `[1, 5]` | Body motors to wave. IDs 1–5 only; gripper ID 6 is disallowed. |
| `amplitudes_ticks` | `[200, 240]` | Maximum movement from each starting position; each value limited to 1–256 ticks. |
| `frequency_hz` | `0.08` | Wave cycles per second, limited to 0.05–0.5. |
| `duration_seconds` | `12.5` | One dance length, at most 15 seconds. |
| `update_rate_hz` | `10.0` | Command rate, limited to 2–20 Hz. |
| `speed` | `200` | Feetech SDK speed register value, limited to 1–200. This arm's phase setting uses the fine 0.0146 RPM unit. |
| `acceleration` | `10` | Feetech SDK acceleration register value, limited to 0–50. |
| `minimum_tick`, `maximum_tick` | `128`, `3967` | Conservative raw command bounds; not calibrated joint limits. |
| `dry_run` | `false` | Simulate the bus without opening hardware. |
| `start_on_launch` | `false` | Start a dance after connecting. |

Validation on the connected Mac arm: the package built in the Jetson Docker
container and unit tests passed. Both IDs 1 and 5 initially reported torque
disabled, position mode, no faults, and about 4.9–5.0 V. The earlier dance sent
targets without enabling torque, explaining the barely visible movement; its
small start/end encoder difference did **not** prove the motors followed commands.
After fixing torque setup, a 100-tick wrist step at speed 120 reached 92 ticks
of measured excursion, with minimum observed voltage 4.9 V. One physical
twelve-second dance produced measured ranges of 1815–1962 ticks (base) and
2053–2233 ticks (wrist), without bus errors. Visual motion, collision clearance,
calibration, power-supply rating, and repeatability still need direct human
verification. The 5 V reading is consistent with the 5 V supply recommended
for 7.4 V SO-101 motors; confirm the actual motor and adapter variant before
changing supplies.

After feedback that this motion was too subtle, the default amplitudes were
raised to 200 and 240 ticks and the speed to 200 while lowering the wave
frequency to 0.08 Hz. A physical 12.5-second run measured 1446–1822 ticks at
the base and 1841–2297 ticks at the wrist (376 and 456 ticks of range), with no
reported bus errors. A follow-up status read showed torque disabled, 4.9 V,
and no fault. These encoder readings confirm motion; visual quality and physical
clearance still need to be checked at the arm. Do not increase amplitudes
further without confirming calibrated joint and collision limits.
