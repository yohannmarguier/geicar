#!/usr/bin/env python3
"""Transfer a built Jetson artifact to the guarded release in a ROS container."""
import argparse
import base64
import hashlib
import os
from pathlib import Path
import posixpath
import re
import shlex
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('alias', help='SSH host alias (direct or ProxyJump)')
    parser.add_argument('artifact', type=Path, help='completed artifact from build.sh')
    parser.add_argument('--container', default='ros-humble', help='existing Docker container name')
    parser.add_argument('--release-parent', required=True, help='absolute host path of the separate release parent bind mount')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', args.alias):
        parser.error('alias must be an SSH host alias, not an option or address with a user')
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', args.container):
        parser.error('invalid container name')
    if not args.release_parent.startswith('/') or posixpath.normpath(args.release_parent) == '/':
        parser.error('release parent must be an absolute, non-root host path')
    try:
        with args.artifact.open('rb') as artifact:
            digest = hashlib.file_digest(artifact, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else digest_file(artifact)
            artifact.seek(0)
            source = Path(__file__).with_name('deploy_target.py').read_bytes()
            encoded = base64.b64encode(source).decode('ascii')
            program = f'exec(__import__("base64").b64decode("{encoded}"))'
            command = shlex.join(['python3', '-c', program, 'host', args.container, args.release_parent, digest, encoded])
            return subprocess.run(['ssh', '-T', '--', args.alias, command], stdin=artifact).returncode
    except (OSError, ValueError) as exc:
        print(f'Deployment failed: {exc}', file=sys.stderr)
        return 2


def digest_file(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(chunk)
    return digest.hexdigest()


if __name__ == '__main__':
    sys.exit(main())
