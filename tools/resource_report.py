"""Observe an existing Linux quality command; never gate on noisy timing values."""

import argparse
import hashlib
import json
import os
import platform
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

INTERVAL = 0.25
ENVIRONMENT = (
    "CARGO_BUILD_JOBS",
    "RUST_TEST_THREADS",
    "MAKEFLAGS",
    "RUSTUP_TOOLCHAIN",
    "CARGO_TARGET_DIR",
    "RUSTFLAGS",
    "RUSTDOCFLAGS",
    "LLVM_PROFILE_FILE",
    "MALLOC_MMAP_THRESHOLD_",
    "MALLOC_TRIM_THRESHOLD_",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "LD_LIBRARY_PATH",
    "LIBRARY_PATH",
    "RPT_ADVANCED_LIBDIR",
    "RPTADV_QUALITY_IMAGE",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
)


def read(path):
    """Return absent or inaccessible diagnostics as unavailable, not zero."""
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return None


def command_output(command, cwd=None):
    """Read bounded identity commands without adding their cost to the workload."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def identity():
    """Record comparable source, package, compiler, architecture and limit inputs."""
    root = Path.cwd()
    git = ["git", "-c", f"safe.directory={root}"]
    inputs = {}
    for name in ("Cargo.lock", ".github/dependencies.json", "rust-toolchain.toml"):
        path = root / name
        if path.is_file():
            inputs[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            if name.endswith(".json"):
                inputs[name]["contents"] = json.loads(path.read_text())
    group = Path("/sys/fs/cgroup")
    membership = read("/proc/self/cgroup")
    if membership:
        for line in membership.splitlines():
            if line.startswith("0::"):
                candidate = group / line[3:].lstrip("/")
                if (candidate / "memory.max").exists():
                    group = candidate
    return {
        "source_revision": os.getenv("RPTADV_SOURCE_REVISION")
        or command_output(git + ["rev-parse", "HEAD"]),
        "tracked_changes": os.environ.get(
            "RPTADV_SOURCE_TRACKED_DIRTY",
            command_output(git + ["status", "--porcelain", "--untracked-files=no"]),
        ),
        "reporter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "inputs": inputs,
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "os_release": read("/etc/os-release"),
        "logical_cpus": os.cpu_count(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "cpu_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in (read("/proc/cpuinfo") or "").splitlines()
                if line.startswith(("model name", "Model"))
            ),
            None,
        ),
        "cgroup_v2": {
            name: read(group / name)
            for name in (
                "cpu.max",
                "cpuset.cpus.effective",
                "memory.max",
                "memory.swap.max",
                "pids.max",
            )
        },
        "toolchains": {
            name: command_output([name, "--version"])
            for name in ("rustc", "cargo", "cc")
        },
        "installed_packages": command_output(
            ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${Architecture}\n"]
        ),
        "environment": {
            key: os.environ[key] for key in ENVIRONMENT if key in os.environ
        },
        "load_average_before": list(os.getloadavg()),
        "image_digest_note": "RPTADV_QUALITY_IMAGE contains a digest only when the launcher supplies one; a tag alone is not immutable identity",
    }


def process_tree(root_pid):
    """Sample child processes, excluding the reporter; no allocation tracing."""
    processes = {}
    for path in Path("/proc").glob("[0-9]*/stat"):
        raw = read(path)
        if not raw:
            continue
        end = raw.rfind(")")
        fields = raw[end + 2 :].split()
        try:
            pid = int(path.parent.name)
            processes[pid] = {
                "pid": pid,
                "ppid": int(fields[1]),
                "name": raw[raw.find("(") + 1 : end],
                "start_ticks": int(fields[19]),
                "rss_bytes": max(0, int(fields[21])) * os.sysconf("SC_PAGE_SIZE"),
                "cpu_seconds": (int(fields[11]) + int(fields[12]))
                / os.sysconf("SC_CLK_TCK"),
                "threads": int(fields[17]),
            }
        except (ValueError, IndexError):
            continue
    selected = {root_pid}
    while True:
        added = {
            pid for pid, value in processes.items() if value["ppid"] in selected
        } - selected
        if not added:
            break
        selected.update(added)
    return [processes[pid] for pid in selected if pid in processes]


def observe(command, output):
    """Wait once for the real command, retaining its status and kernel accounting."""
    started = time.monotonic()
    contributors = {}
    peak_rss = peak_threads = samples = 0
    usage = None
    with (
        (output / "command.log").open("wb") as log,
        (output / "command.log").open("rb") as tail,
    ):
        try:
            child = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=dict(
                    os.environ, RPTADV_RESOURCE_SNAPSHOT_DIR=str(output / "snapshots")
                ),
            )
        except OSError as error:
            log.write(str(error).encode())
            return 127, {"elapsed_seconds": time.monotonic() - started}, {}

        def forward(signum, _frame):
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

        handlers = {
            sig: signal.signal(sig, forward)
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        }
        try:
            while True:
                current = process_tree(child.pid)
                samples += 1
                peak_rss = max(peak_rss, sum(item["rss_bytes"] for item in current))
                peak_threads = max(
                    peak_threads, sum(item["threads"] for item in current)
                )
                for item in current:
                    key = (item["pid"], item["start_ticks"])
                    previous = contributors.setdefault(key, dict(item))
                    for metric in ("rss_bytes", "cpu_seconds", "threads"):
                        previous[metric] = max(previous[metric], item[metric])
                pid, status, usage = os.wait4(child.pid, os.WNOHANG)
                sys.stdout.buffer.write(tail.read())
                sys.stdout.buffer.flush()
                if pid:
                    child.returncode = os.waitstatus_to_exitcode(status)
                    break
                time.sleep(INTERVAL)
        except BaseException:
            forward(signal.SIGTERM, None)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                forward(signal.SIGKILL, None)
                child.wait()
            raise
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
        elapsed = time.monotonic() - started
    code = child.returncode if child.returncode >= 0 else 128 - child.returncode
    return (
        code,
        {
            "elapsed_seconds": elapsed,
            "user_cpu_seconds": usage.ru_utime,
            "system_cpu_seconds": usage.ru_stime,
            "cpu_percent_one_core": 100 * (usage.ru_utime + usage.ru_stime) / elapsed,
            "largest_process_peak_rss_bytes": usage.ru_maxrss * 1024,
            "major_page_faults": usage.ru_majflt,
            "minor_page_faults": usage.ru_minflt,
            "voluntary_context_switches": usage.ru_nvcsw,
            "involuntary_context_switches": usage.ru_nivcsw,
        },
        {
            "interval_seconds": INTERVAL,
            "samples": samples,
            "process_tree_peak_rss_bytes": peak_rss,
            "process_tree_peak_threads": peak_threads,
            "contributors": sorted(
                contributors.values(), key=lambda item: item["rss_bytes"], reverse=True
            ),
        },
    )


def test_suites(log):
    """Reuse Cargo's existing suite timing; counts are not audio throughput."""
    suites = []
    name = "unidentified suite"
    for line in log.splitlines():
        if "Running " in line or "Doc-tests " in line:
            name = line.strip()
        match = re.search(
            r"test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored;.*finished in ([\d.]+)s",
            line,
        )
        if match:
            state, passed, failed, ignored, elapsed = match.groups()
            suites.append(
                {
                    "name": name,
                    "result": state,
                    "passed": int(passed),
                    "failed": int(failed),
                    "ignored": int(ignored),
                    "seconds": float(elapsed),
                    "executed_tests_per_second": (int(passed) + int(failed))
                    / float(elapsed)
                    if float(elapsed) > 0
                    else None,
                }
            )
    return sorted(suites, key=lambda item: item["seconds"], reverse=True)


def markdown(report):
    """Present optimization leads with explicit measurement limitations."""
    measured, sampled = report["measured"], report["sampled"]

    def mib(value):
        return "unavailable" if value is None else f"{value / 1048576:.2f} MiB"

    limits = report["identity"]["cgroup_v2"]
    lines = [
        f"## Performance and memory: {report['label']}",
        f"Command exit: **{report['exit_code']}**; elapsed **{measured['elapsed_seconds']:.3f} s**.",
        f"Source: {report['identity']['source_revision'] or 'unavailable'}; architecture: {report['identity']['architecture']}.",
        f"CPU quota/period: {limits.get('cpu.max') or 'unavailable'}; memory limit: {limits.get('memory.max') or 'unavailable'} bytes; swap limit: {limits.get('memory.swap.max') or 'unavailable'} bytes.",
        f"Image: {report['identity']['environment'].get('RPTADV_QUALITY_IMAGE', 'unavailable')}.",
        f"CPU user/system: {measured.get('user_cpu_seconds', 'unavailable')} / {measured.get('system_cpu_seconds', 'unavailable')} s.",
        f"Kernel largest-process peak RSS: **{mib(measured.get('largest_process_peak_rss_bytes'))}**.",
        f"Sampled process-tree peak RSS: **{mib(sampled.get('process_tree_peak_rss_bytes'))}**; peak threads: {sampled.get('process_tree_peak_threads', 'unavailable')}.",
        "",
        "### Optimization leads",
        "Largest sampled process contributors (individual maxima, not additive):",
    ]
    for item in sampled.get("contributors", [])[:8]:
        lines.append(
            f"- {item['name']} (PID {item['pid']}): {mib(item['rss_bytes'])}; observed CPU {item['cpu_seconds']:.3f} s; threads {item['threads']}."
        )
    lines.append(
        "Slowest existing Rust suites (includes their fixtures/waits, not a production benchmark):"
    )
    for suite in report["rust_suites"][:8]:
        lines.append(
            f"- {suite['name']}: {suite['seconds']:.2f} s; {suite['passed']} passed, {suite['failed']} failed, {suite['ignored']} ignored."
        )
    lines.append(
        "Lifecycle snapshots (whole test process; admission is not simultaneous active audio):"
    )
    for item in report["lifecycle"]:
        heap = item.get("glibc") or {}
        lines.append(
            f"- {item['workload']} / {item['phase']}: {item['connected_peers']} connected; {item['elapsed_seconds']:.3f} s; RSS {mib(item['rss_bytes'])}; glibc arena in use {mib(heap.get('arena_in_use_bytes'))}, free retained {mib(heap.get('arena_free_retained_bytes'))}, mmap {mib(heap.get('mmap_bytes'))}."
        )
    if not report["lifecycle"]:
        lines.append(
            "- Unavailable: this command/source emitted no lifecycle snapshots."
        )
    lines.extend(
        ["", "### Interpretation", *[f"- {note}" for note in report["caveats"]], ""]
    )
    return "\n".join(lines)


def main():
    """Write artifacts and a GitHub summary even when the observed command fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error(
            "output must be empty, so stale measurements cannot enter this report"
        )
    metadata = identity()
    code, measured, sampled = observe(command, output)
    snapshots = [
        json.loads(path.read_text()) for path in (output / "snapshots").glob("*.json")
    ]
    report = {
        "schema_version": 1,
        "label": args.label,
        "command": command,
        "exit_code": code,
        "identity": metadata,
        "measured": measured,
        "sampled": sampled,
        "estimated": {},
        "rust_suites": test_suites(read(output / "command.log") or ""),
        "lifecycle": sorted(
            snapshots,
            key=lambda item: (item["workload"], item["pid"], item["elapsed_seconds"]),
        ),
        "caveats": [
            "Observations, not timing thresholds. All requested tests/workloads and their failure status are preserved.",
            "Elapsed and CPU include builds, fixtures and subprocesses for the named command. Compare identical commands, source/lockfile/dependency identities, build modes, architectures, limits and allocator settings.",
            "Observed elapsed time includes exit polling (250 ms plus scheduler delay); use suite/benchmark timings for short operations. wait4 peak RSS is the largest process high-water mark, not concurrent tree usage. Sampled RSS sums shared pages and can miss short peaks/processes; it is not PSS. Reporter overhead and host contention affect timing.",
            "glibc arena in-use/free/mmap are measured allocator aggregates, not allocation stack attribution. Tcache and other allocators limit live-object inference. Retained RSS alone is not a leak.",
            "Lifecycle snapshots include fixtures and other tests in the same process; use serial tests. A process lifetime high-water mark may predate the observed test. No allocator trim or production setting is applied.",
            "The unchanged 2000-peer admission regression measures retained sessions at 48 kHz, not 2000 active streams. Existing tests/peer_egress_load.py separately reports real loopback throughput/latency/loss; shared USBRadioPlus AGC tests already report voiced/silence CPU cost.",
            "Coverage instrumentation, debug versus release builds and cold versus warm caches are different workloads. No synthetic capacity estimates are substituted for missing measurements.",
            "Missing fields mean unavailable. Image tags are mutable; retain the launcher digest plus installed package and dependency inputs. SIGKILL/OOM killing the reporter itself can prevent artifact completion.",
        ],
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    summary = markdown(report)
    (output / "report.md").write_text(summary)
    if path := os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a") as stream:
            stream.write(summary)
    print(summary)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
