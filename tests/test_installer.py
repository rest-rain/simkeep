"""Exercise the installer with isolated files and fake external Docker/download commands."""
import json
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parent.parent


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='simkeep-installer-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.destination = self.root / 'deployment with spaces'
        self.log = self.root / 'commands.jsonl'
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        for name in ('bash', 'sh', 'python3', 'cat', 'mkdir', 'mktemp', 'mv', 'chmod', 'rm', 'cp', 'touch', 'sha256sum', 'true', 'sleep'):
            (bin_dir / name).symlink_to(shutil.which(name))
        command = '''#!/usr/bin/env python3
import hashlib, json, os, pathlib, shutil, subprocess, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['SIMKEEP_TEST_LOG'], 'a') as output:
    output.write(json.dumps([name, *args]) + '\\n')
state = pathlib.Path(os.environ['SIMKEEP_TEST_STATE'])
if name == 'docker':
    if args == ['info']:
        if os.getenv('SIMKEEP_TEST_ROOT_SOCKET') and not os.getenv('SIMKEEP_TEST_PRIVILEGED'):
            sys.exit(1)
        if os.getenv('SIMKEEP_TEST_STOPPED') and not (state / 'started').exists():
            sys.exit(1)
        sys.exit(int(os.getenv('SIMKEEP_TEST_DOCKER_FAILURE', '0')))
    if args == ['context', 'show']:
        print(os.getenv('SIMKEEP_TEST_CONTEXT', 'default'))
        sys.exit(0)
    if 'pull' in args:
        sys.exit(int(os.getenv('SIMKEEP_TEST_PULL_FAILURE', '0')))
    if 'version' in args:
        if os.getenv('SIMKEEP_TEST_COMPOSE_MISSING') and not (state / 'plugin').exists():
            sys.exit(1)
        print('2.39.0')
elif name == 'curl':
    destination = pathlib.Path(args[args.index('-o') + 1])
    url = args[-1]
    if url == 'https://get.docker.com':
        destination.write_text('cp "$SIMKEEP_TEST_DOCKER_FIXTURE" "$SIMKEEP_TEST_BIN/docker"\\ntouch "$SIMKEEP_TEST_STATE/engine"\\n')
        sys.exit(0)
    if '/docker/compose/releases/latest/download/' in url:
        binary = b'compose-plugin-test-fixture\\n'
        if url.endswith('.sha256'):
            digest = '0' * 64 if os.getenv('SIMKEEP_TEST_BAD_CHECKSUM') else hashlib.sha256(binary).hexdigest()
            destination.write_text(digest + '  ' + url.rsplit('/', 1)[-1].removesuffix('.sha256') + '\\n')
        else:
            destination.write_bytes(binary)
        sys.exit(0)
    source = pathlib.Path(os.environ['SIMKEEP_TEST_FIXTURES']) / args[-1].rsplit('/', 1)[-1]
    if source.name == '.env.example' and os.getenv('SIMKEEP_TEST_DOWNLOAD_FAILURE'):
        destination.write_text('partial download')
        sys.exit(22)
    shutil.copyfile(source, destination)
elif name == 'uname':
    print(os.getenv('SIMKEEP_TEST_SYSTEM', 'Linux') if '-s' in args else os.getenv('SIMKEEP_TEST_ARCH', 'aarch64'))
elif name == 'id':
    print(os.getenv('SIMKEEP_TEST_UID', '0'))
elif name == 'awk':
    if args[-1] == '/etc/os-release':
        print(os.getenv('SIMKEEP_TEST_DISTRO', 'ubuntu'))
    else:
        os.execv(os.environ['SIMKEEP_TEST_AWK'], [os.environ['SIMKEEP_TEST_AWK'], *args])
elif name in ('systemctl', 'service'):
    if os.getenv('SIMKEEP_TEST_DOCKER_FAILURE'):
        sys.exit(1)
    (state / 'started').touch()
elif name == 'install':
    if args[-1].endswith('/docker-compose'):
        (state / 'plugin').touch()
elif name == 'sudo':
    if os.getenv('SIMKEEP_TEST_SUDO_FAILURE'):
        sys.exit(1)
    args = [arg for arg in args if arg != '-n']
    if args == ['-v']:
        sys.exit(0)
    environment = dict(os.environ, SIMKEEP_TEST_PRIVILEGED='1')
    sys.exit(subprocess.call(args, env=environment))
'''
        for name in ('docker', 'curl', 'uname', 'id', 'awk', 'systemctl', 'service', 'install', 'sudo'):
            executable = bin_dir / name
            executable.write_text(command)
            executable.chmod(0o755)
        self.environment = dict(os.environ)
        for name in ('SIMKEEP_IMAGE', 'SIMKEEP_PORT', 'SIMKEEP_PUBLIC_URL', 'SIMKEEP_ENV_FILE', 'DOCKER_HOST', 'DOCKER_CONTEXT'):
            self.environment.pop(name, None)
        (self.root / 'state').mkdir()
        docker_fixture = self.root / 'fake-docker'
        shutil.copy2(bin_dir / 'docker', docker_fixture)
        self.environment.update({
            'PATH': str(bin_dir),
            'SIMKEEP_TEST_LOG': str(self.log),
            'SIMKEEP_TEST_FIXTURES': str(ROOT),
            'SIMKEEP_TEST_STATE': str(self.root / 'state'),
            'SIMKEEP_TEST_BIN': str(bin_dir),
            'SIMKEEP_TEST_DOCKER_FIXTURE': str(docker_fixture),
            'SIMKEEP_TEST_AWK': shutil.which('awk'),
        })

    def install(self, *options, environment=None):
        return subprocess.run(
            ['bash', str(ROOT / 'install.sh'), '--non-interactive', '--dir', str(self.destination), *options],
            cwd=self.root, env=environment or self.environment, input='',
            text=True, capture_output=True, timeout=10,
        )

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_help_does_not_contact_docker_or_create_a_deployment(self):
        result = self.install('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--dir', result.stdout)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.commands(), [])

    def test_fresh_install_writes_private_configuration_and_starts_the_published_image(self):
        result = self.install('--port', '05301', '--url', 'http://example.invalid:5301')
        self.assertEqual(result.returncode, 0, result.stderr)
        env = self.destination / '.env'
        self.assertIn('SIMKEEP_PORT=5301\n', env.read_text())
        self.assertIn('SIMKEEP_PUBLIC_URL=http://example.invalid:5301\n', env.read_text())
        self.assertIn('SIMKEEP_IMAGE=ghcr.io/rest-rain/simkeep:latest\n', env.read_text())
        self.assertEqual(env.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.destination / 'docker-compose.yml').read_bytes(), (ROOT / 'docker-compose.yml').read_bytes())
        docker = [args for args in self.commands() if args[0] == 'docker']
        pull = next(index for index, args in enumerate(docker) if 'pull' in args)
        up = next(index for index, args in enumerate(docker) if 'up' in args)
        self.assertLess(pull, up)
        self.assertIn('--wait', docker[up])
        self.assertIn(str(self.destination / 'docker-compose.yml'), docker[up])
        self.assertIn('http://example.invalid:5301', result.stdout)
        self.assertFalse(any('down' in args or 'build' in args for args in docker))
        self.assertFalse(any(args[0] in ('sudo', 'systemctl', 'service', 'install') for args in self.commands()))

    def test_noninteractive_defaults_work_without_a_terminal(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        content = (self.destination / '.env').read_text()
        self.assertIn('SIMKEEP_PORT=5180\n', content)
        self.assertIn('SIMKEEP_PUBLIC_URL=http://localhost:5180\n', content)

    def test_rerun_preserves_configuration_without_executing_its_contents(self):
        self.destination.mkdir()
        marker = self.root / 'must-not-exist'
        original_env = ('SIMKEEP_PUBLIC_URL=http://example.invalid:5302\nSIMKEEP_PORT=5302\n'
                        'SIMKEEP_IMAGE=ghcr.io/rest-rain/simkeep:latest\n'
                        f'SIMKEEP_SMTP_PASSWORD=$(touch {shlex.quote(str(marker))})\n').encode()
        original_compose = (ROOT / 'docker-compose.yml').read_bytes() + b'\n# Existing custom configuration\n'
        (self.destination / '.env').write_bytes(original_env)
        (self.destination / 'docker-compose.yml').write_bytes(original_compose)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.destination / '.env').read_bytes(), original_env)
        self.assertEqual((self.destination / 'docker-compose.yml').read_bytes(), original_compose)
        self.assertFalse(marker.exists())
        self.assertFalse(any(args[0] == 'curl' for args in self.commands()))

    def test_invalid_new_install_settings_do_not_download_or_start_anything(self):
        for options in (('--port', '0'), ('--port', '65536'), ('--port', '5180;exit'),
                        ('--url', 'http://example.invalid:70000'), ('--url', 'http://example.invalid/$USER')):
            with self.subTest(options=options):
                result = self.install(*options)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotEqual(result.returncode, 127, result.stderr)
                self.assertFalse(self.destination.exists())
                self.assertFalse(any(args[0] == 'curl' or 'up' in args for args in self.commands()))

    def test_unavailable_docker_does_not_create_configuration(self):
        environment = dict(self.environment, SIMKEEP_TEST_DOCKER_FAILURE='1')
        result = self.install(environment=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Docker', result.stderr)
        self.assertFalse(self.destination.exists())
        self.assertFalse(any(args[0] == 'curl' for args in self.commands()))

    def test_partial_download_does_not_install_partial_configuration(self):
        environment = dict(self.environment, SIMKEEP_TEST_DOWNLOAD_FAILURE='1')
        result = self.install(environment=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(args[0] == 'curl' for args in self.commands()))
        self.assertFalse((self.destination / '.env').exists())
        self.assertFalse((self.destination / 'docker-compose.yml').exists())
        self.assertFalse(any('up' in args for args in self.commands()))

    def test_failed_image_pull_does_not_start_a_container_or_report_success(self):
        environment = dict(self.environment, SIMKEEP_TEST_PULL_FAILURE='1')
        result = self.install(environment=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any('pull' in args for args in self.commands()))
        self.assertFalse(any('up' in args for args in self.commands()))
        self.assertNotIn('部署完成', result.stdout)

    def test_missing_docker_is_installed_from_the_official_script(self):
        (Path(self.environment['SIMKEEP_TEST_BIN']) / 'docker').unlink()
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'state/engine').exists())
        self.assertTrue(any(args[0] == 'curl' and args[-1] == 'https://get.docker.com' for args in self.commands()))
        self.assertTrue((self.destination / '.env').is_file())

    def test_missing_compose_is_installed_without_reinstalling_the_engine(self):
        result = self.install(environment=dict(self.environment, SIMKEEP_TEST_COMPOSE_MISSING='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'state/plugin').exists())
        self.assertFalse((self.root / 'state/engine').exists())
        self.assertFalse(any(args[-1] == 'https://get.docker.com' for args in self.commands()))

    def test_corrupt_compose_download_is_rejected_before_installation(self):
        environment = dict(self.environment, SIMKEEP_TEST_COMPOSE_MISSING='1', SIMKEEP_TEST_BAD_CHECKSUM='1')
        result = self.install(environment=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(args[0] == 'curl' and args[-1].endswith('.sha256') for args in self.commands()))
        self.assertFalse((self.root / 'state/plugin').exists())
        self.assertFalse(any('up' in args for args in self.commands()))

    def test_stopped_local_docker_is_started(self):
        result = self.install(environment=dict(self.environment, SIMKEEP_TEST_STOPPED='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'state/started').exists())

    def test_nonroot_user_can_deploy_with_sudo_without_changing_group_membership(self):
        environment = dict(self.environment, SIMKEEP_TEST_UID='1000', SIMKEEP_TEST_ROOT_SOCKET='1')
        result = self.install(environment=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(args[0] == 'sudo' and 'up' in args for args in self.commands()))
        self.assertFalse((self.root / 'state/started').exists())

    def test_unavailable_sudo_fails_before_changing_the_system(self):
        (Path(self.environment['SIMKEEP_TEST_BIN']) / 'docker').unlink()
        environment = dict(self.environment, SIMKEEP_TEST_UID='1000', SIMKEEP_TEST_SUDO_FAILURE='1')
        result = self.install(environment=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('root', result.stderr)
        self.assertFalse(any(args[0] == 'curl' for args in self.commands()))

    def test_unsupported_system_is_rejected_before_running_the_docker_installer(self):
        (Path(self.environment['SIMKEEP_TEST_BIN']) / 'docker').unlink()
        result = self.install(environment=dict(self.environment, SIMKEEP_TEST_DISTRO='arch'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('arch', result.stderr)
        self.assertFalse(any(args[0] == 'curl' for args in self.commands()))

    def test_unreachable_remote_docker_does_not_start_a_local_service(self):
        environment = dict(self.environment, SIMKEEP_TEST_DOCKER_FAILURE='1', DOCKER_HOST='tcp://example.invalid:2376')
        result = self.install(environment=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DOCKER_HOST', result.stderr)
        self.assertFalse(any(args[0] in ('sudo', 'systemctl', 'service') for args in self.commands()))

    @unittest.skipUnless(hasattr(pty, 'fork'), 'Requires a Unix controlling terminal')
    def test_piped_script_reads_installation_answers_from_the_terminal(self):
        shell = f'cat {shlex.quote(str(ROOT / "install.sh"))} | bash -s -- --dir {shlex.quote(str(self.destination))}'
        pid, terminal = pty.fork()
        if pid == 0:
            os.chdir(self.root)
            os.execvpe('bash', ['bash', '-c', shell], self.environment)
        output = bytearray()
        completed = False
        try:
            os.write(terminal, b'5303\nhttp://example.invalid:5303\n')
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if select.select([terminal], [], [], 0.1)[0]:
                    try:
                        chunk = os.read(terminal, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output.extend(chunk)
            waited, status = os.waitpid(pid, os.WNOHANG)
            while waited != pid and time.monotonic() < deadline:
                time.sleep(0.01)
                waited, status = os.waitpid(pid, os.WNOHANG)
            completed = waited == pid
            self.assertTrue(completed, output.decode(errors='replace'))
            self.assertEqual(os.waitstatus_to_exitcode(status), 0, output.decode(errors='replace'))
            self.assertTrue((self.destination / '.env').exists(), output.decode(errors='replace'))
            content = (self.destination / '.env').read_text()
            self.assertIn('SIMKEEP_PORT=5303\n', content)
            self.assertIn('SIMKEEP_PUBLIC_URL=http://example.invalid:5303\n', content)
        finally:
            if not completed:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            os.close(terminal)


if __name__ == '__main__':
    unittest.main()
