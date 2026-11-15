# ROS 2 Humble development on macOS

This Docker setup provides Ubuntu 22.04 and ROS 2 Humble for editing and building
the Raspberry Pi and Jetson ROS workspaces on a Mac. It is a **local development
environment**, not the container running on the car's Jetson. Docker Desktop for
Mac is required and must be running. Both Apple Silicon and Intel Macs use the
architecture supported by their Docker installation; a local build does not
replace a build and test on the target boards.

From the repository root, build the image once:

```sh
docker compose build raspberry
```

Open a shell in either workspace:

```sh
docker compose run --rm raspberry
docker compose run --rm jetson
```

The repository is mounted at `/project`, so edits made on the Mac appear in the
container immediately. The shell starts in the selected `ros2_ws` directory.
The ROS base environment is sourced by the image entrypoint. Each workspace
has its own Docker volumes for `build/`, `install/`, and `log/`; these survive
`run --rm` and keep Linux build products off the Mac filesystem. Do not build
the repository root as one workspace: both workspaces contain `interfaces`.

The image installs the dependencies declared in both workspaces' `package.xml`
files through `rosdep`. Rebuild with `docker compose build raspberry` after
changing package dependencies. Source edits take effect immediately through
the bind mount. The image skips the inherited `joystick_ros2` rosdep key:
`geicar_start/package.xml` names it, while the workspace builds the joystick
node inside the `joystick` package.

Then build. In the Raspberry shell, start with the shared messages and build
other packages individually as described in
[`raspberryPI3/ros2_ws/how_to_compile.md`](../../raspberryPI3/ros2_ws/how_to_compile.md):

```sh
colcon build --packages-select interfaces
source install/local_setup.bash
colcon build --packages-up-to car_control
source install/local_setup.bash
ros2 pkg list | grep car_control
```

In the Jetson shell, follow
[`jetsonNano/ros2_ws/how_to_compile.md`](../../jetsonNano/ros2_ws/how_to_compile.md):

```sh
colcon build --packages-select interfaces
source install/local_setup.bash
colcon build --packages-up-to usb_cam
source install/local_setup.bash
ros2 pkg list | grep usb_cam
```

Source `install/local_setup.bash` again in each new shell after a successful
build. The `ros2 pkg list` checks confirm package discovery, not sensor or car
operation. If `rosdep` reports an unresolved key during image build, inspect
that package and its component guide before adding or changing dependencies.

## SO-101 arm connected to the Mac

Docker Desktop for Mac [does not directly pass USB devices](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/general/#can-i-pass-through-a-usb-device-to-a-container)
to a Linux container. The optional bridge below opens the serial port on the Mac and gives
the Jetson container a Linux pseudo-terminal at `/tmp/so101`. This is only a
byte transport; the optional [SO-101 dance package](../../jetsonNano/ros2_ws/src/so-arm101/README.md)
uses that path for a bounded motion demo. Use the container path, not the macOS
`/dev/cu.*` path inside the container.

On the Mac, install the host bridge's one Python dependency and start it in a
terminal from the repository root:

```sh
python3 -m venv docker/ros2/.venv
docker/ros2/.venv/bin/python -m pip install pyserial
docker/ros2/.venv/bin/python docker/ros2/so101_serial_host.py \
  --device /dev/cu.usbmodem5AA90177351
```

Leave that terminal running. The host bridge listens only on Mac loopback port
54321 and opens the serial port at 1,000,000 baud when the container connects.
In a second Mac terminal, rebuild the image once to add `socat`, then open the
Jetson shell with the bridge:

```sh
docker compose build raspberry
docker compose run --rm jetson bash /project/docker/ros2/jetson_so101_shell.sh
```

Inside that shell, verify that the device exists without sending motor commands:

```sh
ls -l /tmp/so101
```

Press Ctrl-D to leave the shell and Ctrl-C in the Mac bridge terminal to stop.
Only one program should open `/tmp/so101` at a time. The Mac bridge holds the
physical port while connected; close any Mac program using the arm first. If
the device name changes after reconnecting USB, update `--device`. If your
arm's configured baud rate differs, pass the same `--baudrate` to the Mac
script. The Linux pseudo-terminal's baud setting does not change the physical
port speed on the Mac. The bridge forwards serial bytes as soon as they arrive
and disables TCP small-packet buffering, but it still adds a Mac-to-Docker hop.
Actual arm round-trip latency has not been measured. Do motor setup,
calibration, and motion tests only with
the correct arm variant, power supply, and joint limits confirmed.

The macOS container still does not expose the car's CAN bus, camera, lidar, or
joystick. Docker Desktop's networking and device access differ from Linux on
the car. Validate hardware and ROS communication on the target Pi/Jetson after
local builds. The pre-existing Jetson `ros-humble` container described in the
board guide is a separate deployment environment.
