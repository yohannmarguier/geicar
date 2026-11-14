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

This macOS container does not expose the car's CAN bus, camera, lidar, joystick,
or arm. Docker Desktop's networking and device access differ from Linux on the
car. Validate hardware and ROS communication on the target Pi/Jetson after local
builds. The pre-existing Jetson `ros-humble` container described in the board
guide is a separate deployment environment.
