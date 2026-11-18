"""Run the 52 selected phone assertions directly against installed candidate DSOs."""

import argparse
import json
import os
import signal
import subprocess
from pathlib import Path

from phone_cohort import command, require_tests
from provision_private_sofia import VERSION as SOFIA_VERSION, validate_install
from staged_packages import guard
from staged_phone import loaded_paths, sha256, verify_files, verify_loaded

RECOVERY = "phone::call_media::tests::scripted_recovery_reaches_sink_with_one_decision_across_credit"
SELECTIONS = (
    ("downlink", "rptadv-product", "downlink_", 5),
    ("native-sip", "rpt-advanced-standalone", "real_product_sip_call_", 2),
    ("native-rtp", "rpt-advanced-standalone", "phone::call_media::tests::", 37),
    ("recovery-fixture", "rpt-advanced-standalone", RECOVERY, 1),
    ("native-ring", "rptadv-product", "link::private_phone::tests::native_ring::", 7),
)
REQUIRED = {
    "librptadv_product.so.3", "libusbradioplus_product.so.1",
    "librptadv_portaudio_alsa_adapter.so.2", "librptadvradio.so.5",
    "librptadv_rnnoise_adapter.so.1", "librptadv_codec_g711.so.1",
    "librptadv_sip_adapter.so.1", "usbradioplus_agc.so",
}


def test_executable(output):
    """Select one actual Cargo library test executable, rejecting empty builds."""
    matches = set()
    for line in output.splitlines():
        item = json.loads(line)
        if (item.get("reason") == "compiler-artifact"
                and item.get("profile", {}).get("test")
                and item.get("target", {}).get("kind") == ["lib"]
                and item.get("executable")):
            matches.add(Path(item["executable"]))
    if len(matches) != 1:
        raise ValueError("expected exactly one library test executable")
    return matches.pop()


def runtime_environment(original, multiarch):
    """Replace build-tree lookup paths; Cargo is never the test process launcher."""
    if multiarch not in {"x86_64-linux-gnu", "aarch64-linux-gnu"}:
        raise ValueError("unsupported native multiarch")
    environment = original.copy()
    for key in ("LD_PRELOAD", "LD_AUDIT", "LD_DEBUG", "LD_DEBUG_OUTPUT", "CARGO_TARGET_DIR",
                "CARGO_BUILD_TARGET", "BINDGEN_EXTRA_CLANG_ARGS"):
        environment.pop(key, None)
    library = f"/usr/lib/{multiarch}"
    private = library + "/rpt_advanced"
    environment.update(
        LD_LIBRARY_PATH=f"{private}:{library}", LIBRARY_PATH=f"{private}:{library}",
        RPT_ADVANCED_LIBDIR=private, URP_PRODUCT_INCLUDE="/usr/include",
        RPTADV_CODEC_INCLUDE="/usr/include/rptadv-codec",
        RPTADV_IAX2_INCLUDE="/usr/include/rptadv_iax2",
        RPTADV_SIP_TEST_PROVIDER=private + "/librptadv_sip_adapter.so.1",
        USBRADIOPLUS_AGC_PLUGIN_PATH=library + "/usbradioplus/usbradioplus_agc.so",
        CARGO_BUILD_JOBS="1", RUST_TEST_THREADS="1", CARGO_INCREMENTAL="0",
    )
    environment["TMPDIR"] = "/tmp"
    if original.get("RPTADV_SOFIA_PREFIX"):
        prefix = Path(original["RPTADV_SOFIA_PREFIX"])
        expected = Path(original["RUNNER_TEMP"]) / f"rptadv-sofia-{SOFIA_VERSION}"
        if prefix != expected or not prefix.is_absolute():
            raise ValueError("unverified private Sofia prefix")
        for key in ("LD_LIBRARY_PATH", "LIBRARY_PATH"):
            environment[key] += ":" + str(prefix / "lib")
    return environment


def partition_fixture(paths, parent_pid, enabled):
    """Separate only the known recovery test's own codec shim from package proof."""
    shim = Path(f"/tmp/rptadv-recovery-{parent_pid}/librptadv_codec_g711.so.1")
    fixtures = {shim} & paths if enabled else set()
    return paths - fixtures, fixtures


def verify_observed(paths, files):
    """Bind observed project DSOs to installed archive bytes, including required ones."""
    candidates = {
        Path("/", name).resolve(): digest for name, digest in files.items() if ".so" in name
    }
    names = {path.name.split(".so")[0] for path in candidates}
    required = {}
    for name, digest in files.items():
        if Path(name).name in REQUIRED:
            required[str(Path("/", name))] = digest
    if {Path(name).name for name in required} != REQUIRED:
        raise ValueError("required installed runtime package inventory incomplete")
    for path in paths:
        if path.name.split(".so")[0] in names:
            if candidates.get(path.resolve()) != sha256(path):
                raise ValueError(f"observed project DSO escaped package bytes: {path}")
    verify_loaded(paths, required)
    return {str(path): sha256(path) for path in sorted(paths) if path.is_file()}


def execute(root, architecture):
    """Compile tests without running, then capture the direct native loader traces."""
    guard(architecture)
    output = root / "staged-output"
    logs = output / "installed-tests"
    logs.mkdir()
    receipt = json.loads((output / "installed.json").read_text())
    files = receipt["installed"]["files_sha256"]
    verify_files(Path("/"), files)
    environment = runtime_environment(os.environ, command(["dpkg-architecture", "-qDEB_HOST_MULTIARCH"]))
    if "CARGO_ENCODED_RUSTFLAGS" in environment:
        raise ValueError("encoded Rust flags override warnings")
    environment["RUSTFLAGS"] = (environment.get("RUSTFLAGS", "") + " -Dwarnings").strip()
    prefix = Path(environment["RPTADV_SOFIA_PREFIX"])
    validate_install(prefix)
    sofia_sha256 = sha256(prefix / "lib/libsofia-sip-ua.so.0")
    source = root / "sources/controller"
    executables = {}
    for package in sorted({item[1] for item in SELECTIONS}):
        result = subprocess.run(
            ["cargo", "test", "--locked", "-p", package, "--lib", "--no-run", "--message-format=json"],
            cwd=source, env=environment, text=True, capture_output=True, check=False,
        )
        (logs / f"compile-{package}.jsonl").write_text(result.stdout)
        (logs / f"compile-{package}.stderr").write_text(result.stderr)
        result.check_returncode()
        executables[package] = test_executable(result.stdout)
    observed = set()
    fixture_paths = set()
    results = []
    for label, package, selection, count in SELECTIONS:
        arguments = [str(executables[package]), selection, "--test-threads=1", "--nocapture"]
        if label == "native-rtp":
            arguments += ["--skip", RECOVERY]
        if label == "recovery-fixture":
            arguments += ["--exact"]
        trace = logs / (label + "-loader")
        env = environment | {"LD_DEBUG": "files", "LD_DEBUG_OUTPUT": str(trace)}
        with (logs / f"{label}.log").open("w") as stream:
            process = subprocess.Popen(arguments, cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                status = process.wait(timeout=900)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
        text = (logs / f"{label}.log").read_text()
        if status != 0:
            raise ValueError(f"installed test failed: {label} ({status})")
        require_tests(text, count)
        traces = list(logs.glob(trace.name + ".*"))
        if not traces:
            raise ValueError("missing native loader evidence")
        paths = set().union(*(loaded_paths(path.read_text()) for path in traces))
        paths, fixtures = partition_fixture(paths, process.pid, label == "recovery-fixture")
        observed |= paths
        fixture_paths |= fixtures
        results.append({"selection": selection, "passed": count, "executable": str(executables[package]),
                        "executable_sha256": sha256(executables[package])})
    loaded = verify_observed(observed, files)
    verify_files(Path("/"), files)
    (output / "installed-tests.json").write_text(json.dumps({
        "scope": "52 selected installed-provider assertions; not hardware acceptance",
        "architecture": architecture, "results": results, "loaded_sha256": loaded,
        "private_sofia_sha256": sofia_sha256,
        "intentional_recovery_fixture_paths": sorted(map(str, fixture_paths)),
        "fixture_source_sha256": sha256(source / "rust/standalone/tests/fixtures/phone_codec.c"),
    }, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", required=True, choices=("amd64", "arm64"))
    args = parser.parse_args()
    execute(Path.cwd().resolve(), args.arch)


if __name__ == "__main__":
    main()
