#!/usr/bin/env bash
set -euo pipefail

export DISPLAY=:1
export LIBGL_ALWAYS_SOFTWARE=1
background_pids=()
launch_pid=

cleanup() {
    # Keep the serial bridge alive during ROS shutdown so torque can be released.
    if [[ -n "$launch_pid" ]]; then
        kill -INT "$launch_pid" 2>/dev/null || true
        wait "$launch_pid" 2>/dev/null || true
    fi
    kill "${background_pids[@]}" 2>/dev/null || true
    wait
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

Xvfb "$DISPLAY" -screen 0 1440x900x24 -nolisten tcp -noreset &
display_pid=$!
background_pids+=("$display_pid")
if ! timeout 10s bash -c 'until xdpyinfo >/dev/null 2>&1; do sleep 0.1; done'; then
    echo 'The RViz display did not start.' >&2
    exit 1
fi

openbox &
background_pids+=("$!")
x11vnc -display "$DISPLAY" -localhost -rfbport 5900 -forever -nopw &
background_pids+=("$!")
websockify --web /usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900 &
background_pids+=("$!")

serial_args=()
if [[ -n "${SO101_SERIAL_TCP:-}" ]]; then
    serial_device=/tmp/so101
    socat "PTY,link=$serial_device,raw,echo=0" "TCP:$SO101_SERIAL_TCP,nodelay,connect-timeout=5" &
    serial_pid=$!
    background_pids+=("$serial_pid")
    for _ in {1..50}; do
        [[ -c "$serial_device" ]] && break
        kill -0 "$serial_pid" 2>/dev/null || break
        sleep 0.1
    done
    if [[ ! -c "$serial_device" ]]; then
        echo 'Could not connect to the SO-101 host serial bridge.' >&2
        exit 1
    fi
    serial_args+=("port:=$serial_device")
fi

env --default-signal=INT ros2 launch so101_follower_moveit demo.launch.py "${serial_args[@]}" "$@" &
launch_pid=$!
status=0
wait -n -p stopped_pid "$launch_pid" "${background_pids[@]}" || status=$?
if [[ "${stopped_pid:-}" == "$launch_pid" ]]; then
    launch_pid=
    exit "$status"
fi
echo 'The display or serial bridge stopped. Shutting down the SO-101 launch.' >&2
exit 1
