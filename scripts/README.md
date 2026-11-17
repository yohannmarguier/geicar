# Car SSH connection

Run `bash scripts/ssh-connection.sh MODE PI_ADDRESS` from your computer, replacing
`PI_ADDRESS` with the car's reachable Raspberry Pi address. The computer needs
OpenSSH with jump-host (`-J`) support and network access to the Pi. The inherited
setup connects the Jetson at `192.168.1.10` through the Pi; verify these addresses
against your car.

- `pi` opens a shell on the Pi.
- `jetson` opens a shell on the Jetson through the Pi.
- `docker` starts the existing `ros-humble` container on the Jetson and launches
  `geicar_start_jetson geicar.jetson.launch.py` inside it. It expects ROS Humble
  and the built workspace at `~/ros2_ws` inside the container, as in the Jetson
  build guide. Stop the launch with Ctrl-C; the container remains running.

For example: `bash scripts/ssh-connection.sh jetson 10.105.1.42`.
SSH and sudo may prompt for passwords; SSH keys configured on both hosts can
avoid SSH password prompts. Passwords are not passed as script arguments. X11
forwarding is requested and requires a working X server where needed.

To verify, connect in `pi` mode and check the prompt, then use `jetson` mode and
check the Jetson prompt. For `docker` mode, verify the launch output and the
camera and lidar on the car. Hardware and container configuration must be checked
on the target; a successful SSH connection alone does not verify sensors.
