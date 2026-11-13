# EcoCar contributor guide

## Project context

This repository is a fork of the teacher-provided GeiCar platform for a student
group project. The vehicle is approximately one metre long and contains several
computers, microcontrollers, sensors, and actuators. ROS 2 connects the onboard
software; lower-level hardware communication also uses CAN and, for some board
variants, serial connections.

The group's EcoCar goal is to:

1. Automate the movement of the car.
2. Detect litter (cans, cups, tissues, and bottles) using a camera assisted by lidar.
3. Approach the litter and pick it up with a robotic arm.
4. Deposit collected litter in a trashcan.

The inherited code provides the basics of the car. Treat autonomous navigation,
litter perception/localization, arm control, and the collection sequence as project
features to implement and validate, not as capabilities already delivered by the
base platform. Camera experiments in `jetsonNano/playground/` are not evidence of
an integrated litter-collection system. Confirm the arm hardware and interfaces
before designing its integration.

## Read component documentation first

**Documentation and explanations live in the folder of each component. Read them
before changing that component to understand what it does and how to use it.**
Start with [README.md](README.md) for the inherited platform overview, then use:

| Area | Purpose and documentation entry points |
| --- | --- |
| `general/` | Vehicle operation: [how_to_use.md](general/how_to_use.md). Development: [software_development_tips.md](general/software_development_tips.md). Troubleshooting: [debugging_help.md](general/debugging_help.md). CAN protocol: [can_description.md](general/software/can/can_description.md). |
| `raspberryPI3/` | Vehicle control, joystick input, CAN communication, system checks, and simulation integration. Read [initial_configuration.md](raspberryPI3/initial_configuration.md) and [ros2_ws/how_to_compile.md](raspberryPI3/ros2_ws/how_to_compile.md); packages are in `ros2_ws/src/`. |
| `jetsonNano/` | Camera, lidar, and perception work. Read [initial_configuration.md](jetsonNano/initial_configuration.md) and [ros2_ws/how_to_compile.md](jetsonNano/ros2_ws/how_to_compile.md). Driver guides: [usb_cam](jetsonNano/ros2_ws/src/usb_cam/README.md) and [rplidar_ros2](jetsonNano/ros2_ws/src/rplidar_ros2/README.md). |
| `nucleoF103/` | Motor and steering control, power, and ultrasonic sensors. Read [software_description.md](nucleoF103/documentation/software/software_description.md) and the hardware documents in `documentation/`. |
| `nucleoL476/` | GPS and IMU firmware. Read [README.md](nucleoL476/README.md) and [initial_configuration.md](nucleoL476/initial_configuration.md). |
| `carte-imu-gps-freertos/` | FreeRTOS sensor-board implementation. Read [how_to_use.md](carte-imu-gps-freertos/how_to_use.md), including its serial frame format and application structure. |
| `carte-moteurs-ultrasons-freertos/` | FreeRTOS motor/ultrasonic-board implementation. Inspect `Application/` and the STM32 project configuration; add a component guide when working here if none exists. |
| `simulation/` | CARLA setup and the limitations of the existing simulation example: [README.md](simulation/README.md). ROS simulation packages are in the Raspberry Pi workspace. |

The original and FreeRTOS firmware trees are distinct implementations. Establish
which one is deployed on the group's car before modifying firmware or assuming a
protocol. Existing guides describe the inherited setup and may contain outdated
commands, addresses, or hardware assumptions; check them against the relevant
source, launch files, and actual target environment.

## Keep documentation with the implementation

- Every new component or ROS package owned by the group should have a local
  `README.md` explaining its purpose and how to use it. Extend existing local
  guides rather than duplicating them unnecessarily.
- When changing a component, update its documentation in the same change. Include
  dependencies and target hardware, setup/build steps, configuration, run/launch
  commands, expected behavior, and a practical verification procedure.
- Document ROS nodes, topics, services/actions, message types, parameters, units,
  and coordinate frames where applicable. For hardware interfaces, document
  connections, device names, protocol details, and calibration requirements.
- Clearly distinguish implemented and tested behavior from experiments, planned
  work, known limitations, and assumptions requiring hardware verification.
- Add new component documentation to the table above so teammates can find it.
  Keep explanations accessible to students who did not write the component.

## Development conventions

- Extend the existing platform in focused changes. Preserve teacher/upstream
  attribution and avoid unrelated rewrites of drivers or generated STM32 code.
- Most EcoCar work belongs on the Raspberry Pi and Jetson side. Change MCU
  firmware only when the feature requires it and the deployed variant is known.
- The repository's development guides target ROS 2 Humble. Verify the target
  environment before adding dependencies or using APIs from another distribution.
- Build each ROS workspace separately, from its own `ros2_ws/` root. Do not treat
  this repository as a single colcon workspace: both workspaces contain packages
  with the same names, including `interfaces`.
- Keep shared message definitions compatible across the Raspberry Pi and Jetson
  copies of `interfaces`; update and rebuild affected consumers when they change.
- Follow the local style of the C/C++, Python, launch, and configuration files.
  Check actual `package.xml`, `CMakeLists.txt`, and launch definitions for package
  and executable names rather than inferring them from directory names.
- Preserve existing stop behavior, manual control, calibration, and hardware
  limits when adding autonomous behavior. Document failure and stop behavior for
  new motion or manipulation features.
- Keep datasets, model weights, training output, disk images, and generated build
  artifacts out of ordinary source changes unless explicitly needed. Do not
  overwrite unrelated local work or assume resource/export copies are deployed
  source trees.

## Build and verification

Follow the component's build guide. In a configured ROS 2 Humble environment,
source `/opt/ros/humble/setup.bash` before building and source the workspace's
`install/local_setup.bash` afterward. On the Raspberry Pi, build `interfaces`
first and build packages individually because memory is limited. The Jetson guide
describes building inside its `ros-humble` Docker container. STM32 firmware uses
STM32CubeIDE and the corresponding board project.

For software changes, build the affected packages and run relevant existing tests
in a compatible environment. Validate new behavior with focused tests, recorded
inputs, or simulation where practical before physical trials. The existing CARLA
example is only a starting point, not a complete EcoCar simulation.

Report what was checked and what still needs the car, sensors, arm, or target
toolchain. Do not claim that a successful build proves physical behavior. A
documentation-only change needs link/path and content checks, not a hardware run.
