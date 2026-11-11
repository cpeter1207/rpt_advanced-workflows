#!/bin/sh
## @file
## @brief Run a command in a disposable labeled container for an explicit workspace.
set -eu

if [ "$#" -lt 3 ]; then
	printf '%s\n' "usage: $0 IMAGE WORKSPACE COMMAND [ARG...]" >&2
	exit 2
fi

image=$1
workspace=$2
shift 2
root=$(CDPATH='' cd -- "$workspace" && pwd)
project=$(basename "$root")
scope=$(printf '%s' "$root" | cksum | awk '{print $1}')
project_label="org.rptadvanced.test.project=$project"
scope_label="org.rptadvanced.test.scope=$scope"
name="$project-test-$scope-$$"
pull_image=${RPTADV_CONTAINER_PULL:-1}
pass_docker_socket=${RPTADV_CONTAINER_DOCKER_SOCKET:-0}
case $pass_docker_socket in
	0|1) ;;
	*)
		printf '%s\n' 'RPTADV_CONTAINER_DOCKER_SOCKET must be 0 or 1' >&2
		exit 2
		;;
esac
profile=${RPTADV_CONTAINER_PROFILE:-default}
case $profile in
	default) ;;
	constrained)
		if [ "$pass_docker_socket" != '0' ] || [ "$pull_image" != '1' ]; then
			printf '%s\n' 'constrained profile requires a fresh pull and no Docker socket' >&2
			exit 2
		fi
		;;
	*)
		printf '%s\n' 'RPTADV_CONTAINER_PROFILE must be default or constrained' >&2
		exit 2
		;;
esac
if [ "$profile" = constrained ]; then
	# Serialize constrained runs by this account across all project workspaces.
	lock_dir="$HOME/.cache/rpt-advanced"
	mkdir -p "$lock_dir"
	exec 9>"$lock_dir/constrained.lock"
	if ! flock -n 9; then
		printf '%s\n' 'another constrained quality run is active for this account' >&2
		exit 1
	fi
fi
cid_dir=$(mktemp -d "${TMPDIR:-/tmp}/rpt-advanced-container.XXXXXX")
cidfile="$cid_dir/container-id"

## @brief Remove only stopped test containers for this workspace.
cleanup_stale()
{
	stale=$(docker container ls --all --quiet --filter 'label=rpt_advanced.test=true' \
		--filter "label=$project_label" --filter "label=$scope_label" \
		--filter 'status=exited' --filter 'status=dead')
	[ -n "$stale" ] || return 0
	while IFS= read -r container; do
		[ -n "$container" ] || continue
		docker container rm "$container" >/dev/null 2>&1 || true
	done <<EOF
$stale
EOF
}

## @brief Remove only the container created by this invocation.
cleanup_current()
{
	if [ -s "$cidfile" ]; then
		container=$(cat "$cidfile")
		docker container rm --force "$container" >/dev/null 2>&1 || true
	fi
	rm -rf "$cid_dir"
}

trap cleanup_current EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
cleanup_stale

if [ "$pull_image" = '1' ]; then
	pull_output=$(docker image pull "$image" 2>&1)
	printf '%s\n' "$pull_output" >&2
	pulled_digest=$(printf '%s\n' "$pull_output" | sed -n 's/^Digest: //p' | tail -n 1)
	if [ -z "$pulled_digest" ]; then
		printf '%s\n' "could not determine the freshly pulled digest for $image" >&2
		exit 1
	fi
	run_image="$image@$pulled_digest"
	printf '%s\n' "Using $run_image" >&2
elif [ "$pull_image" = '0' ]; then
	image_id=$(docker image inspect --format '{{.Id}}' "$image")
	run_image=$image
	printf '%s\n' "Using existing local image $image ($image_id)" >&2
else
	printf '%s\n' 'RPTADV_CONTAINER_PULL must be 0 or 1' >&2
	exit 2
fi

# Worktree git metadata may live outside the bind mount; retain host-side source identity.
source_revision=$(git -C "$root" rev-parse HEAD 2>/dev/null || true)
source_tracked_dirty=$(git -C "$root" status --porcelain --untracked-files=no 2>/dev/null || true)
host_root=$root
docker_cidfile=$cidfile
case $(uname -s) in
	MINGW*|MSYS*)
		host_root=$(cd "$root" && pwd -W)
		docker_cidfile="$(cd "$cid_dir" && pwd -W)/container-id"
		export MSYS_NO_PATHCONV=1
		;;
esac

if [ "$profile" = constrained ]; then
	# Keep compilation and tests serial; cap the whole container independently.
	set -- --cpus 1 --memory 1536m --memory-swap 1536m --pids-limit 256 \
		--env CARGO_BUILD_JOBS=1 --env RUST_TEST_THREADS=1 --env OMP_NUM_THREADS=1 \
		--env OPENBLAS_NUM_THREADS=1 --env MAKEFLAGS=-j1 \
		--env MALLOC_MMAP_THRESHOLD_=131072 --env MALLOC_TRIM_THRESHOLD_=131072 \
		"$run_image" timeout --signal=TERM --kill-after=15s 20m "$@"
else
	set -- "$run_image" "$@"
fi
if [ "$pass_docker_socket" = '1' ]; then
	set -- --volume /var/run/docker.sock:/var/run/docker.sock "$@"
fi
docker run --rm --env "RPTADV_QUALITY_IMAGE=$run_image" \
	--env "RPTADV_SOURCE_REVISION=$source_revision" \
	--env "RPTADV_SOURCE_TRACKED_DIRTY=$source_tracked_dirty" --cidfile "$docker_cidfile" --name "$name" --label rpt_advanced.test=true \
	--label "$project_label" --label "$scope_label" \
	--volume "$host_root:/workspace" --workdir /workspace "$@"
