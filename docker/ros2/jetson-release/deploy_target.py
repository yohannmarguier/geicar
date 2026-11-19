#!/usr/bin/env python3
"""Private SSH-side and container-side implementation for deploy.py."""
import ctypes
import errno
import hashlib
import json
import os
import platform
import posixpath
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

PARENT = Path('/root/ros2_ws')
MARKER = '.geicar-managed-release'
GUARD = '/usr/local/bin/geicar-session.py'


def fail(message):
    raise RuntimeError(message)


def host(container, release_parent, digest, encoded):
    inspect = subprocess.check_output(['docker', 'inspect', container])
    info = json.loads(inspect)[0]
    if not info['State']['Running']:
        fail('container is not running; deployment never starts containers')
    mounts = info.get('Mounts', [])
    matches = [m for m in mounts if m['Destination'] == str(PARENT)]
    if len(matches) != 1 or matches[0]['Type'] != 'bind' or not matches[0]['RW']:
        fail('container needs a writable host bind mount at /root/ros2_ws')
    if os.path.realpath(release_parent) == '/' or os.path.realpath(matches[0]['Source']) != os.path.realpath(release_parent):
        fail('container release mount does not match the selected host release parent')
    if any(m['Destination'].startswith(str(PARENT) + '/') for m in mounts):
        fail('nested mounts under /root/ros2_ws would prevent safe replacement')
    print('Release bind mount: {} -> {}'.format(matches[0]['Source'], PARENT), file=sys.stderr, flush=True)
    code = 'exec(__import__("base64").b64decode("%s"))' % encoded
    command = ['docker', 'exec', '-i', container, 'python3', GUARD, 'replace', '--',
               'python3', '-c', code, 'container', digest]
    return subprocess.call(command, stdin=sys.stdin.buffer)


def rename_atomic(source, destination, flags):
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        fn = libc.renameat2
    except AttributeError:
        fail('atomic renameat2 is unavailable; release was not changed')
    fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    fn.restype = ctypes.c_int
    if fn(-100, os.fsencode(source), -100, os.fsencode(destination), flags):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def extract(archive, stage):
    prefix = PurePosixPath('root/ros2_ws')
    install = prefix / 'install'
    seen = set()
    links = []
    with tarfile.open(archive, 'r:') as tf:
        members = tf.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or path in seen:
                fail('unsafe or duplicate archive path: ' + member.name)
            seen.add(path)
            if path not in (prefix / 'packages.txt', prefix / 'release-manifest.txt') and path != install and install not in path.parents:
                fail('unexpected archive path: ' + member.name)
            if path in (install / MARKER, install / '.geicar-packages.txt', install / '.geicar-release-manifest.txt', install / '.geicar-artifact-sha256'):
                fail('artifact contains reserved deployment metadata: ' + member.name)
            if not (member.isdir() or member.isfile() or member.issym()):
                fail('unsupported archive entry: ' + member.name)
            if member.mode & (stat.S_ISUID | stat.S_ISGID):
                fail('privileged archive entry: ' + member.name)
            if member.issym():
                target = PurePosixPath(posixpath.normpath(posixpath.join(str(path.parent), member.linkname)))
                if member.linkname.startswith('/') or (target != install and install not in target.parents):
                    fail('symlink escapes installation: ' + member.name)
                links.append((path, member.linkname))
        for path, _ in links:
            if any(path in other.parents for other in seen):
                fail('archive writes through a symlink: ' + str(path))
        for member in members:
            path = PurePosixPath(member.name)
            dest = stage.joinpath(*path.relative_to(prefix).parts)
            if member.issym():
                continue
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                source = tf.extractfile(member)
                if source is None:
                    fail('cannot read archive entry: ' + member.name)
                with source, dest.open('xb') as out:
                    shutil.copyfileobj(source, out)
                os.chmod(dest, member.mode & 0o777)
        for path, target in links:
            dest = stage.joinpath(*path.relative_to(prefix).parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(target, dest)


def validate(stage, digest):
    if os.geteuid() != 0 or platform.machine() != 'aarch64':
        fail('release requires a root ARM64 container')
    if not Path('/opt/ros/humble/setup.bash').is_file():
        fail('ROS Humble setup is missing')
    clean_env = {key: os.environ[key] for key in
                 ('HOME', 'USER', 'LOGNAME', 'TERM', 'ROS_DOMAIN_ID',
                  'ROS_LOCALHOST_ONLY', 'RMW_IMPLEMENTATION') if key in os.environ}
    clean_env['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    install = stage / 'install'
    if not (install / 'local_setup.bash').is_file():
        fail('artifact has no local_setup.bash')
    manifest = (stage / 'release-manifest.txt').read_text()
    for expected in ('ROS_DISTRO=humble', 'architecture=aarch64',
                     'CPU baseline=armv8-a', 'install prefix=/root/ros2_ws/install'):
        if expected not in manifest.splitlines():
            fail('artifact manifest does not match: ' + expected)
    packages = (stage / 'packages.txt').read_text().splitlines()
    if not packages or any(not p or '/' in p or p in ('.', '..') for p in packages):
        fail('invalid artifact package list')
    for package in packages:
        if not (install / package / 'share' / 'ament_index' / 'resource_index' / 'packages' / package).is_file():
            fail('missing package index: ' + package)
    # A matching build package set is conservative, but avoids silently accepting
    # an older target library or Python ABI than the one used to build the artifact.
    try:
        debs = manifest.split('Debian packages:\n', 1)[1].split('Python packages:\n', 1)[0]
        python_packages = manifest.split('Python packages:\n', 1)[1]
    except IndexError:
        fail('artifact manifest has no dependency inventory')
    current_debs = subprocess.check_output(['dpkg-query', '-W', '-f=${Package} ${Version}\n'],
                                           env=clean_env, universal_newlines=True).splitlines()
    missing = set(debs.splitlines()) - set(current_debs)
    if missing:
        fail('target Debian package versions differ from build: ' + ', '.join(sorted(missing)[:8]))
    current_python = subprocess.check_output(
        ['bash', '--noprofile', '--norc', '-c',
         'source /opt/ros/humble/setup.bash && exec python3 -m pip freeze'],
        env=clean_env, universal_newlines=True).splitlines()
    missing = set(python_packages.splitlines()) - set(current_python)
    if missing:
        fail('target Python packages differ from build: ' + ', '.join(sorted(missing)[:8]))
    for path in install.rglob('*'):
        if path.is_symlink():
            try:
                target = path.resolve(strict=True)
                target.relative_to(install.resolve(strict=True))
            except (OSError, RuntimeError, ValueError):
                fail('dangling or escaping installation symlink: ' + str(path.relative_to(install)))
    files = [p for p in install.rglob('*') if p.is_file() and not p.is_symlink()]
    # Use only paths exported by the staged release's real colcon hooks, in
    # the same clean shell environment as a session. Do not make unexported
    # library directories visible just to make ldd succeed.
    environment = subprocess.check_output(
        ['bash', '--noprofile', '--norc', '-c',
         'source /opt/ros/humble/setup.bash && source "$1/local_setup.bash" && env -0',
         'release-check', str(install)], env=clean_env)
    env = {}
    for item in environment.split(b'\0'):
        if item:
            key, value = item.split(b'=', 1)
            env[os.fsdecode(key)] = os.fsdecode(value)
    for variable in ('LD_LIBRARY_PATH', 'PYTHONPATH', 'AMENT_PREFIX_PATH', 'COLCON_PREFIX_PATH'):
        for path in env.get(variable, '').split(':'):
            if path == str(PARENT / 'install') or path.startswith(str(PARENT / 'install') + '/'):
                fail('staged setup refers to the active release: ' + variable)
    for path in files:
        with path.open('rb') as binary:
            header = binary.read(20)
        if not header.startswith(b'\x7fELF'):
            continue
        if len(header) < 20 or header[5] != 1 or int.from_bytes(header[18:20], 'little') != 183:
            fail('artifact contains a non-ARM64 ELF file: ' + str(path.relative_to(install)))
        check = subprocess.run(['ldd', str(path)], env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, universal_newlines=True)
        output = check.stdout
        if str(PARENT / 'install') + '/' in output:
            fail('runtime library resolves from the active release: ' + str(path.relative_to(install)))
        if 'not found' in output or (check.returncode and 'not a dynamic executable' not in output and 'statically linked' not in output):
            fail('runtime library check failed for {}: {}'.format(path.relative_to(install), output.strip()))
    (install / MARKER).write_text('Managed by geicar deploy.py\n')
    (install / '.geicar-artifact-sha256').write_text(digest + '\n')
    shutil.copy2(stage / 'packages.txt', install / '.geicar-packages.txt')
    shutil.copy2(stage / 'release-manifest.txt', install / '.geicar-release-manifest.txt')


def deploy(digest):
    if not PARENT.is_dir() or PARENT.is_symlink():
        fail('release parent is missing or is a symlink')
    current = PARENT / 'install'
    if current.is_symlink() or (current.exists() and (not current.is_dir() or not (current / MARKER).is_file())):
        fail('existing install is not a managed release; refusing to overwrite it')
    if any(PARENT.glob('.geicar-stage-*')):
        fail('an earlier deployment needs inspection and recovery before retrying')
    stage = Path(tempfile.mkdtemp(prefix='.geicar-stage-', dir=str(PARENT)))
    previous = stage / 'previous'
    installed = False
    try:
        archive = stage / 'transfer.tar'
        checksum = hashlib.sha256()
        with archive.open('xb') as out:
            while True:
                chunk = sys.stdin.buffer.read(1024 * 1024)
                if not chunk:
                    break
                checksum.update(chunk)
                out.write(chunk)
        if checksum.hexdigest() != digest:
            fail('transfer checksum mismatch; existing release unchanged')
        extract(archive, stage)
        validate(stage, digest)
        # NOREPLACE prevents a race on first install; EXCHANGE keeps either the
        # entire old or entire new installation visible during replacement.
        if current.exists():
            try:
                rename_atomic(stage / 'install', current, 2)
            except OSError as exc:
                if exc.errno not in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP, errno.ENOTEMPTY):
                    raise
                # Some host-backed filesystems do not implement EXCHANGE. The
                # guard excludes sessions during the gap; leave the old tree in
                # the stage for manual recovery if the process is interrupted.
                rename_atomic(current, previous, 1)
                try:
                    rename_atomic(stage / 'install', current, 1)
                except OSError:
                    rename_atomic(previous, current, 1)
                    raise
        else:
            rename_atomic(stage / 'install', current, 1)
        installed = True
        print('Release installed at /root/ros2_ws/install', flush=True)
    finally:
        # Never remove the only copy of the old release after a failed restore.
        if not previous.exists() or installed:
            shutil.rmtree(stage)
    return 0


def main():
    try:
        if sys.argv[1] == 'host' and len(sys.argv) == 6:
            return host(*sys.argv[2:])
        if sys.argv[1] == 'container' and len(sys.argv) == 3:
            return deploy(sys.argv[2])
        fail('invalid deployment invocation')
    except (OSError, RuntimeError, ValueError, KeyError, IndexError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print('Deployment failed: {}'.format(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
