"""Check the private dependency boundary without downloading or building Sofia."""

import importlib.util
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/provision_private_sofia.py"


class PrivateSofiaTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "private Sofia provisioner is missing")
        spec = importlib.util.spec_from_file_location("private_sofia", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_archive_hash_rejects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "source.tar.gz"
            archive.write_bytes(b"not the pinned release")
            with self.assertRaisesRegex(ValueError, "checksum"):
                self.module.verify_archive(archive)

    def test_prefix_must_be_a_new_private_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(
                self.module.private_prefix(root), root / "rptadv-sofia-1.13.19"
            )
            (root / "rptadv-sofia-1.13.19").mkdir()
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.module.private_prefix(root)

    def test_missing_header_fails_install_validation(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "header"),
        ):
            self.module.validate_install(Path(directory))

    def test_wrong_installed_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            header = prefix / "include/sofia-sip-1.13/sofia-sip/bnf.h"
            header.parent.mkdir(parents=True)
            header.write_text("/* test header */")
            pc = prefix / "lib/pkgconfig/sofia-sip-ua.pc"
            pc.parent.mkdir(parents=True)
            pc.write_text(
                "Name: sofia-sip-ua\nDescription: wrong version fixture\nVersion: 1.12.11\n"
            )
            with self.assertRaisesRegex(ValueError, "incorrect Sofia version"):
                self.module.validate_install(prefix)

    def test_existing_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rptadv-sofia-1.13.19").symlink_to(root / "missing")
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.module.private_prefix(root)

    def test_environment_rejects_github_environment_injection(self):
        with self.assertRaisesRegex(ValueError, "newline"):
            self.module.build_environment(
                Path("/tmp/prefix"), {"LD_LIBRARY_PATH": "x\nBAD=value"}
            )

    def test_environment_preserves_existing_paths_and_exports_both_consumers(self):
        prefix = Path("/temporary/private-sofia")
        result = self.module.build_environment(prefix, {"LD_LIBRARY_PATH": "/existing"})
        self.assertEqual(result["SOFIA_PREFIX"], str(prefix))
        self.assertEqual(result["RPTADV_SOFIA_PREFIX"], str(prefix))
        self.assertEqual(result["LD_LIBRARY_PATH"], str(prefix / "lib") + ":/existing")
        self.assertEqual(result["PKG_CONFIG_PATH"], str(prefix / "lib/pkgconfig"))

    def test_action_shell_programs(self):
        action = (
            ROOT / ".github/actions/provision-private-sofia/action.yml"
        ).read_text()
        blocks = re.findall(r"(?m)^      run: \|\n((?:        .*\n|\n)+)", action)
        inline = re.findall(r"(?m)^      run: (?!\|)(.*)$", action)
        self.assertEqual(len(blocks) + len(inline), 2)
        for script in [textwrap.dedent(block) for block in blocks] + inline:
            subprocess.run(
                ["shellcheck", "--shell=bash", "-"], input=script, text=True, check=True
            )

    def test_preflight_and_all_quality_jobs_provision(self):
        for name, count in [("preflight.yml", 1), ("quality.yml", 3)]:
            workflow = (ROOT / ".github/workflows" / name).read_text()
            self.assertEqual(
                workflow.count("/.github/actions/provision-private-sofia@main"), count
            )
        action = (
            ROOT / ".github/actions/provision-private-sofia/action.yml"
        ).read_text()
        self.assertNotIn("upload-artifact", action)
        self.assertNotIn("docker push", action)
        self.assertIn("provision_private_sofia.py", action)


if __name__ == "__main__":
    unittest.main()
