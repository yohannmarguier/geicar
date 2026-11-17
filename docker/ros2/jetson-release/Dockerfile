FROM --platform=linux/arm64 arm64v8/ros:humble-ros-base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libavcodec-dev libswscale-dev pkg-config python3-pip python3-serial v4l-utils \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --no-cache-dir --no-deps ftservo-python-sdk==2.0.1
COPY jetsonNano/ros2_ws/src /tmp/jetson-src
RUN apt-get update && rosdep update --rosdistro humble \
    && rosdep install --from-paths /tmp/jetson-src --ignore-src --rosdistro humble -y \
    && rm -rf /tmp/jetson-src /var/lib/apt/lists/*
