"""Build pinned, dynamic Sofia only in an ephemeral CI job's private prefix.

This is test provisioning, not a distributable dependency package or license
clearance. Keep upstream defaults, including OpenSSL, unchanged.
"""

import hashlib
import os
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

VERSION = "1.13.19"
SHA256 = "99389b574dfcff5775b260dd9ef1bdd2bcb5a42e655bd229d477e488e658064f"
URL = f"https://codeload.github.com/freeswitch/sofia-sip/tar.gz/refs/tags/v{VERSION}"


def verify_archive(archive):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise ValueError("Sofia source checksum mismatch")


def private_prefix(root):
    root = root.resolve(strict=True)
    prefix = root / f"rptadv-sofia-{VERSION}"
    if prefix.exists() or prefix.is_symlink():
        raise ValueError("private Sofia prefix already exists")
    return prefix


def build_environment(prefix, previous):
    result = {"SOFIA_PREFIX": str(prefix), "RPTADV_SOFIA_PREFIX": str(prefix)}
    for name, suffix in [
        ("LIBRARY_PATH", "lib"),
        ("LD_LIBRARY_PATH", "lib"),
        ("PKG_CONFIG_PATH", "lib/pkgconfig"),
    ]:
        result[name] = str(prefix / suffix)
        if previous.get(name):
            result[name] += ":" + previous[name]
    if any("\n" in value or "\r" in value for value in result.values()):
        raise ValueError("invalid newline in build environment")
    return result


def validate_install(prefix):
    if not (prefix / "include/sofia-sip-1.13/sofia-sip/bnf.h").is_file():
        raise ValueError("missing Sofia header")
    env = dict(
        os.environ, PKG_CONFIG_LIBDIR=str(prefix / "lib/pkgconfig"), PKG_CONFIG_PATH=""
    )
    version = subprocess.check_output(
        ["pkg-config", "--modversion", "sofia-sip-ua"], env=env, text=True
    ).strip()
    if version != VERSION:
        raise ValueError("incorrect Sofia version")
    library = prefix / "lib/libsofia-sip-ua.so.0"
    dynamic = subprocess.check_output(["readelf", "-d", str(library)], text=True)
    if "Library soname: [libsofia-sip-ua.so.0]" not in dynamic:
        raise ValueError("incorrect Sofia SONAME")
    relocations = subprocess.check_output(["ldd", "-r", str(library)], text=True)
    if "not found" in relocations or "undefined symbol" in relocations:
        raise ValueError("unresolved Sofia runtime dependency")
    print(
        f"SOFIA_VERSION={version} SOFIA_SHA256={hashlib.sha256(library.read_bytes()).hexdigest()}",
        flush=True,
    )


def main():
    root = Path(os.environ["RUNNER_TEMP"])
    prefix = private_prefix(root)
    environment = build_environment(prefix, os.environ)
    with tempfile.TemporaryDirectory(prefix="sofia-source-", dir=root) as temporary:
        work = Path(temporary)
        archive = work / "source.tar.gz"
        with urllib.request.urlopen(URL, timeout=60) as response:
            archive.write_bytes(response.read())
        verify_archive(archive)
        with tarfile.open(archive) as source:
            source.extractall(work, filter="data")
        source = work / f"sofia-sip-{VERSION}"
        for command in (
            ["autoreconf", "-fi"],
            ["./configure", f"--prefix={prefix}", "--disable-static"],
            ["make", "-C", "libsofia-sip-ua", "-j1"],
            ["make", "-C", "libsofia-sip-ua", "install"],
            ["make", "-C", "packages", "install-pkgconfigDATA"],
        ):
            subprocess.run(command, cwd=source, check=True, timeout=600)
    validate_install(prefix)
    with Path(os.environ["GITHUB_ENV"]).open("a") as output:
        output.writelines(f"{key}={value}\n" for key, value in environment.items())
    print(
        "Private CI dependency only; distribution qualification remains blocked.",
        flush=True,
    )


if __name__ == "__main__":
    main()
