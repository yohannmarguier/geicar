#!/bin/bash
set -euo pipefail

usage() {
    echo "Usage: $0 <x> <y> <z>" >&2
    echo "Example: $0  0.13 -0.220 0.370" >&2
}

if [[ $# -ne 3 ]]; then
    usage
    exit 1
fi

exec docker exec -it geicar-so101 bash -lc '
  source /opt/so101_ws/install/setup.bash

  ros2 action send_goal /move_action moveit_msgs/action/MoveGroup "{
    request: {
      group_name: arm,
      allowed_planning_time: 1.0,
      max_velocity_scaling_factor: 0.1,
      max_acceleration_scaling_factor: 0.1,
      goal_constraints: [{
        position_constraints: [{
          header: {frame_id: base_link},
          link_name: gripper_link,
          weight: 1.0,
          constraint_region: {
            primitives: [{type: 2, dimensions: [0.003]}],
            primitive_poses: [{
              position: {x: "$1", y: "$2", z: "$3"}
            }]
          }
        }]
      }]
    },
    planning_options: {plan_only: false}
  }" --feedback
'