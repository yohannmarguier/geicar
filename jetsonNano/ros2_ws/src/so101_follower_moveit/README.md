# SO-101 MoveIt position demo

The [upstream Lerobot_ros2 packages](https://github.com/AgRoboticsResearch/Lerobot_ros2)
provide the follower arm model and MoveIt configuration. This demo uses ROS 2
Humble and supports a mock arm or an SO-101 follower on a USB serial adapter.

## Build and run

In the Jetson workspace on a Humble system, install dependencies and build:

```bash
cd ~/Documents/dev/geicar/jetsonNano/ros2_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src/so101_follower_description src/so101_follower_moveit src/so101_hw_interface --ignore-src -r -y
colcon build --packages-select so101_follower_description so101_follower_moveit so101_hw_interface
source install/local_setup.bash
ros2 launch so101_follower_moveit demo.launch.py use_fake_hardware:=true use_rviz:=false
```

Adjust the workspace path for your checkout or container. The mock demo needs
MoveIt, ros2_control, the joint state broadcaster, and the joint trajectory
controller. Omit `use_rviz:=false` on a desktop to open the visualization.
Leave the launch running while sending goals.

In a second terminal, source Humble and this workspace's
`install/local_setup.bash`, then send the example:

```bash
goal_file="$(ros2 pkg prefix --share so101_follower_moveit)/config/example_position_goal.yaml"
ros2 action send_goal /move_action moveit_msgs/action/MoveGroup "$(cat "$goal_file")"
```

Look for `Goal finished with status: SUCCEEDED` and MoveIt error code `1`.
The example computes a path from the mock starting position. To test mock
execution, copy the YAML to your working directory, set `plan_only: false`
in the copy, and send it while the mock launch is running. Look for updated
joint positions in `ros2 topic echo /joint_states --once`. Press Ctrl+C in
the launch terminal to stop the mock stack.

## ROS interface

- `/move_action` uses `moveit_msgs/action/MoveGroup`. The `arm` group has
  five joints. The separate `gripper` group controls the jaw.
- The example specifies the XYZ position of the `gripper_link` origin
  relative to `base_link`, in metres. The spherical goal has a 3 mm radius
  and leaves orientation free. The model fixes `base_link` to `world`.
- `/joint_states` uses `sensor_msgs/msg/JointState`. The joint state
  broadcaster publishes joint angles in radians, and the robot state
  publisher uses them to publish the link transforms.
- MoveIt sends trajectories to
  `/arm_controller/follow_joint_trajectory` using
  `control_msgs/action/FollowJointTrajectory`.
- The description's `include_hardware_control` Xacro argument defaults
  to true for the standalone hardware configuration. The MoveIt Xacro
  defaults it to false so the demo loads only its selected control system.

## Physical arm

Use the USB serial device and the calibration file from your working
[motor bridge setup](../so101_hw_interface/README.md). The real mode also
requires the Humble `topic_based_ros2_control` plugin. Stop any previous
motor bridge and manual slider publisher before launching MoveIt.

```bash
ros2 launch so101_follower_moveit demo.launch.py use_fake_hardware:=false use_rviz:=false port:=/dev/ttyACM0
```

The launch starts the motor bridge, which reads all six motor positions
and uses them as the first goals before enabling torque. The trajectory
controllers and MoveIt wait for the bridge to publish feedback. If you used a
custom calibration with the manual setup, pass its absolute path as
`calib_file:=/path/to/your/calibration.yaml`.

In another sourced terminal, run `ros2 topic echo --once /joint_states`
and check that all six angles are present. Send the example above with
`plan_only: true` to check planning from the real arm's current position.
For the first powered move, use a small target near the current
`gripper_link` position and review the plan with the arm's workspace clear
before setting `plan_only: false`. Use `ros2 run tf2_ros tf2_echo base_link
gripper_link` to read the current XYZ position. The example coordinates
were selected for the mock starting pose.

Ctrl+C stops the launch and releases motor torque on a normal shutdown.
Support the arm if it could sag. On a serial fault the bridge exits and
the launch shuts down. The motors may retain their last goal if the
serial bus is unavailable. Use the arm's power switch if needed. The
live launch was tested end to end with simulated serial feedback and the
Humble trajectory controllers. Execution on the powered arm still needs
verification.
