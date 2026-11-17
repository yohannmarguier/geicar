import os
from pathlib import Path
import subprocess
import signal
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'session.py'


class SessionTest(unittest.TestCase):
    def test_interrupt_does_not_end_supervision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('ros', 'release'):
                (root / name).write_text(':\n')
            base = ['python3', str(SCRIPT), '--lock', str(root / 'lock')]
            session = subprocess.Popen(
                base + ['session', '--ros-setup', str(root / 'ros'),
                        '--release-setup', str(root / 'release'), '--',
                        'sh', '-c', 'echo ready; read line'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(session.stdout.readline().strip(), 'ready')
                session.send_signal(signal.SIGINT)
                self.assertEqual(subprocess.run(base + ['status'], capture_output=True).returncode, 1)
            finally:
                session.communicate('stop\n', timeout=5)
            self.assertEqual(session.returncode, 0)
            self.assertEqual(subprocess.run(base + ['status'], capture_output=True).returncode, 2)

    def test_crashed_session_leaves_status_uncertain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('ros', 'release'):
                (root / name).write_text(':\n')
            base = ['python3', str(SCRIPT), '--lock', str(root / 'lock')]
            session = subprocess.Popen(
                base + ['session', '--ros-setup', str(root / 'ros'),
                        '--release-setup', str(root / 'release'), '--',
                        'sh', '-c', 'echo ready; sleep 1'], stdout=subprocess.PIPE, text=True)
            self.assertEqual(session.stdout.readline().strip(), 'ready')
            session.send_signal(signal.SIGKILL)
            session.communicate(timeout=5)
            self.assertEqual(subprocess.run(base + ['status'], capture_output=True).returncode, 2)
            self.assertEqual(subprocess.run(base + ['replace', '--', 'true'], capture_output=True).returncode, 2)
            self.assertEqual(subprocess.run(base + ['recover'], capture_output=True).returncode, 0)
            self.assertEqual(subprocess.run(base + ['status'], capture_output=True).returncode, 0)

    @unittest.skipUnless(Path('/opt/ros/humble/setup.bash').exists(), 'ROS Humble is unavailable')
    def test_ros_package_discovery_excludes_old_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for prefix, package in (('old', 'old_only_test'), ('release', 'branch_only_test')):
                resources = root / prefix / 'share/ament_index/resource_index/packages'
                resources.mkdir(parents=True)
                (resources / package).touch()
            (root / '.bashrc').write_text(f'export AMENT_PREFIX_PATH={root}/old\n')
            (root / 'release_setup').write_text(
                f'export AMENT_PREFIX_PATH={root}/release:${{AMENT_PREFIX_PATH:-}}\n')
            env = dict(os.environ, HOME=tmp, AMENT_PREFIX_PATH=str(root / 'old'),
                       BASH_ENV=str(root / '.bashrc'))
            result = subprocess.run(
                ['python3', str(SCRIPT), '--lock', str(root / 'lock'), 'session',
                 '--release-setup', str(root / 'release_setup'), '--', 'ros2', 'pkg', 'list'],
                env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('branch_only_test', result.stdout.splitlines())
            self.assertNotIn('old_only_test', result.stdout.splitlines())

    def test_uncertain_status_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = ['python3', str(SCRIPT), '--lock', str(Path(tmp) / 'missing' / 'lock')]
            for action in (['status'], ['session'], ['replace', '--', 'true']):
                result = subprocess.run(base + action, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('Cannot establish release guard', result.stderr)

    def test_replacement_excludes_session_and_other_replacements(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = ['python3', str(SCRIPT), '--lock', str(Path(tmp) / 'lock')]
            replacement = subprocess.Popen(
                base + ['replace', '--', 'sh', '-c', 'echo ready; read line'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(replacement.stdout.readline().strip(), 'ready')
                for action in (['status'], ['session'], ['replace', '--', 'true']):
                    self.assertEqual(subprocess.run(base + action, capture_output=True).returncode, 1)
            finally:
                replacement.communicate('stop\n', timeout=5)
            self.assertEqual(replacement.returncode, 0)
            self.assertEqual(subprocess.run(base + ['status'], capture_output=True).returncode, 0)

    def test_session_blocks_replacement_until_it_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('ros', 'release'):
                (root / name).write_text(':\n')
            base = ['python3', str(SCRIPT), '--lock', str(root / 'lock')]
            session = subprocess.Popen(
                base + ['session', '--ros-setup', str(root / 'ros'),
                        '--release-setup', str(root / 'release'), '--',
                        'sh', '-c', 'echo ready; read line'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(session.stdout.readline().strip(), 'ready')
                self.assertEqual(subprocess.run(base + ['status'], capture_output=True).returncode, 1)
                self.assertEqual(subprocess.run(base + ['replace', '--', 'true'], capture_output=True).returncode, 1)
            finally:
                session.communicate('stop\n', timeout=5)
            self.assertEqual(session.returncode, 0)
            self.assertEqual(subprocess.run(base + ['status'], capture_output=True).returncode, 2)
            self.assertEqual(subprocess.run(base + ['replace', '--', 'true'], capture_output=True).returncode, 2)
            self.assertEqual(subprocess.run(base + ['recover'], capture_output=True).returncode, 0)
            self.assertEqual(subprocess.run(base + ['status'], capture_output=True).returncode, 0)
            self.assertEqual(subprocess.run(base + ['replace', '--', 'true'], capture_output=True).returncode, 0)

    def test_session_ignores_existing_environment_and_shell_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.bashrc').write_text('export OLD_WORKSPACE=from_bashrc\n')
            (root / 'ros').write_text('export AMENT_PREFIX_PATH=/opt/ros/humble\n')
            (root / 'release').write_text('export AMENT_PREFIX_PATH=/release:$AMENT_PREFIX_PATH\n')
            env = dict(os.environ, HOME=tmp, OLD_WORKSPACE='inherited',
                       AMENT_PREFIX_PATH='/old', BASH_ENV=str(root / '.bashrc'))
            result = subprocess.run(
                ['python3', str(SCRIPT), '--lock', str(root / 'lock'), 'session',
                 '--ros-setup', str(root / 'ros'), '--release-setup', str(root / 'release'),
                 '--', 'bash', '-c', 'printf "%s|%s" "$AMENT_PREFIX_PATH" "${OLD_WORKSPACE-unset}"'],
                env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '/release:/opt/ros/humble|unset')


if __name__ == '__main__':
    unittest.main()
