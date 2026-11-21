import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, ExecuteProcess, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    use_fake_hardware = LaunchConfiguration("use_fake_hardware")
    # Declare the launch argument
    declare_use_fake_hardware = DeclareLaunchArgument(
        "use_fake_hardware",
        default_value="true",
        description="Bypass hardware interface and use fake controller",
    )
    declare_use_rviz = DeclareLaunchArgument(
        "use_rviz",
        default_value="true",
        description="Open RViz to visualize the arm",
    )
    declare_port = DeclareLaunchArgument("port", default_value="/dev/ttyACM0")
    declare_calib_file = DeclareLaunchArgument(
        "calib_file",
        default_value=PathJoinSubstitution([
            FindPackageShare("so101_hw_interface"), "config", "so101_calibration.yaml"
        ]),
    )

    # Setup MoveIt configs
    moveit_config = (
        MoveItConfigsBuilder("so101_follower", package_name="so101_follower_moveit")
        .robot_description(
            mappings={"use_fake_hardware": use_fake_hardware}
        )
        .trajectory_execution(file_path="config/moveit_controllers.yaml")
        .to_moveit_configs()
    )

    # RViz
    rviz_config = os.path.join(
        moveit_config.package_path, "config", "moveit.rviz"
    )
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="log",
        condition=IfCondition(LaunchConfiguration("use_rviz")),
        arguments=["-d", rviz_config],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
        ],
    )

    # Publish link transforms from the URDF and controller joint states.
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[moveit_config.robot_description],
    )

    # MoveGroup
    move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[moveit_config.to_dict()],
    )

    # Load the control system selected in the URDF.
    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[
            moveit_config.robot_description,
            os.path.join(moveit_config.package_path, "config", "ros2_controllers.yaml"),
        ],
        output="screen",
    )

    motor_bridge = Node(
        package="so101_hw_interface",
        executable="so101_motor_bridge",
        output="screen",
        parameters=[{
            "port": ParameterValue(LaunchConfiguration("port"), value_type=str),
            "calib_file": ParameterValue(LaunchConfiguration("calib_file"), value_type=str),
            "require_calibration": True,
            "stop_on_bus_error": True,
        }],
    )

    joint_states = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_state_broadcaster", "-c", "/controller_manager"],
    )
    trajectory_controllers = [
        Node(
            package="controller_manager",
            executable="spawner",
            arguments=[controller, "-c", "/controller_manager"],
        ) for controller in ("arm_controller", "gripper_controller")
    ]

    wait_for_arm = ExecuteProcess(cmd=[
        "timeout", "20s", "ros2", "topic", "echo", "--no-daemon", "--once",
        "/so101_follower/joint_states", "sensor_msgs/msg/JointState",
    ])

    def start_after_broadcaster(event, context):
        if event.returncode != 0:
            return [EmitEvent(event=Shutdown(reason="Joint state broadcaster failed to start"))]
        if IfCondition(use_fake_hardware).evaluate(context):
            return [move_group_node, *trajectory_controllers]
        return [motor_bridge, wait_for_arm]

    def start_after_feedback(event, _context):
        if event.returncode != 0:
            return [EmitEvent(event=Shutdown(reason="No joint feedback from the SO-101"))]
        return [move_group_node, *trajectory_controllers]

    return LaunchDescription(
        [
            declare_use_fake_hardware,
            declare_use_rviz,
            declare_port,
            declare_calib_file,
            RegisterEventHandler(OnProcessExit(
                target_action=joint_states, on_exit=start_after_broadcaster
            )),
            RegisterEventHandler(OnProcessExit(
                target_action=wait_for_arm, on_exit=start_after_feedback,
            )),
            RegisterEventHandler(OnProcessExit(
                target_action=motor_bridge,
                on_exit=[EmitEvent(event=Shutdown(reason="SO-101 motor bridge stopped"))],
            )),
            RegisterEventHandler(OnProcessExit(
                target_action=ros2_control_node,
                on_exit=[EmitEvent(event=Shutdown(reason="Controller manager stopped"))],
            )),
            rviz_node,
            robot_state_publisher,
            ros2_control_node,
            joint_states,
        ]
    )
