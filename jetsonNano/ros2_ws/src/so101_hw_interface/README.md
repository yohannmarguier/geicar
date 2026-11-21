# SO-101 motor bridge

This package comes from [Lerobot_ros2](https://github.com/AgRoboticsResearch/Lerobot_ros2).
The `so101_motor_bridge` executable connects an SO-101 follower's six
Feetech STS3215 motors on IDs 1–6 to ROS 2 Humble. Use the serial adapter
and Python `scservo_sdk` environment that worked for the upstream manual
joint control. The default serial port is `/dev/ttyACM0`. The ROS user
needs permission to open the adapter.

From the Jetson workspace, source Humble, build the package with
`colcon build --packages-select so101_hw_interface`, and source
`install/local_setup.bash`. For manual joint control, start the bridge:

```bash
ros2 run so101_hw_interface so101_motor_bridge --ros-args -p port:=/dev/ttyACM0
```

Check positions with `ros2 topic echo --once /so101_follower/joint_states`.
The bridge publishes that topic at 50 Hz and receives targets on
`/so101_follower/joint_commands`. Both use `sensor_msgs/msg/JointState`
with positions in radians. The bridge reads the starting encoder
positions and writes them as the first goals before it enables torque.
Use `calib_file` to specify the actual arm's calibration if it differs
from the installed YAML. The file supplies homes and allowed ranges
in encoder ticks. Position mode is required on each motor.

With the bridge stopped, read all six encoders without changing torque or
setting a goal:

```bash
ros2 run so101_hw_interface so101_read_steps --port /dev/ttyACM0 --once
```

If startup reports a joint outside its range, compare the measured ticks
with the calibration file named in the error. Support the arm before
repositioning an unpowered joint. Use a known calibration for this arm if
the recorded limits or zero positions differ from the installed example.

The [MoveIt launch](../so101_follower_moveit/README.md#physical-arm) starts
this same bridge with `require_calibration` and `stop_on_bus_error`
enabled. Ctrl+C releases torque on normal shutdown. If serial communication
fails, use the physical power switch if the arm keeps holding its last goal.
