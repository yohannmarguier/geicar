#!/bin/bash
set -euo pipefail

usage() {
    echo "Usage: $0 {pi|jetson|docker} <pi-address>" >&2
    echo "Example: $0 jetson 10.105.1.42" >&2
}

if [[ $# -ne 2 ]]; then
    usage
    exit 1
fi

remote_node=$1
pi_address=$2

case "$remote_node" in
    pi)
        exec ssh -X "pi@$pi_address"
        ;;
    jetson)
        exec ssh -X -J "pi@$pi_address" jetson@192.168.1.10
        ;;
    docker)
        exec ssh -tt -X -J "pi@$pi_address" jetson@192.168.1.10 \
            'sudo docker start ros-humble >/dev/null && sudo docker exec -it ros-humble bash -lc '\''source /opt/ros/humble/setup.bash && source ~/ros2_ws/install/local_setup.bash && exec ros2 launch geicar_start_jetson geicar.jetson.launch.py'\'''
        ;;
    *)
        usage
        exit 1
        ;;
esac
