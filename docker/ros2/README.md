# ROS 2 Humble development on macOS

This Docker setup provides Ubuntu 22.04 and ROS 2 Humble for editing and building
the Raspberry Pi and Jetson ROS workspaces on a Mac. It is a **local development
environment**, not the container running on the car's Jetson. Docker Desktop for
Mac is required and must be running. Both Apple Silicon and Intel Macs use the
architecture supported by their Docker installation; a local build does not
replace a build and test on the target boards.

From the repository root, build the image once:

```sh
docker compose build raspberry
```

Open a shell in either workspace:

```sh
docker compose run --rm raspberry
docker compose run --rm jetson
```

The repository is mounted at `/project`, so edits made on the Mac appear in the
container immediately. The shell starts in the selected `ros2_ws` directory.
The ROS base environment is sourced by the image entrypoint. Each workspace
has its own Docker volumes for `build/`, `install/`, and `log/`; these survive
`run --rm` and keep Linux build products off the Mac filesystem. Do not build
the repository root as one workspace: both workspaces contain `interfaces`.

The image installs the dependencies declared in both workspaces' `package.xml`
files through `rosdep`. Rebuild with `docker compose build raspberry` after
changing package dependencies. Source edits take effect immediately through
the bind mount. The image skips the inherited `joystick_ros2` rosdep key:
`geicar_start/package.xml` names it, while the workspace builds the joystick
node inside the `joystick` package.

Then build. In the Raspberry shell, start with the shared messages and build
other packages individually as described in
[`raspberryPI3/ros2_ws/how_to_compile.md`](../../raspberryPI3/ros2_ws/how_to_compile.md):

```sh
colcon build --packages-select interfaces
source install/local_setup.bash
colcon build --packages-up-to car_control
source install/local_setup.bash
ros2 pkg list | grep car_control
```

In the Jetson shell, follow
[`jetsonNano/ros2_ws/how_to_compile.md`](../../jetsonNano/ros2_ws/how_to_compile.md):

```sh
colcon build --packages-select interfaces
source install/local_setup.bash
colcon build --packages-up-to usb_cam
source install/local_setup.bash
ros2 pkg list | grep usb_cam
```

Source `install/local_setup.bash` again in each new shell after a successful
build. The `ros2 pkg list` checks confirm package discovery, not sensor or car
operation. If `rosdep` reports an unresolved key during image build, inspect
that package and its component guide before adding or changing dependencies.

## SO-101 arm connected to the Mac

Docker Desktop for Mac [does not directly pass USB devices](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/general/#can-i-pass-through-a-usb-device-to-a-container)
to a Linux container. The optional bridge below opens the serial port on the Mac and gives
the Jetson container a Linux pseudo-terminal at `/tmp/so101`. This is only a
byte transport; the optional [SO-101 dance package](../../jetsonNano/ros2_ws/src/so-arm101/README.md)
uses that path for a bounded motion demo. Use the container path, not the macOS
`/dev/cu.*` path inside the container.

On the Mac, install the host bridge's one Python dependency and start it in a
terminal from the repository root:

```sh
python3 -m venv docker/ros2/.venv
docker/ros2/.venv/bin/python -m pip install pyserial
docker/ros2/.venv/bin/python docker/ros2/so101_serial_host.py \
  --device /dev/cu.usbmodem5AA90177351
```

Leave that terminal running. The host bridge listens only on Mac loopback port
54321 and opens the serial port at 1,000,000 baud when the container connects.
In a second Mac terminal, rebuild the image once to add `socat`, then open the
Jetson shell with the bridge:

```sh
docker compose build raspberry
docker compose run --rm jetson bash /project/docker/ros2/jetson_so101_shell.sh
```

Inside that shell, verify that the device exists without sending motor commands:

```sh
ls -l /tmp/so101
```

Press Ctrl-D to leave the shell and Ctrl-C in the Mac bridge terminal to stop.
Only one program should open `/tmp/so101` at a time. The Mac bridge holds the
physical port while connected; close any Mac program using the arm first. If
the device name changes after reconnecting USB, update `--device`. If your
arm's configured baud rate differs, pass the same `--baudrate` to the Mac
script. The Linux pseudo-terminal's baud setting does not change the physical
port speed on the Mac. The bridge forwards serial bytes as soon as they arrive
and disables TCP small-packet buffering, but it still adds a Mac-to-Docker hop.
Actual arm round-trip latency has not been measured. Do motor setup,
calibration, and motion tests only with
the correct arm variant, power supply, and joint limits confirmed.

The macOS container still does not expose the car's CAN bus, camera, lidar, or
joystick. Docker Desktop's networking and device access differ from Linux on
the car. Validate hardware and ROS communication on the target Pi/Jetson after
local builds. The pre-existing Jetson `ros-humble` container described in the
board guide is a separate deployment environment.

## Jetson ARM64 release from a Mac

Issue #2 adds an offline build artifact for the **Jetson workspace only**. On an
Apple Silicon Mac with Docker Desktop running, network access for image and
package downloads, and sufficient disk space, run from the repository root:

```sh
docker/ros2/jetson-release/build.sh /absolute/path/jetson-release.tar
```

The output path must not already exist. The build uses the current Jetson
`src/` files, including uncommitted and new files (except Docker's
`.dockerignore` exclusions). It resolves their declared dependencies with
`rosdep`, installs the existing camera build dependencies and the SO-101 Python
SDK, then runs a fresh non-symlink colcon build. The Docker image and build
container are ARM64; C and C++ builds request the generic `armv8-a` CPU
baseline. Packages that override compiler flags or use prebuilt binaries need
separate inspection. The Raspberry Pi workspace and the Jetson are not touched.
The image tag and package repositories are mutable: this is a repeatable process,
not a bit-for-bit reproducible or pinned build.

The install prefix is **`/root/ros2_ws/install`**, matching `~/ros2_ws/install`
only if the Jetson container runs as root. The tar contains that absolute-path
layout, the discovered package names, and `release-manifest.txt` with the
build's OS and Python package versions. Do not relocate it. The script refuses
to overwrite an existing output and only publishes the tar after a successful
build and a source-free, network-disabled container check. That check extracts
it at the intended path, discovers every built package and checks dangling links
and loads an installed generated message and arm motion module alongside its
Python dependencies. It does not exercise hardware or every node.

Before any later deployment, inspect the actual `ros-humble` container without
changing it: confirm its user/home and install path, `uname -m`, Ubuntu and ROS
Humble versions, and installed library and Python versions against the manifest.
The guide's `arm64v8/ros:humble-ros-base` image is an assumption, not proof of
the running image or dependency compatibility. In particular, ensure the same
runtime dependencies (including `ftservo-python-sdk==2.0.1` and
`python3-serial`) exist in the target container. Verify the Jetson CPU supports
the baseline and check package-specific compiler flags and binary dependencies.
If the actual path or runtime differs, rebuild for that environment; extraction
or deployment is outside this build procedure. After installation, source
`/opt/ros/humble/setup.bash` and `/root/ros2_ws/install/local_setup.bash`, check
`ros2 pkg list`, and follow the component guides for hardware validation. A
successful local check does not prove camera, lidar, vehicle, or arm operation.

## Guarded Jetson release sessions

Issue #3 provides `jetson-release/session.py`, a cooperative Linux lock and
clean session launcher. It does not deploy files or start any nodes. The
following setup is for the existing Jetson `ros-humble` container, **after**
confirming its user, mounts, dependencies and the fixed installation path in
the preceding section. The running container and actual Jetson have not been
verified by these checks.

The release must appear at `/root/ros2_ws/install` inside the container. The
existing workspace must remain untouched on the host: mount a **separate,
host-backed release parent directory** at `/root/ros2_ws` in the container,
with the release under its `install/` child. Do not bind-mount the `install`
directory itself when deploying: a bind
mount can keep referring to the old directory after a rename. Changing mounts
requires recreating the container; inspect its existing settings and preserve
its devices, network, other mounts and configuration first. Do not recreate it
as part of starting a session. The release must already be installed and its
runtime compatibility verified; the deployment procedure is described below.

Copy `session.py` into a stable location in that container, for example
`/usr/local/bin/geicar-session.py`, and create a persistent, writable guard
directory outside the release, `/root/geicar-release-guard`. This directory
must be visible to every session and replacement operation, on a local Linux
filesystem that supports `flock`. The lock file is
`/root/geicar-release-guard/session.lock`: never remove, rename or replace it,
or replace its containing mount, while operations may be running. Recreating
or independently copying the lock file creates a different lock and defeats
the guard. The adjacent `session.lock.sessions` directory contains persistent
session records; preserve it as well. All users must have permission to open
the same file and access that directory. Keep the script and guard directory
outside the replaced release.

From a Jetson host shell, start a deliberate interactive test session:

```sh
docker exec -it ros-humble python3 /usr/local/bin/geicar-session.py session
```

The launcher starts with a clean environment, sources ROS Humble and the
release, and starts Bash without shell startup files. It preserves `HOME`,
`USER`, `LOGNAME`, `TERM`, `ROS_DOMAIN_ID`, `ROS_LOCALHOST_ONLY`, and
`RMW_IMPLEMENTATION` when set; configure the ROS domain in the environment
passed to `docker exec` if needed (for example `docker exec -e ROS_DOMAIN_ID=1
...`). It does not source the old workspace or `.bashrc`. Inside the session,
verify package origins before deliberately launching anything:

```sh
ros2 pkg prefix usb_cam
ros2 pkg prefix so_arm101
ros2 pkg list
# If desired, deliberately launch the branch's existing camera/lidar stack:
ros2 launch geicar_start_jetson geicar.jetson.launch.py
```

Replace the example packages with names in `packages.txt` and check that their
prefixes are under `/root/ros2_ws/install`. Also check that a known package
exclusive to the old workspace is absent. This branch's launch does **not**
launch the unmerged emergency-stop node. Verify all actual node and hardware
behavior separately. Stop the launched application and its children before
exiting the session with Ctrl-D. Sourcing a different environment affects only
that shell and future children; it does not change already running processes.

Deployment runs its **entire replacement operation** under the
same exclusive guard inside the same container and PID namespace, for example:

```sh
docker exec ros-humble python3 /usr/local/bin/geicar-session.py status
docker exec ros-humble python3 /usr/local/bin/geicar-session.py replace -- /path/to/replacement-command
```

`status` returns 0 for idle, 1 for a held lock, and 2 if it cannot establish
status or finds a session record awaiting verification. `replace` holds an exclusive lock while its command runs and refuses
to start with status 1 if a session or replacement holds the lock; an error
opening or locking the file returns 2. A session holds a shared lock for its
lifetime and refuses to start during replacement. Checking status followed by
an unguarded replacement is **not safe**: another session can start between
those operations. The replacement command must complete all file changes before
it exits, and deployment must treat every nonzero result as refusal or failure.
Neither status nor replacement starts or stops applications.

Every session leaves its record behind, including after a normal exit, because
the launcher cannot prove that all of its children have stopped. After the
session ends, inspect the container's processes and stop every process that
could be using the release before clearing those records deliberately:

```sh
docker exec ros-humble python3 /usr/local/bin/geicar-session.py recover
```

Recovery takes the exclusive lock and refuses while a guarded session or
replacement is active. It does not inspect or stop processes; only use it
after that manual verification. Until then, status and replacement return 2.

This is a cooperative guard, not process discovery: every release user and
every replacement must use it. Do not source the release elsewhere, detach
processes from the session, or exit or kill the session before all its
application processes have stopped. Programs that close inherited file
descriptors can outlive a successfully exited session without holding its lock.
An independently started or detached process is not detected; follow the
session lifetime rule even when the guard reports idle.
The `--lock`, `--ros-setup`, and `--release-setup` options are intended for
consistent site configuration and testing: changing them for one participant
can defeat coordination or isolation.

The focused checks can be run on a machine with Python 3:

```sh
python3 -m unittest discover -s docker/ros2/jetson-release/tests -p 'test_session.py'
```

The ROS package-discovery check is skipped without `/opt/ros/humble`; the suite
also runs in the local ARM64 release image. It exercises synthetic package
indexes, session exit, locking, interrupted-session recovery and guard errors,
not actual deployment, target mounts, application crashes or vehicle hardware.

## Deploy the Jetson release over SSH

Build an artifact first with `jetson-release/build.sh`. The Mac needs Python
3.8 or later and SSH; the Jetson host needs Python 3, Docker, and permission
for the SSH user to use Docker without an interactive `sudo` prompt. Docker
access grants powerful host privileges; configure it deliberately. The running
container needs Python 3, Bash, `dpkg-query`, pip, `ldd`, ROS Humble, and the
runtime dependencies from the build. Deployment never starts or stops the
container or nodes.

Configure SSH host aliases locally; substitute your actual hostnames, users and
identity settings. Either direct Ethernet or a Pi jump route works through the
same command; SSH selects the route:

```sshconfig
Host car-jetson-direct
    HostName YOUR_JETSON_ADDRESS
    User YOUR_JETSON_USER

Host car-pi
    HostName YOUR_PI_ADDRESS
    User YOUR_PI_USER

Host car-jetson-via-pi
    HostName YOUR_JETSON_ADDRESS_AS_SEEN_FROM_PI
    User YOUR_JETSON_USER
    ProxyJump car-pi
```

Test the selected alias with `ssh car-jetson-direct` or
`ssh car-jetson-via-pi` first, including host-key verification and authentication.
The deploy command uses SSH's standard configuration and does not embed
credentials or addresses. It accepts an alias, not a `user@host` argument.

### Prepare the existing container

On the Jetson host, inspect the **running** container and its mounts first:

```sh
docker inspect --format '{{json .Mounts}}' ros-humble
docker inspect --format '{{json .Config.User}} {{.State.Running}}' ros-humble
docker exec ros-humble sh -c 'id; uname -m; echo "$HOME"; test -f /opt/ros/humble/setup.bash && echo Humble-present'
```

Record where the current workspace actually lives, and preserve it. If it is
inside the container's writable layer, copy it to a new, empty host location
before any container recreation. If it is a host mount, preserve that host
directory. Do not reuse or remove the existing workspace. The deployment
requires a **different** writable host bind mount at `/root/ros2_ws`, with no
additional mounts beneath that path. Its `install` child must be absent on the
first deployment; an existing install is accepted only if created by this
command. The parent, not `install`, must be mounted so directory renames are
visible in the container.

If the running container lacks that mount, adding it requires creating a
replacement container. First record and preserve the existing container's
image, network, device mappings, environment, other mounts, and any data in its
writable layer; incorporate a bind mount such as
`--mount type=bind,src=/YOUR/SEPARATE/RELEASE-PARENT,dst=/root/ros2_ws` into
its otherwise equivalent configuration. Retain the original container and
workspace until their preservation is verified. Container recreation can affect
running applications and devices and is a deliberate separate operation, not
part of deployment. The SSH user and container root need write access to the
release parent. A local Linux filesystem with `flock` and `renameat2` support
is required; network filesystems have not been validated.

Set up the stable session guard described above outside the release. For
example, from the Mac copy `jetson-release/session.py` to the Jetson host, then
on the host create `/root/geicar-release-guard` inside the container and copy
the script to `/usr/local/bin/geicar-session.py`. For a first setup, when no
release sessions or replacements are running and the script is not already
installed:

```sh
# On the Mac, from the repository root:
scp docker/ros2/jetson-release/session.py car-jetson-via-pi:/tmp/geicar-session.py
# On the Jetson host:
docker exec ros-humble mkdir -p /root/geicar-release-guard
docker cp /tmp/geicar-session.py ros-humble:/usr/local/bin/geicar-session.py
```

Preserve the guard directory
and lock file across all sessions and replacement operations; a separate
host-backed guard mount is recommended when recreating containers. All release
users must cooperate with this same guard. Do not replace the guard script or
lock while operations may be running. The deployment invokes its `replace`
action inside the existing container and holds the exclusive lock for transfer,
verification, and replacement.

### Deploy and verify

From the repository root on the Mac, using your chosen alias and completed
artifact:

```sh
python3 docker/ros2/jetson-release/deploy.py car-jetson-via-pi /absolute/path/jetson-release.tar --release-parent /YOUR/SEPARATE/RELEASE-PARENT
# Optional when the running container has a different name:
python3 docker/ros2/jetson-release/deploy.py car-jetson-direct /absolute/path/jetson-release.tar --release-parent /YOUR/SEPARATE/RELEASE-PARENT --container ros-humble
```

The command checks the running container's actual mount against the explicitly
selected host release parent and prints its host source. You must verify that
this directory is separate from the old workspace. It transfers the artifact
under the guard, checks its SHA-256, archive
paths, ARM64/Humble manifest, package indexes, dangling links, ARM64 ELF files
and dynamic library resolution. For a conservative compatibility check, it
requires **every** Debian package and Python package version recorded by the
build to be present in the target, even build-only dependencies. This can
reject a target that might otherwise run the release; compare the reported
versions and prepare or rebuild for the actual environment. Archive hard links,
special files, and links escaping the install are refused. Package-specific CPU
flags and hardware behavior still need separate verification.
The staged library check sources the staged install's hooks in a clean shell;
the install is still at a temporary path at that point. Check libraries again
in the actual session at the fixed installation path.

The artifact, its package list, and manifest must come from the same successful
build. The installed release records its digest in
`/root/ros2_ws/install/.geicar-artifact-sha256`, its package list in
`.geicar-packages.txt`, and its manifest in `.geicar-release-manifest.txt`.
Use the guarded session instructions above to verify package origins, the
absence of an old-workspace-only package, and to launch deliberately. Check
native libraries and generated paths on the actual target, for example:

```sh
docker exec ros-humble python3 /usr/local/bin/geicar-session.py session -- bash -c \
  'ros2 pkg prefix usb_cam; ldd /root/ros2_ws/install/usb_cam/lib/usb_cam/usb_cam_node_exe; python3 -c "from interfaces.msg import MotorsOrder; import serial, scservo_sdk; MotorsOrder()"'
```

Inspect the `ldd` output for missing libraries and repeat the check for other
installed executables and libraries that will be used. This creates a session
record, which requires the manual process inspection and
`recover` procedure above before another deployment. Do not interpret package
discovery or a successful build as a camera, lidar, arm or car test.

### Interruption and recovery

A failed build or interrupted transfer does not replace the active release. A
checksum failure or any inability to establish the guard refuses replacement.
The command stages on the same mount and uses Linux atomic exchange when
available. If exchange is unsupported, it moves the old release aside while
holding the exclusive guard, then installs the fully verified new release. An
interruption in that short gap can leave `install` absent, but retains the old
release in a `.geicar-stage-*` directory. Sessions cannot use a missing install.
An interruption after the new install is moved into place can leave both the
new install and the previous copy. In either case a later deployment refuses to
proceed while any stage directory remains. An SSH disconnect after a complete
transfer may occur after activation; inspect the installed digest rather than
assuming the old or new release is active.

Before recovery, inspect processes and clear session records as described in the
guard section. Under the same exclusive guard, inspect each `.geicar-stage-*`
directory and its `previous`, `install`, and `transfer.tar` entries. Never
remove the only complete copy. If `install` is absent and a stage contains
`previous`, restore it to `/root/ros2_ws/install` under the exclusive guard;
if `install` is present, compare its digest and the retained copy before
choosing which to keep. A stage's `install` may be the old release after an
atomic exchange or an unactivated new release before exchange; check its digest.
Remove the specific stage directory only after confirming a complete chosen
release is in place. Run any recovery file operations through
`geicar-session.py replace -- ...`, not after a separate status check. A stage
left during an initial transfer may contain only partial staging data; it does
not represent an activated release. Preserve unrelated files throughout.

For example, after confirming that `install` is absent and that the named
stage's `previous` is the complete old release, restore it with the guard:

```sh
docker exec ros-humble python3 /usr/local/bin/geicar-session.py replace -- \
  sh -c 'test ! -e /root/ros2_ws/install && mv -T -n /root/ros2_ws/.geicar-stage-CHOSEN/previous /root/ros2_ws/install'
```

Substitute the inspected stage name and check the result before removing any
stage. If the guard reports a session record, first follow its manual recovery
procedure; never delete or replace the guard lock to force progress.

Local command-boundary tests use a fake SSH transport and a disposable ARM64
container. With the image and an artifact built as above:

```sh
GEICAR_DEPLOY_TEST_IMAGE=geicar-jetson-release:humble \
GEICAR_DEPLOY_TEST_ARTIFACT=/absolute/path/jetson-release.tar \
python3 -m unittest discover -s docker/ros2/jetson-release/tests
```

These checks do not establish the actual Jetson's mount, permissions, installed
libraries, or camera, lidar, arm and vehicle behavior. Those target checks must
be recorded separately when the car is reachable.

On 19 November 2026, the ARM64 artifact build and clean-container discovery
check passed on the Mac. The disposable-container deployment checks exercised
installation, replacement, transfer interruption, guarded refusal, concurrent
session refusal, package isolation, generated message loading, and runtime
dependency checks. OS-level fault injection in the disposable container also
checked rollback after a failed replacement and recovery after killing the
replacement between renames. The complete local suite passed 20 tests with one
ROS-dependent host test skipped; all seven session tests also passed in the
ARM64 ROS image, including that skipped check. The Jetson could not be reached
over SSH, so its actual
mount, installation path, compatibility, camera, lidar, arm, and car behavior
remain unverified.
