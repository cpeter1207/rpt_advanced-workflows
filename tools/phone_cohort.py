"""Identity and result checks for CI-only native phone qualification."""

import argparse
import hashlib
import json
import re
import struct
import subprocess
import urllib.request
from pathlib import Path

REPOSITORIES = {
    "controller": "cpeter1207/rpt_advanced",
    "sdk": "cpeter1207/USBRadioPlus",
    "adapter": "cpeter1207/rptadv-portaudio-alsa-adapter",
    "codec": "cpeter1207/rptadv-codec-adapters",
    "radio": "cpeter1207/librptadvradio",
    "rnnoise": "cpeter1207/rptadv-rnnoise-adapter",
}
MACHINES = {"amd64": 62, "arm64": 183}


# Released development headers, verified against the retained signed packages.
HEADER_INPUTS = {
    "rptadvremote/rptadvremote.h": {
        "repository": "cpeter1207/librptadvremote",
        "sha": "041b16b253853d70ef02caf08e217fae06e7e2e3",
        "sha256": "696b3c9864ff3ed1b53263f159487b91e2d5941dd2b80b9830f1ada3054e7d5a",
    },
    "rptadv_hamlib_adapter/rptadv_hamlib_adapter.h": {
        "repository": "cpeter1207/rptadv-hamlib-adapter",
        "sha": "fb054d720c6b894008b277fe7cc9737dc7173ff1",
        "sha256": "7d2a2b9b6c84bab6d1d9cfeadf12b0ee92006e943676c7d947a1af1401fe946c",
    },
}


def prepare_headers(root):
    """Fetch only immutable reviewed headers and fail before writing wrong bytes."""
    for name, item in HEADER_INPUTS.items():
        url = f"https://raw.githubusercontent.com/{item['repository']}/{item['sha']}/include/{name}"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"header hash mismatch: {name}")
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def header_receipt(root):
    """Recheck supplemental header bytes before recording their provenance."""
    for name, item in HEADER_INPUTS.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"header hash mismatch: {name}")
    return HEADER_INPUTS


def validate_manifest(manifest):
    """Accept only the complete fixed repository set at immutable commits."""
    if set(manifest) != set(REPOSITORIES):
        raise ValueError("incorrect cohort roles")
    for role, repo in REPOSITORIES.items():
        item = manifest[role]
        if set(item) != {"repository", "sha"} or item["repository"] != repo:
            raise ValueError(f"incorrect repository for {role}")
        if not re.fullmatch("[0-9a-f]{40}", item["sha"]):
            raise ValueError(f"immutable commit required for {role}")


def verify_elf(path, arch):
    """Require a native 64-bit little-endian ELF, independent of file naming."""
    data = path.read_bytes()[:64]
    if (
        len(data) != 64
        or data[:6] != b"\x7fELF\x02\x01"
        or struct.unpack_from("<H", data, 18)[0] != MACHINES[arch]
    ):
        raise ValueError(f"wrong ELF architecture: {path}")


def require_tests(output, expected):
    """Reject zero selections, failures, ignored cases and unexpected counts."""
    summaries = re.findall(
        r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;", output
    )
    if summaries != [(str(expected), "0", "0")]:
        raise ValueError("unexpected test result count")


def dependencies(output):
    """Parse every resolved ldd entry, including indented transitive libraries."""
    if "not found" in output:
        raise ValueError("unresolved dependency")
    return dict(re.findall(r"^\s*(\S+) => (/\S+)", output, re.MULTILINE))


def command(args, cwd=None):
    """Run one explicit command without shell interpolation."""
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def workflow_commit():
    """Read the Actions checkout SHA despite its different container owner."""
    root = Path(__file__).resolve().parents[1]
    # Trust only this checkout for this read; never persist or wildcard trust.
    return command(["git", "-c", f"safe.directory={root}", "rev-parse", "HEAD"], root)


def checkout(manifest, root):
    """Fetch only fixed public repositories and verify their exact source pins."""
    root.mkdir(parents=True, exist_ok=True)
    for role, item in manifest.items():
        path = root / role
        path.mkdir()
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(path),
                "fetch",
                "--depth=1",
                f"https://github.com/{item['repository']}.git",
                item["sha"],
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "checkout", "--detach", "FETCH_HEAD"], check=True
        )
        verify_source(path, item["sha"])


def verify_source(path, sha):
    """Reject changed commits or tracked source before recording qualification."""
    if command(["git", "rev-parse", "HEAD"], path) != sha:
        raise ValueError(f"source commit mismatch: {path}")
    if command(["git", "status", "--porcelain", "--untracked-files=no"], path):
        raise ValueError(f"modified source: {path}")


def receipt(manifest, root, runtime, arch, image):
    """Record architecture-specific hashes, exact sources and resolved DSOs."""
    if command(["dpkg", "--print-architecture"]) != arch:
        raise ValueError("runner architecture mismatch")
    if not re.fullmatch(
        r"ghcr.io/cpeter1207/rpt-advanced-quality-debian13@sha256:[0-9a-f]{64}", image
    ):
        raise ValueError("resolved quality image digest required")
    for role, item in manifest.items():
        verify_source(root / role, item["sha"])
    libraries = sorted(p for p in runtime.iterdir() if p.is_file() and ".so" in p.name)
    if not libraries:
        raise ValueError("empty runtime")
    required = {
        "librptadv_product.so.3",
        "libusbradioplus_product.so.1",
        "librptadv_portaudio_alsa_adapter.so.2",
        "librptadvradio.so.5",
        "librptadv_rnnoise_adapter.so.1",
        "librptadv_codec_g711.so.1",
        "librptadv_sip_adapter.so.1",
        "usbradioplus_agc.so",
    }
    if not required.issubset({p.name for p in libraries}):
        raise ValueError("incomplete candidate runtime")
    hashes = {}
    resolved = {}
    names = {p.name for p in libraries}
    for path in libraries:
        verify_elf(path, arch)
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        output = command(["ldd", str(path)])
        for name, target in dependencies(output).items():
            if name in names and Path(target).resolve().parent != runtime.resolve():
                raise ValueError(f"candidate dependency escaped runtime: {name}")
            if Path(target).is_file():
                verify_elf(Path(target), arch)
                resolved[target] = hashlib.sha256(Path(target).read_bytes()).hexdigest()
    return {
        "scope": "CI-only; not release or physical hardware qualification",
        "architecture": arch,
        "image": image,
        "sources": manifest,
        "supplemental_headers": header_receipt(runtime.parent / "include"),
        "workflow_commit": workflow_commit(),
        "build_script_sha256": hashlib.sha256(
            Path("tools/run_phone_cohort.sh").read_bytes()
        ).hexdigest(),
        "runtime_sha256": hashes,
        "resolved_dependencies_sha256": resolved,
        "packages": command(["dpkg-query", "-W"]),
    }


def main():
    """Expose narrowly scoped checkout, test-result and provenance operations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("checkout", "receipt", "tests", "headers"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--arch", choices=MACHINES)
    parser.add_argument("--image")
    parser.add_argument("--log", type=Path)
    parser.add_argument("--expected", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "headers":
        prepare_headers(args.output)
        return
    if args.action == "tests":
        require_tests(args.log.read_text(), args.expected)
        return
    manifest = json.loads(args.manifest.read_text())
    validate_manifest(manifest)
    if args.action == "checkout":
        checkout(manifest, args.sources.resolve())
    else:
        result = receipt(
            manifest,
            args.sources.resolve(),
            args.runtime.resolve(),
            args.arch,
            args.image,
        )
        args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
