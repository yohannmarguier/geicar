"""Command-boundary tests; set GEICAR_DEPLOY_TEST_IMAGE and ARTIFACT for Docker tests."""
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
COMMAND = ROOT / 'deploy.py'
IMAGE = os.environ.get('GEICAR_DEPLOY_TEST_IMAGE')
ARTIFACT = os.environ.get('GEICAR_DEPLOY_TEST_ARTIFACT')


class AliasTests(unittest.TestCase):
    def test_alias_and_artifact_are_passed_to_ssh(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            ssh = path / 'ssh'
            ssh.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$ARGS_LOG"\ncat > "$DATA_LOG"\n')
            ssh.chmod(0o755)
            artifact = path / 'release.tar'
            artifact.write_bytes(b'complete release')
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ['PATH'],
                       ARGS_LOG=str(path / 'args'), DATA_LOG=str(path / 'data'))
            for alias in ('ethernet-route', 'pi-jump'):
                result = subprocess.run([sys.executable, str(COMMAND), alias, str(artifact), '--release-parent', '/release'], env=env, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((path / 'args').read_text().splitlines()[2], alias)
                self.assertEqual((path / 'data').read_bytes(), artifact.read_bytes())

    def test_option_like_alias_is_rejected(self):
        result = subprocess.run([sys.executable, str(COMMAND), '--release-parent', '/release', '--', '-bad', '/unused'], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_missing_build_artifact_fails_before_ssh(self):
        with tempfile.TemporaryDirectory() as tmp:
            ssh = Path(tmp) / 'ssh'
            ssh.write_text('#!/bin/sh\ntouch "$CALLED"\n')
            ssh.chmod(0o755)
            called = Path(tmp) / 'called'
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ['PATH'], CALLED=str(called))
            result = subprocess.run([sys.executable, str(COMMAND), 'ethernet-route', str(Path(tmp) / 'missing.tar'), '--release-parent', '/release'], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(called.exists())


@unittest.skipUnless(IMAGE and ARTIFACT, 'set GEICAR_DEPLOY_TEST_IMAGE and GEICAR_DEPLOY_TEST_ARTIFACT for isolated Docker checks')
class DockerDeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='geicar-deploy-test-')
        cls.path = Path(cls.temp.name)
        (cls.path / 'release').mkdir()
        (cls.path / 'guard').mkdir()
        (cls.path / 'fault').mkdir()
        # Inject rename failures at the OS boundary only inside the disposable
        # container, so the real deployment command and recovery paths run.
        (cls.path / 'fault' / 'fault.c').write_text(r'''
#define _GNU_SOURCE
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>
int renameat2(int a, const char *src, int b, const char *dst, unsigned int flags) {
    char mode[32] = "";
    FILE *f = fopen("/tmp/geicar-fault/mode", "r");
    if (f) { (void)fgets(mode, sizeof(mode), f); fclose(f); }
    if (*mode && flags == 2) { errno = ENOTSUP; return -1; }
    if (!strcmp(mode, "fail") && flags == 1 && strstr(src, "/.geicar-stage-") &&
        strstr(src, "/install") && !strcmp(dst, "/root/ros2_ws/install")) {
        errno = EIO; return -1;
    }
    int result = syscall(SYS_renameat2, a, src, b, dst, flags);
    if (!strcmp(mode, "interrupt") && !result && flags == 1 && strstr(dst, "/previous"))
        kill(getpid(), SIGKILL);
    return result;
}
''')
        subprocess.run(['docker', 'run', '--rm', '--platform', 'linux/arm64',
                        '-v', str(cls.path / 'fault') + ':/test', '--entrypoint', 'gcc', IMAGE,
                        '-shared', '-fPIC', '-o', '/test/fault.so', '/test/fault.c'], check=True, capture_output=True)
        cls.name = 'geicar-deploy-test-' + uuid.uuid4().hex[:12]
        cls.ssh = cls.path / 'ssh'
        cls.ssh.write_text('#!/bin/sh\nexec sh -c "$4"\n')
        cls.ssh.chmod(0o755)
        cls.env = dict(os.environ, PATH=str(cls.path) + os.pathsep + os.environ['PATH'])
        subprocess.run(['docker', 'run', '-d', '--rm', '--platform', 'linux/arm64', '--name', cls.name,
                        '-e', 'PYTHONPATH=/tmp/oldpython', '-e', 'LD_PRELOAD=/tmp/geicar-fault/fault.so',
                        '-v', str(cls.path / 'release') + ':/root/ros2_ws',
                        '-v', str(cls.path / 'guard') + ':/root/geicar-release-guard',
                        '-v', str(cls.path / 'fault') + ':/tmp/geicar-fault',
                        '-v', str(ROOT / 'session.py') + ':/usr/local/bin/geicar-session.py:ro',
                        '--entrypoint', 'sleep', IMAGE, 'infinity'], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['docker', 'rm', '-f', cls.name], capture_output=True)
        cls.temp.cleanup()

    def setUp(self):
        (self.path / 'fault' / 'mode').unlink(missing_ok=True)
        self.ssh.write_text('#!/bin/sh\nexec sh -c "$4"\n')
        for child in (self.path / 'release').iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        subprocess.run(['docker', 'exec', self.name, 'python3', '/usr/local/bin/geicar-session.py', 'recover'], check=True, capture_output=True)

    def deploy(self, alias='ethernet-route', artifact=ARTIFACT):
        return subprocess.run([sys.executable, str(COMMAND), alias, str(artifact), '--container', self.name,
                               '--release-parent', str(self.path / 'release')],
                              env=self.env, capture_output=True, text=True, timeout=120)

    def test_complete_release_and_atomic_replacement(self):
        first = self.deploy()
        self.assertEqual(first.returncode, 0, first.stderr)
        install = self.path / 'release' / 'install'
        self.assertTrue((install / '.geicar-managed-release').is_file())
        (install / 'old-release-only').write_text('old')
        second = self.deploy('pi-jump')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertFalse((install / 'old-release-only').exists())
        subprocess.run(['docker', 'exec', self.name, 'sh', '-c',
                        'mkdir -p /tmp/old/share/ament_index/resource_index/packages; touch /tmp/old/share/ament_index/resource_index/packages/old_only'], check=True)
        result = subprocess.run(['docker', 'exec', '-e', 'AMENT_PREFIX_PATH=/tmp/old', self.name,
                                 'python3', '/usr/local/bin/geicar-session.py', 'session', '--', 'bash', '-c',
                                 'ros2 pkg prefix usb_cam && ! ros2 pkg list | grep -qx old_only && '
                                 'libs=$(ldd /root/ros2_ws/install/usb_cam/lib/usb_cam/usb_cam_node_exe) && '
                                 '! grep -q "not found" <<< "$libs" && '
                                 'python3 -c "from interfaces.msg import MotorsOrder; import serial, scservo_sdk; MotorsOrder()"'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('/root/ros2_ws/install/usb_cam', result.stdout)

    def test_interrupted_transfer_leaves_release_unchanged(self):
        self.assertEqual(self.deploy().returncode, 0)
        sentinel = self.path / 'release' / 'install' / 'sentinel'
        sentinel.write_text('old release')
        self.ssh.write_text('#!/bin/sh\nhead -c 1024 | sh -c "$4"\n')
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), 'old release')

    def test_unmanaged_install_is_never_replaced(self):
        install = self.path / 'release' / 'install'
        install.mkdir()
        (install / 'old-workspace').write_text('preserve')
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((install / 'old-workspace').read_text(), 'preserve')

    def test_mount_must_match_selected_parent(self):
        result = subprocess.run([sys.executable, str(COMMAND), 'ethernet-route', ARTIFACT,
                                 '--container', self.name, '--release-parent', str(self.path / 'other')],
                                env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('does not match', result.stderr)
        self.assertEqual(list((self.path / 'release').iterdir()), [])

    def test_symlink_chain_cannot_escape_release(self):
        self.assertEqual(self.deploy().returncode, 0)
        sentinel = self.path / 'release' / 'install' / 'sentinel'
        sentinel.write_text('old release')
        artifact = self.path / 'escaping.tar'
        with tarfile.open(ARTIFACT, 'r:') as original, tarfile.open(artifact, 'w:') as modified:
            for member in original:
                stream = original.extractfile(member) if member.isfile() else None
                modified.addfile(member, stream)
                if stream:
                    stream.close()
            for name, target in (('a', '.'), ('b', 'a/..')):
                link = tarfile.TarInfo('root/ros2_ws/install/' + name)
                link.type = tarfile.SYMTYPE
                link.linkname = target
                modified.addfile(link)
        result = self.deploy(artifact=artifact)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('escaping installation symlink', result.stderr)
        self.assertEqual(sentinel.read_text(), 'old release')

    def test_old_python_path_cannot_satisfy_runtime_dependencies(self):
        subprocess.run(['docker', 'exec', self.name, 'sh', '-c',
                        "mkdir -p /tmp/oldpython/geicar_old_only-1.0.dist-info && printf 'Metadata-Version: 2.1\\nName: geicar-old-only\\nVersion: 1.0\\n' > /tmp/oldpython/geicar_old_only-1.0.dist-info/METADATA"], check=True)
        inherited = subprocess.run(['docker', 'exec', self.name, 'python3', '-m', 'pip', 'freeze'], capture_output=True, text=True, check=True)
        self.assertIn('geicar-old-only==1.0', inherited.stdout)
        artifact = self.path / 'old-python-path.tar'
        with tarfile.open(ARTIFACT, 'r:') as original, tarfile.open(artifact, 'w:') as modified:
            for member in original:
                stream = original.extractfile(member) if member.isfile() else None
                if member.name == 'root/ros2_ws/release-manifest.txt':
                    contents = stream.read() + b'geicar-old-only==1.0\n'
                    stream.close()
                    member.size = len(contents)
                    stream = io.BytesIO(contents)
                modified.addfile(member, stream)
                if stream:
                    stream.close()
        result = self.deploy(artifact=artifact)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('target Python packages differ', result.stderr)
        self.assertFalse((self.path / 'release' / 'install').exists())

    def test_interrupted_replacement_requires_recovery(self):
        self.assertEqual(self.deploy().returncode, 0)
        install = self.path / 'release' / 'install'
        (install / 'old-release').write_text('preserve')
        (self.path / 'fault' / 'mode').write_text('interrupt')
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        stages = list((self.path / 'release').glob('.geicar-stage-*'))
        self.assertEqual(len(stages), 1)
        previous = stages[0] / 'previous'
        self.assertEqual((previous / 'old-release').read_text(), 'preserve')
        self.assertFalse(install.exists())
        (self.path / 'fault' / 'mode').unlink()
        self.assertIn('needs inspection and recovery', self.deploy().stderr)
        subprocess.run(['docker', 'exec', self.name, 'python3', '/usr/local/bin/geicar-session.py',
                        'replace', '--', 'mv', '-T', str('/root/ros2_ws/' + stages[0].name + '/previous'),
                        '/root/ros2_ws/install'], check=True)
        self.assertEqual((install / 'old-release').read_text(), 'preserve')

    def test_failed_replacement_restores_previous_release(self):
        self.assertEqual(self.deploy().returncode, 0)
        sentinel = self.path / 'release' / 'install' / 'sentinel'
        sentinel.write_text('old release')
        (self.path / 'fault' / 'mode').write_text('fail')
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), 'old release')
        self.assertEqual(list((self.path / 'release').glob('.geicar-stage-*')), [])

    def test_session_cannot_start_during_transfer(self):
        self.ssh.write_text('#!/bin/sh\n(head -c 1024; sleep 5; cat) | sh -c "$4"\n')
        proc = subprocess.Popen([sys.executable, str(COMMAND), 'pi-jump', ARTIFACT, '--container', self.name,
                                 '--release-parent', str(self.path / 'release')],
                                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                if list((self.path / 'release').glob('.geicar-stage-*')):
                    break
                time.sleep(0.1)
            else:
                self.fail('deployment did not acquire guard')
            session = subprocess.run(['docker', 'exec', self.name, 'python3', '/usr/local/bin/geicar-session.py', 'session', '--', 'true'], capture_output=True)
            self.assertNotEqual(session.returncode, 0)
            stdout, stderr = proc.communicate(timeout=60)
            self.assertEqual(proc.returncode, 0, stdout + stderr)
        finally:
            if proc.poll() is None:
                proc.communicate(timeout=60)

    def test_active_and_uncertain_sessions_refuse_replacement(self):
        self.assertEqual(self.deploy().returncode, 0)
        command = ['docker', 'exec', self.name, 'python3', '/usr/local/bin/geicar-session.py', 'session', '--', 'sleep', '5']
        session = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                marker_dir = self.path / 'guard' / 'session.lock.sessions'
                if marker_dir.exists() and list(marker_dir.iterdir()):
                    break
                time.sleep(0.1)
            else:
                self.fail('session did not acquire guard: ' + (session.stderr.read() if session.poll() is not None else 'still running'))
            self.assertNotEqual(self.deploy().returncode, 0)
            session.communicate(timeout=10)
            self.assertNotEqual(self.deploy().returncode, 0)
        finally:
            if session.poll() is None:
                session.communicate(timeout=10)
            else:
                session.communicate()


if __name__ == '__main__':
    unittest.main()
