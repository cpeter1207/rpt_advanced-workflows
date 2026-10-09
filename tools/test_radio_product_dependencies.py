#!/usr/bin/env python3
"""Verify the signed-APT radio product input without network or installation."""

import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINGERPRINT = "A0D5A79E0F5C45E9E63679950951502BAC795E55"


class RadioProductDependencies(unittest.TestCase):
    def test_signed_download_is_scoped_and_rejects_wrong_key(self):
        source = (
            ROOT / ".github/actions/install-shared-dependencies/action.yml"
        ).read_text()
        step = source.split("    - name: Download signed radio product packages\n", 1)[
            1
        ]
        script = textwrap.dedent(
            re.search(r"(?m)^      run: \|\n((?:        .*\n|\n)+)", step).group(1)
        )
        mocks = """
curl() { touch "${@: -1}"; }
gpg() { printf '%s\\n' "$TEST_KEY_LIST"; }
apt-get() { printf '%s\\n' "$*" >> "$APT_LOG"; }
"""
        for fingerprints, accepted in (
            ((FINGERPRINT,), True),
            (("WRONG",), False),
            ((FINGERPRINT, "WRONG"), False),
        ):
            with (
                self.subTest(fingerprints=fingerprints),
                tempfile.TemporaryDirectory() as work,
            ):
                log = Path(work) / "apt.log"
                result = subprocess.run(
                    ["bash", "-c", mocks + script],
                    env=dict(
                        os.environ,
                        GITHUB_WORKSPACE=work,
                        APT_LOG=str(log),
                        TEST_KEY_LIST="\n".join(
                            f"pub::::::::::\nfpr:::::::::{fingerprint}:"
                            for fingerprint in fingerprints
                        ),
                    ),
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if not accepted:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(log.exists())
                    continue
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = log.read_text().splitlines()
                self.assertEqual(len(calls), 2)
                self.assertIn("Dir::Etc::sourceparts=-", calls[0])
                self.assertIn("Dir::State::lists=", calls[0])
                self.assertTrue(calls[0].endswith(" update"))
                self.assertEqual(
                    calls[1].split(" download ", 1)[1].split(),
                    [
                        "libusbradioplus-product1",
                        "libusbradioplus-product-dev",
                        "librptadv-rnnoise-adapter1",
                        "librnnoise0",
                    ],
                )

    def test_action_shell_programs(self):
        source = (
            ROOT / ".github/actions/install-shared-dependencies/action.yml"
        ).read_text()
        scripts = re.findall(r"(?m)^      run: \|\n((?:        .*\n|\n)+)", source)
        self.assertEqual(len(scripts), 3)
        for script in scripts:
            subprocess.run(
                ["shellcheck", "--shell=bash", "-"],
                input=textwrap.dedent(script),
                text=True,
                check=True,
            )

    def test_image_checks_product_abi_header_and_soname(self):
        source = (ROOT / ".github/workflows/images.yml").read_text()
        self.assertIn(
            'pkg-config --variable=abi_version usbradioplus_product)" = 1', source
        )
        self.assertIn("/usr/include/usbradioplus_product.h", source)
        self.assertIn("/libusbradioplus_product.so.1", source)


if __name__ == "__main__":
    unittest.main()
