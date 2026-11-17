#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../../.." && pwd)
output=${1:-"$root/jetson-release.tar"}
case "$output" in /*) ;; *) output="$PWD/$output" ;; esac
if [ -e "$output" ]; then
  echo "Refusing to overwrite existing artifact: $output" >&2
  exit 1
fi
outdir=$(dirname "$output")
[ -d "$outdir" ] || { echo "Output directory does not exist: $outdir" >&2; exit 1; }
tmp=$(mktemp -d "$outdir/.jetson-release.XXXXXXXX")
builder="geicar-jetson-release-$$"
cleanup() { docker rm -f "$builder" >/dev/null 2>&1 || true; rm -rf "$tmp"; }
trap cleanup EXIT

cd "$root"
docker build --platform linux/arm64 -f docker/ros2/jetson-release/Dockerfile -t geicar-jetson-release:humble .
docker create --name "$builder" --platform linux/arm64 --network none \
  -v "$root/jetsonNano/ros2_ws/src:/source:ro" \
  --entrypoint bash geicar-jetson-release:humble -c '
set -euo pipefail
[ "$(uname -m)" = aarch64 ]
set +u
source /opt/ros/humble/setup.bash
set -u
mkdir -p /root/ros2_ws
cd /root/ros2_ws
colcon list --base-paths /source --names-only | sort > packages.txt
[ -s packages.txt ]
export CFLAGS="-march=armv8-a" CXXFLAGS="-march=armv8-a"
colcon build --base-paths /source --install-base /root/ros2_ws/install
{
  echo "ROS_DISTRO=$ROS_DISTRO"
  echo "architecture=$(uname -m)"
  echo "CPU baseline=armv8-a"
  echo "install prefix=/root/ros2_ws/install"
  echo "packages:"
  cat packages.txt
  echo "Debian packages:"
  dpkg-query -W -f="\${Package} \${Version}\n"
  echo "Python packages:"
  python3 -m pip freeze
} > release-manifest.txt
# Only the install and its manifest are distributed.
tar -C / -cf /release.tar root/ros2_ws/install root/ros2_ws/packages.txt root/ros2_ws/release-manifest.txt
'
docker start -a "$builder"
docker cp "$builder:/release.tar" "$tmp/release.tar"
# A fresh container has the same dependencies but neither build nor source tree.
docker run --rm -i --platform linux/arm64 --network none --entrypoint bash \
  geicar-jetson-release:humble -c '
set -euo pipefail
tar -C / -xf -
set +u
source /opt/ros/humble/setup.bash
source /root/ros2_ws/install/local_setup.bash
set -u
while IFS= read -r package; do
  prefix=$(ros2 pkg prefix "$package")
  case "$prefix" in /root/ros2_ws/install/*|/root/ros2_ws/install) ;; *) echo "Unexpected prefix for $package: $prefix" >&2; exit 1 ;; esac
done < /root/ros2_ws/packages.txt
if [ -n "$(find -L /root/ros2_ws/install -type l -print -quit)" ]; then
  echo "Installation contains a dangling symlink" >&2; exit 1
fi
python3 -c "
import serial, scservo_sdk
from interfaces.msg import MotorsOrder
from so_arm101.motion import targets_at
assert targets_at([2048], [100], 0.25, 1.0) == [2148]
MotorsOrder()
"
echo "Clean-container package discovery and Python dependencies passed."
' < "$tmp/release.tar"
mv "$tmp/release.tar" "$output"
echo "Created $output"
