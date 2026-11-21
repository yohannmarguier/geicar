# SO-101 ROS 2 node diagrams

The three SO-101 packages cover the robot model (`so101_follower_description`), motion planning and control (`so101_follower_moveit`), and serial communication with the motors (`so101_hw_interface`). The diagrams reflect the launch files and configuration in the Jetson workspace.

## MoveIt demo

```mermaid
flowchart TD
    Model["so101_follower_description<br/>URDF/Xacro and meshes"]
    CLI["CLI or application"]
    RViz["/rviz2<br/>Optional MoveIt UI"]

    subgraph Demo["so101_follower_moveit · demo.launch.py"]
        MoveGroup["/move_group<br/>Plans arm motion"]
        RSP["/robot_state_publisher<br/>Converts joint angles into link transforms"]

        subgraph Control["ros2_control · /controller_manager"]
            Traj["/arm_controller and /gripper_controller"]
            JS["/joint_state_broadcaster"]
            Mock["GenericSystem plugin<br/>Mock mode, default"]
            Real["TopicBasedSystem plugin<br/>Real mode"]
        end
    end

    subgraph Hardware["so101_hw_interface"]
        Bridge["/so101_motor_bridge"]
    end

    Motors["Six Feetech servos"]

    Model -.->|robot model| MoveGroup
    Model -.->|robot model| RSP
    CLI -->|"/move_action"| MoveGroup
    RViz -->|"planning and execution requests"| MoveGroup
    MoveGroup -->|"follow_joint_trajectory action on each controller"| Traj
    Traj -->|position commands| Mock
    Traj -->|position commands| Real
    Mock -->|mock joint feedback| JS
    Real -->|motor joint feedback| JS
    Real -->|"/so101_follower/joint_commands"| Bridge
    Bridge -->|"/so101_follower/joint_states"| Real
    Bridge <-->|USB serial| Motors
    JS -->|"/joint_states"| MoveGroup
    JS -->|"/joint_states"| RSP
    RSP -->|"/tf and /tf_static"| RViz
```

The launch selects one hardware plugin. With `use_fake_hardware:=true`, `GenericSystem` supplies mock joint feedback. With `use_fake_hardware:=false`, the launch waits for the bridge's first joint-state message before starting the trajectory controllers. The bridge publishes calibrated motor angles on `/so101_follower/joint_states`, and the broadcaster publishes `/joint_states` for MoveIt and the robot state publisher. [Demo launch](../jetsonNano/ros2_ws/src/so101_follower_moveit/launch/demo.launch.py) · [Hardware plugin configuration](../jetsonNano/ros2_ws/src/so101_follower_moveit/config/so101_follower.ros2_control.xacro) · [Motor bridge](../jetsonNano/ros2_ws/src/so101_hw_interface/so101_hw_interface/motor_bridge.py)

## Standalone model display

```mermaid
flowchart LR
    GUI["/joint_state_publisher_gui<br/>Sliders enabled by default"]
    RSP["/robot_state_publisher"]
    RViz["/rviz2"]
    Bridge["/so101_motor_bridge<br/>Started separately"]

    GUI -->|"/joint_states by default"| RSP
    Bridge -.->|"/so101_follower/joint_states in live display mode"| RSP
    RSP -->|"/tf and /tf_static"| RViz
```

- `so101_follower_description/display.launch.py` previews the model in RViz. To display the real pose from an already-running bridge, pass `use_gui:=false joint_states_topic:=/so101_follower/joint_states`. [Display launch](../jetsonNano/ros2_ws/src/so101_follower_description/launch/display.launch.py)
- `so101_hw_interface/so101_hw.launch.py` starts `/robot_state_publisher` and `/controller_manager` with its standalone controller configuration. The hardware package also provides the `/so101_calibrator` utility node and the `so101_read_steps` command for reading encoder counts directly over serial. [Hardware launch](../jetsonNano/ros2_ws/src/so101_hw_interface/launch/so101_hw.launch.py) · [Executable definitions](../jetsonNano/ros2_ws/src/so101_hw_interface/setup.py)
