FROM ros:humble-ros-base-jammy

# The base image provides the ROS APT repository, colcon, and initialized rosdep.
WORKDIR /opt/so101_ws
COPY jetsonNano/ros2_ws/src/so101_follower_description/ src/so101_follower_description/
COPY jetsonNano/ros2_ws/src/so101_follower_moveit/ src/so101_follower_moveit/
COPY jetsonNano/ros2_ws/src/so101_hw_interface/ src/so101_hw_interface/

# ament_python uses setuptools. The optional MongoDB warehouse has no Humble
# package for Jammy; the mock and physical arm demos do not use it.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libgl1-mesa-dri novnc openbox python3-deepdiff python3-pip python3-serial \
        python3-tqdm python3-yaml ros-humble-desktop socat websockify x11-utils \
        x11vnc xfonts-base xvfb \
    && rosdep update --rosdistro humble \
    && DEBIAN_FRONTEND=noninteractive rosdep install --from-paths src \
        --ignore-src --rosdistro humble --skip-keys 'ament_python warehouse_ros_mongo' -y \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m pip install --no-cache-dir --no-deps feetech-servo-sdk==1.0.0

RUN bash -c 'source /opt/ros/humble/setup.bash && colcon build'

COPY ressources/so101-rviz.sh /usr/local/bin/so101-rviz
RUN chmod +x /usr/local/bin/so101-rviz

ENTRYPOINT ["/ros_entrypoint.sh", "bash", "-c", "source /opt/so101_ws/install/local_setup.bash && exec \"$@\"", "--"]
CMD ["bash"]
