# SO-101 Docker environment

Run the SO-101 arm from a Docker host on Linux, macOS, or Windows with WSL 2
using the steps below. The image builds the Jetson workspace's three
`so101_*` packages on Ubuntu 22.04 for ARM64 or x86-64. It includes ROS 2
Humble Desktop, RViz, MoveIt, ros2_control, and the Feetech SDK. RViz runs in
the same container as MoveIt and the motor bridge. You interact with it in
your browser. The optional MongoDB warehouse launch requires a separate
setup because its Humble package is unavailable for Jammy. See the
[official ROS image tags](https://github.com/docker-library/official-images/blob/master/library/ros)
and the [warehouse compatibility issue](https://github.com/moveit/warehouse_ros_mongo/issues/75).

## Build and verify

With Docker running, build from the repository root. This copies the current
package sources into the image. Rebuild after changing them.

```bash
docker build -f ressources/Dockerfile -t geicar-so101 .
docker run --rm geicar-so101 ros2 pkg list | grep '^so101_'
docker run --rm -it --init --name geicar-so101 \
  -p 127.0.0.1:6080:6080 geicar-so101 so101-rviz use_fake_hardware:=true
```

The package list should show `so101_follower_description`,
`so101_follower_moveit`, and `so101_hw_interface`. Open
[RViz in your browser](http://localhost:6080/vnc.html?autoconnect=1). The
mock launch should activate the trajectory controllers and report that
MoveIt is ready. Leave it running and send the example planning goal from
another terminal.

```bash
docker exec -it geicar-so101 bash -c '
  source /opt/so101_ws/install/setup.bash
  goal_file="$(ros2 pkg prefix --share so101_follower_moveit)/config/example_position_goal.yaml"
  ros2 action send_goal /move_action moveit_msgs/action/MoveGroup "$(cat "$goal_file")"
'
```

Look for `SUCCEEDED` and a MoveIt error code of `1` in the result. Ctrl+C
in the launch terminal stops the demo.

## Physical arm on Linux

Connect the USB adapter to the computer running Docker Engine. If it appears
as `/dev/ttyUSB0` or under `/dev/serial/by-id/`, change `serial_device`.
Docker maps that device to `/dev/ttyACM0` inside the container. Stop the mock
container and any other process using the serial adapter before launching.

```bash
serial_device=/dev/ttyACM0
docker run --rm -it --init --name geicar-so101 \
  --device "$serial_device:/dev/ttyACM0" \
  -p 127.0.0.1:6080:6080 \
  geicar-so101 so101-rviz use_fake_hardware:=false
```

The physical launch enables torque as soon as it connects to the arm.
Verify the current joint positions and calibration before launching, then
open [RViz in your browser](http://localhost:6080/vnc.html?autoconnect=1).
If you use a custom calibration,
add `-v /absolute/path/to/calibration.yaml:/calibration.yaml:ro` before the
image name and `calib_file:=/calibration.yaml` after the launch arguments.
Ctrl+C in the launch terminal stops MoveIt and the motor bridge. Closing the
browser only disconnects the display. Keep the physical power switch
accessible in case the arm loses serial communication with torque enabled.
[Physical arm launch and stop behavior](../jetsonNano/ros2_ws/src/so101_follower_moveit/README.md#physical-arm)

## Physical arm on macOS

Use Docker Desktop and the repository's serial bridge. On the Mac, from the
repository root, set up the bridge once, then start it with the actual
`/dev/cu.*` device for the adapter.
[Docker Desktop USB support](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/general/#can-i-pass-through-a-usb-device-to-a-container)

```bash
python3 -m venv docker/ros2/.venv
docker/ros2/.venv/bin/python -m pip install pyserial
docker/ros2/.venv/bin/python docker/ros2/so101_serial_host.py --device /dev/cu.usbmodemXXXX
```

Leave the bridge running. Start the container from another terminal, then
open the same browser address. The container connects to the bridge through
`host.docker.internal` and hands the motor bridge a Linux serial device at
`/tmp/so101`. Use the same calibration and shutdown procedure as on Linux.
[Existing serial bridge guide](../docker/ros2/README.md#so-101-arm-connected-to-the-mac)

```bash
docker run --rm -it --init --name geicar-so101 \
  -e SO101_SERIAL_TCP=host.docker.internal:54321 \
  -p 127.0.0.1:6080:6080 \
  geicar-so101 so101-rviz use_fake_hardware:=false
```

## Physical arm on Windows

Attach the adapter to WSL 2 with `usbipd-win` and run Docker Engine inside
the WSL distribution that can see the device. Once it shows up under
`/dev/ttyACM*` or `/dev/ttyUSB*`, use the Linux command in WSL and open
RViz in your Windows browser. Verify that your Docker CLI is connected to
the engine inside WSL so `--device` can access the adapter from that
distribution. [Microsoft USB setup for WSL](https://learn.microsoft.com/en-us/windows/wsl/connect-usb)

## Read encoders without enabling torque

With the motor bridge stopped, on Linux or WSL run:

```bash
docker run --rm -it --device "$serial_device:/dev/ttyACM0" geicar-so101 \
  ros2 run so101_hw_interface so101_read_steps --port /dev/ttyACM0 --once
```

On macOS, first run the macOS command with `use_fake_hardware:=true`. The
container opens the serial connection while MoveIt uses the mock arm.
Then run the encoder reader from a second terminal.

```bash
docker exec -it geicar-so101 bash -c '
  source /opt/so101_ws/install/setup.bash
  ros2 run so101_hw_interface so101_read_steps --port /tmp/so101 --once
'
```
