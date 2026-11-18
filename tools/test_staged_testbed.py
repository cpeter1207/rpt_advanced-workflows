"""Fast contracts for the hosted-only native RNNoise testbed."""
import unittest

from staged_testbed import build_arguments, validate_host


class TestbedTests(unittest.TestCase):
    def test_build_binds_native_platform_and_immutable_base(self):
        image = 'ghcr.io/cpeter1207/rpt-advanced-quality-debian13@sha256:' + 'a' * 64
        args = build_arguments('arm64', image, '/source', '/receipt')
        self.assertIn('linux/arm64', args)
        self.assertIn('BASE_IMAGE=' + image, args)
        self.assertIn('/source/containers/quality.Dockerfile', args)
        self.assertNotIn('--push', args)
        self.assertNotIn('--tag', args)
        with self.assertRaises(ValueError):
            build_arguments('arm64', 'image:latest', '/source', '/receipt')

    def test_host_guard_rejects_development_and_emulation(self):
        environment = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted'}
        validate_host(environment, 'arm64', 'aarch64', 20 * 1024**3)
        for env, arch, machine, free in (({}, 'arm64', 'aarch64', 20 * 1024**3),
                                        (environment, 'arm64', 'x86_64', 20 * 1024**3),
                                        (environment, 'arm64', 'aarch64', 1)):
            with self.assertRaises(ValueError):
                validate_host(env, arch, machine, free)


if __name__ == '__main__':
    unittest.main()
