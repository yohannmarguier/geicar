FROM ros:humble-ros-base

# The ROS image is based on Ubuntu 22.04 and already provides colcon and rosdep.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libavcodec-dev \
        libswscale-dev \
        pkg-config \
        python3-pip \
        python3-serial \
        socat \
        v4l-utils \
    && rm -rf /var/lib/apt/lists/*

# Feetech's Python SDK is used by the optional SO-101 ROS package. Its serial
# dependency comes from Ubuntu's python3-serial package above.
RUN python3 -m pip install --no-cache-dir --no-deps ftservo-python-sdk==2.0.1

# Source trees are small and used only for dependency discovery. Live files are
# bind-mounted by Compose, so editing source does not require an image rebuild.
COPY raspberryPI3/ros2_ws/src /tmp/geicar-deps/raspberry/src
COPY jetsonNano/ros2_ws/src /tmp/geicar-deps/jetson/src
RUN apt-get update \
    && rosdep update --rosdistro humble \
    && rosdep install --from-paths /tmp/geicar-deps/raspberry/src /tmp/geicar-deps/jetson/src \
        --ignore-src --skip-keys joystick_ros2 --rosdistro humble -y \
    && rm -rf /tmp/geicar-deps /var/lib/apt/lists/*

CMD ["bash"]
