#!/usr/bin/env python3
"""Run isolated release sessions and serialize replacement against them."""
import argparse
import errno
import fcntl
import os
import signal
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', default='/root/geicar-release-guard/session.lock')
    commands = parser.add_subparsers(dest='action', required=True)
    session = commands.add_parser('session')
    session.add_argument('--ros-setup', default='/opt/ros/humble/setup.bash')
    session.add_argument('--release-setup', default='/root/ros2_ws/install/local_setup.bash')
    session.add_argument('command', nargs=argparse.REMAINDER)
    commands.add_parser('status')
    commands.add_parser('recover')
    replace = commands.add_parser('replace')
    replace.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = getattr(args, 'command', [])
    if command and command[0] == '--':
        command = command[1:]
    if args.action == 'replace' and not command:
        parser.error('replace requires a command')

    try:
        fd = os.open(args.lock, os.O_RDWR | os.O_CREAT, 0o600)
        mode = fcntl.LOCK_SH if args.action == 'session' else fcntl.LOCK_EX
        fcntl.flock(fd, mode | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EAGAIN, errno.EACCES) and 'fd' in locals():
            print('Release is in use or being replaced', file=sys.stderr)
            return 1
        print(f'Cannot establish release guard: {exc}', file=sys.stderr)
        return 2
    marker_dir = args.lock + '.sessions'
    os.makedirs(marker_dir, mode=0o700, exist_ok=True)
    markers = os.listdir(marker_dir)
    if args.action == 'recover':
        for marker in markers:
            os.unlink(os.path.join(marker_dir, marker))
        print('Session records cleared; verify all release processes before recovery')
        return 0
    if args.action in ('status', 'replace') and markers:
        print('Release status uncertain: session records require verification and recovery', file=sys.stderr)
        return 2
    if args.action == 'status':
        print('Release is idle')
        return 0

    # Keep the lock across exec and in descendants, including background jobs.
    os.set_inheritable(fd, True)
    if args.action == 'replace':
        os.execvp(command[0], command)
    env = {key: os.environ[key] for key in
           ('HOME', 'USER', 'LOGNAME', 'TERM', 'ROS_DOMAIN_ID',
            'ROS_LOCALHOST_ONLY', 'RMW_IMPLEMENTATION') if key in os.environ}
    env['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    command = command or ['bash', '--noprofile', '--norc', '-i']
    script = 'source "$1" || exit; source "$2" || exit; shift 2; exec "$@"'
    marker_fd, _ = tempfile.mkstemp(prefix='session-', dir=marker_dir)
    os.close(marker_fd)
    # The foreground shell receives terminal Ctrl-C itself. Keep the supervisor
    # alive so it continues holding the guard while the shell handles it.
    signal.signal(signal.SIGINT, lambda _signum, _frame: None)
    result = subprocess.run(
        ['bash', '--noprofile', '--norc', '-c', script,
         'release-session', args.ros_setup, args.release_setup, *command],
        env=env, pass_fds=(fd,))
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


if __name__ == '__main__':
    try:
        sys.exit(main())
    except OSError as exc:
        print(f'Cannot start guarded operation: {exc}', file=sys.stderr)
        sys.exit(2)
