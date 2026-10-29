#!/usr/bin/env python3
"""Verify dependency downloads without external network or installation."""

import os
import re
import socket
import struct
import subprocess
import tempfile
import textwrap
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINGERPRINT = "A0D5A79E0F5C45E9E63679950951502BAC795E55"


class RadioProductDependencies(unittest.TestCase):
    def test_dependency_downloads_retry_connection_resets_with_bounded_attempts(self):
        source = (
            ROOT / ".github/actions/install-shared-dependencies/action.yml"
        ).read_text()
        commands = re.findall(r"(?m)^ *curl [^\n]*\\\n[^\n]+", source)
        self.assertEqual(len(commands), 2)

        class ResetThenServe(BaseHTTPRequestHandler):
            def do_GET(self):
                self.server.attempts += 1
                if self.server.attempts <= self.server.failures:
                    self.connection.setsockopt(
                        socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
                    )
                    self.close_connection = True
                    self.connection.close()
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"verified dependency fixture")

            def log_message(self, _format, *args):
                pass

        for index, command in enumerate(commands):
            for failures, accepted, attempts in ((1, True, 2), (10, False, 4)):
                with (
                    self.subTest(download=index, failures=failures),
                    tempfile.TemporaryDirectory() as work,
                    HTTPServer(("127.0.0.1", 0), ResetThenServe) as server,
                ):
                    server.attempts = 0
                    server.failures = failures
                    thread = threading.Thread(target=server.serve_forever)
                    thread.start()
                    url = f"http://127.0.0.1:{server.server_port}"
                    try:
                        result = subprocess.run(
                            ["bash", "-c", command],
                            env=dict(
                                os.environ,
                                repository=url,
                                temporary=work,
                                file=str(Path(work) / "package.deb"),
                                asset='{"browser_download_url":"' + url + '/package"}',
                            ),
                            text=True,
                            capture_output=True,
                            check=False,
                        )
                    finally:
                        server.shutdown()
                        thread.join()
                    self.assertEqual(result.returncode == 0, accepted, result.stderr)
                    self.assertEqual(server.attempts, attempts)
                    if accepted:
                        payloads = list(Path(work).iterdir())
                        self.assertEqual(len(payloads), 1)
                        self.assertEqual(
                            payloads[0].read_bytes(), b"verified dependency fixture"
                        )

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
dpkg-deb() { printf '%s\\n' "$TEST_USB_VERSION"; }
"""
        for fingerprints, version, accepted in (
            ((FINGERPRINT,), "0.1.0~alpha24-1.deb13", True),
            ((FINGERPRINT,), "0.1.0~alpha25-1.deb13", True),
            ((FINGERPRINT,), "0.1.0~alpha23-1.deb13", False),
            (("WRONG",), "0.1.0~alpha24-1.deb13", False),
            ((FINGERPRINT, "WRONG"), "0.1.0~alpha24-1.deb13", False),
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
                        TEST_USB_VERSION=version,
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
                    if fingerprints != (FINGERPRINT,):
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

    def test_image_supplies_site_adapter_dependencies(self):
        dockerfile = (ROOT / "containers/quality.Dockerfile").read_text()
        verification = (ROOT / ".github/workflows/images.yml").read_text()
        for package in ("libsensors-dev", "libsensors5", "libgpiod-dev", "libgpiod3"):
            self.assertIn(package, dockerfile)
            self.assertIn(package, verification)
        for header in ("/usr/include/sensors/sensors.h", "/usr/include/gpiod.h"):
            self.assertIn(header, verification)
        self.assertIn("0.1.0~alpha24-1.deb13", verification)

    def test_image_verification_shell(self):
        source = (ROOT / ".github/workflows/images.yml").read_text()
        script = source.split('"$IMAGE" sh -c \'\n', 1)[1].split("\n          '\n", 1)[
            0
        ]
        subprocess.run(
            ["shellcheck", "--shell=sh", "-"],
            input=textwrap.dedent(script),
            text=True,
            check=True,
        )

    def test_image_iax_probe_requires_the_installed_abi2_library(self):
        source = (ROOT / ".github/workflows/images.yml").read_text()
        probe = source.split("            pkg-config --exists rptadv_iax2 &&\n", 1)[
            1
        ].split("            jq --version &&\n", 1)[0]
        tools = """
pkg-config() {
    case "$1" in
        --variable=abi_version) printf '%s\\n' "$TEST_ABI" ;;
        --variable=libdir) printf '%s\\n' "$TEST_LIBDIR" ;;
        *) return 1 ;;
    esac
}
"""
        for abi, available, accepted in (
            (2, True, True),
            (1, True, False),
            (2, False, False),
        ):
            with (
                self.subTest(abi=abi, available=available),
                tempfile.TemporaryDirectory() as work,
            ):
                root = Path(work)
                header = root / "rptadv_iax2_client.h"
                header.touch()
                if available:
                    (root / "librptadviax2.so.2").touch()
                script = (
                    probe.replace(
                        "/usr/include/rptadv_iax2/rptadv_iax2_client.h", str(header)
                    )
                    .rstrip()
                    .removesuffix("&&")
                )
                result = subprocess.run(
                    ["bash", "-ec", tools + script],
                    env=dict(os.environ, TEST_ABI=str(abi), TEST_LIBDIR=work),
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode == 0, accepted, result.stderr)

    def test_controller_download_route_selects_released_owners_and_providers(self):
        source = (
            ROOT / ".github/actions/install-shared-dependencies/action.yml"
        ).read_text()
        route = source.split("        download rate_adjusting_pcm_ring", 1)[1].split(
            '        if [[ "$INSTALL_PACKAGES" == true ]]; then', 1
        )[0]
        script = (
            "set -euo pipefail\n"
            'download() { printf "%s\\n" "$*" >> "$DOWNLOAD_LOG"; }\n'
            "download rate_adjusting_pcm_ring " + textwrap.dedent(route)
        )
        with tempfile.TemporaryDirectory() as work:
            log = Path(work) / "downloads.log"
            result = subprocess.run(
                ["bash", "-c", script],
                env=dict(os.environ, DOWNLOAD_LOG=str(log)),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = {
                "rate_adjusting_pcm_ring v3.0.0-alpha2 librate-adjusting-pcm-ring3",
                "rate_adjusting_pcm_ring v3.0.0-alpha2 librate-adjusting-pcm-ring3-dev",
                "rptadv-samplerate-adapter v0.2.0-alpha1 librptadv-samplerate-adapter2",
                "rptadv-samplerate-adapter v0.2.0-alpha1 librptadv-samplerate-adapter-dev",
                "librptadviax2 v0.1.0-alpha5 librptadv-iax2-client1",
                "librptadviax2 v0.1.0-alpha5 librptadv-iax2-client-dev",
            }
            for repository, tag, runtime, development in (
                (
                    "librptadvradio",
                    "v0.1.0-alpha.8",
                    "librptadvradio4",
                    "librptadvradio-dev",
                ),
                (
                    "rptadv-gpio-adapter",
                    "v0.1.0-alpha.4",
                    "librptadv-gpio-adapter1",
                    "librptadv-gpio-adapter-dev",
                ),
                (
                    "librptadvsquelch",
                    "v0.1.0-alpha.2",
                    "librptadvsquelch2",
                    "librptadvsquelch-dev",
                ),
                (
                    "librptadvctcss",
                    "v0.1.0-alpha.2",
                    "librptadvctcss2",
                    "librptadvctcss-dev",
                ),
                (
                    "librptadvdtmf",
                    "v0.1.0-alpha.2",
                    "librptadvdtmf1",
                    "librptadvdtmf-dev",
                ),
                *(
                    (
                        f"librptadv{name}",
                        "v0.1.0-alpha.1",
                        f"librptadv{name}1",
                        f"librptadv{name}-dev",
                    )
                    for name in (
                        "dcs",
                        "signaling",
                        "tone",
                        "morse",
                        "template",
                        "schedule",
                    )
                ),
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
            (
                "librptadv-gpio-adapter1",
                "rptadv_gpio_adapter",
                "librptadv_gpio_adapter.so.1",
            ),
        ):
            with self.subTest(package=package):
                self.assertIn(package, source)
                self.assertIn(f"pkg-config --exists {pc_name}", source)
                self.assertIn(soname, source)
        self.assertIn('pkg-config --variable=abi_version rptadvradio)" = 4', source)

        components = (
            "squelch",
            "ctcss",
            "dcs",
            "signaling",
            "tone",
            "morse",
            "dtmf",
            "template",
            "schedule",
        )
        match = re.search(
            r"for component in ([^;]+); do\n(.*?)\n            done &&",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "provider image-verification loop missing")
        self.assertEqual(match.group(1).split(), list(components))
        script = (
            "set -eu\n"
            'dpkg-query() { printf "%s\\n" "$@" >> "$PACKAGE_LOG"; }\n'
            'pkg-config() { case "$1" in --exists) return 0;; '
            '--variable=abi_version) case "$2" in '
            'rptadvsquelch|rptadvctcss) printf "%s" "${ABI2:-2}";; '
            "*) printf 1;; esac;; "
            '--variable=libdir) printf "%s" "$LIBDIR";; esac; }\n'
            + textwrap.dedent(match.group(0)).removesuffix(" &&")
        )
        with tempfile.TemporaryDirectory() as work:
            directory = Path(work)
            for name in components:
                abi = 2 if name in ("squelch", "ctcss") else 1
                (directory / f"librptadv{name}.so.{abi}").touch()
            log = directory / "packages.log"
            environment = dict(os.environ, LIBDIR=str(directory), PACKAGE_LOG=str(log))
            result = subprocess.run(
                ["bash", "-c", script],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                set(log.read_text().splitlines()) - {"-W"},
                {
                    package
                    for name in components
                    for package in (
                        f"librptadv{name}{2 if name in ('squelch', 'ctcss') else 1}",
                        f"librptadv{name}-dev",
                    )
                },
            )
            result = subprocess.run(
                ["bash", "-c", script],
                env=dict(environment, ABI2="1"),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(
                result.returncode, 0, "ABI 1 must fail for ABI 2 providers"
            )
            (directory / "librptadvmorse.so.1").unlink()
            result = subprocess.run(
                ["bash", "-c", script],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
