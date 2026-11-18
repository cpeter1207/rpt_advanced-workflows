"""Pure tests of installed-provider test execution controls."""
import json
import unittest
from pathlib import Path

import installed_phone as runner


class InstalledPhoneTests(unittest.TestCase):
    def test_cargo_artifact_requires_exact_single_test_binary(self):
        artifact = {"reason": "compiler-artifact", "profile": {"test": True}, "target": {"kind": ["lib"]}, "executable": "/tmp/test-binary"}
        self.assertEqual(runner.test_executable(json.dumps(artifact)), Path("/tmp/test-binary"))
        for output in ("", json.dumps(artifact) + "\n" + json.dumps(dict(artifact, executable="/tmp/other"))):
            with self.assertRaises(ValueError):
                runner.test_executable(output)

    def test_runtime_paths_replace_not_append_build_tree_paths(self):
        env = runner.runtime_environment({"LD_LIBRARY_PATH": "/tmp/build", "LD_PRELOAD": "/tmp/stale.so", "RPT_ADVANCED_LIBDIR": "/tmp/old"}, "x86_64-linux-gnu")
        self.assertNotIn("/tmp", env["LD_LIBRARY_PATH"])
        self.assertNotIn("LD_PRELOAD", env)
        self.assertEqual(env["RPT_ADVANCED_LIBDIR"], "/usr/lib/x86_64-linux-gnu/rpt_advanced")
        self.assertEqual(env["URP_PRODUCT_INCLUDE"], "/usr/include")

    def test_private_sofia_prefix_cannot_replace_actual_packages(self):
        original = {"RUNNER_TEMP": "/ci/tmp", "RPTADV_SOFIA_PREFIX": "/ci/tmp/rptadv-sofia-1.13.19"}
        with self.assertRaises(ValueError):
            runner.runtime_environment(original, "aarch64-linux-gnu")

    def test_exact_selection_counts_preserve_all_52(self):
        self.assertEqual(sum(item[3] for item in runner.SELECTIONS), 52)
        self.assertEqual([item[3] for item in runner.SELECTIONS], [5, 2, 37, 1, 7])

    def test_only_owned_recovery_shim_exception(self):
        allowed = Path("/tmp/rptadv-recovery-123/librptadv_codec_g711.so.1")
        self.assertEqual(runner.partition_fixture({allowed}, 123, True), (set(), {allowed}))
        for path, enabled in [(allowed, False), (Path("/tmp/rptadv-recovery-124/librptadv_codec_g711.so.1"), True)]:
            self.assertEqual(runner.partition_fixture({path}, 123, enabled), ({path}, set()))


if __name__ == "__main__":
    unittest.main()
