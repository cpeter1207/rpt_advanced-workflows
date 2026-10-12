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

    def test_image_verification_shell(self):
        source = (ROOT / ".github/workflows/images.yml").read_text()
        script = source.split("\"$IMAGE\" sh -c '\n", 1)[1].split("\n          '\n", 1)[0]
        subprocess.run(
            ["shellcheck", "--shell=sh", "-"],
            input=textwrap.dedent(script), text=True, check=True,
        )

    def test_controller_download_route_selects_released_owners_and_providers(self):
        source = (ROOT / ".github/actions/install-shared-dependencies/action.yml").read_text()
        route = source.split(
            "        download rate_adjusting_pcm_ring", 1
        )[1].split('        if [[ "$INSTALL_PACKAGES" == true ]]; then', 1)[0]
        script = (
            'set -euo pipefail\n'
            'download() { printf "%s\\n" "$*" >> "$DOWNLOAD_LOG"; }\n'
            'download rate_adjusting_pcm_ring ' + textwrap.dedent(route)
        )
        with tempfile.TemporaryDirectory() as work:
            log = Path(work) / "downloads.log"
            result = subprocess.run(
                ["bash", "-c", script],
                env=dict(os.environ, DOWNLOAD_LOG=str(log)),
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = {
                "rate_adjusting_pcm_ring v3.0.0-alpha2 librate-adjusting-pcm-ring3",
                "rate_adjusting_pcm_ring v3.0.0-alpha2 librate-adjusting-pcm-ring3-dev",
                "rptadv-samplerate-adapter v0.2.0-alpha1 librptadv-samplerate-adapter2",
                "rptadv-samplerate-adapter v0.2.0-alpha1 librptadv-samplerate-adapter-dev",
                "librptadviax2 v0.1.0-alpha4 librptadv-iax2-client1",
                "librptadviax2 v0.1.0-alpha4 librptadv-iax2-client-dev",
            }
            for repository, tag, runtime, development in (
                ("librptadvradio", "v0.1.0-alpha.7", "librptadvradio4", "librptadvradio-dev"),
                ("rptadv-gpio-adapter", "v0.1.0-alpha.3", "librptadv-gpio-adapter1",
                 "librptadv-gpio-adapter-dev"),
                *((f"librptadv{name}", "v0.1.0-alpha.1", f"librptadv{name}1",
                   f"librptadv{name}-dev") for name in (
                    "squelch", "ctcss", "dcs", "signaling", "tone", "morse",
                    "dtmf", "template", "schedule",
                )),
            ):
                expected.add(f"{repository} {tag} {runtime}")
                expected.add(f"{repository} {tag} {development}")
            actual = log.read_text().splitlines()
            self.assertEqual(len(actual), len(expected))
            self.assertEqual(set(actual), expected)

    def test_image_checks_new_owner_and_provider_sonames(self):
        source = (ROOT / ".github/workflows/images.yml").read_text()
        for package, pc_name, soname in (
            ("librptadvradio4", "rptadvradio", "librptadvradio.so.4"),
            ("librptadv-gpio-adapter1", "rptadv_gpio_adapter", "librptadv_gpio_adapter.so.1"),
        ):
            with self.subTest(package=package):
                self.assertIn(package, source)
                self.assertIn(f"pkg-config --exists {pc_name}", source)
                self.assertIn(soname, source)
        self.assertIn('pkg-config --variable=abi_version rptadvradio)" = 4', source)

        components = ("squelch", "ctcss", "dcs", "signaling", "tone", "morse",
                      "dtmf", "template", "schedule")
        match = re.search(r"for component in ([^;]+); do\n(.*?)\n            done &&", source, re.DOTALL)
        self.assertIsNotNone(match, "provider image-verification loop missing")
        self.assertEqual(match.group(1).split(), list(components))
        script = (
            'set -eu\n'
            'dpkg-query() { printf "%s\\n" "$@" >> "$PACKAGE_LOG"; }\n'
            'pkg-config() { case "$1" in --exists) return 0;; '
            '--variable=abi_version) printf 1;; '
            '--variable=libdir) printf "%s" "$LIBDIR";; esac; }\n'
            + textwrap.dedent(match.group(0)).removesuffix(" &&")
        )
        with tempfile.TemporaryDirectory() as work:
            directory = Path(work)
            for name in components:
                (directory / f"librptadv{name}.so.1").touch()
            log = directory / "packages.log"
            environment = dict(os.environ, LIBDIR=str(directory), PACKAGE_LOG=str(log))
            result = subprocess.run(["bash", "-c", script], env=environment,
                                    text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(set(log.read_text().splitlines()) - {"-W"}, {
                package for name in components
                for package in (f"librptadv{name}1", f"librptadv{name}-dev")
            })
            (directory / "librptadvmorse.so.1").unlink()
            result = subprocess.run(["bash", "-c", script], env=environment,
                                    text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
