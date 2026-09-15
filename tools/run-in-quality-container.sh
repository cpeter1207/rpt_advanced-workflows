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

host_root=$root
docker_cidfile=$cidfile
case $(uname -s) in
	MINGW*|MSYS*)
		host_root=$(cd "$root" && pwd -W)
		docker_cidfile="$(cd "$cid_dir" && pwd -W)/container-id"
		export MSYS_NO_PATHCONV=1
		;;
esac

docker run --rm --cidfile "$docker_cidfile" --name "$name" --label rpt_advanced.test=true \
	--label "$project_label" --label "$scope_label" \
	--volume "$host_root:/workspace" --workdir /workspace "$run_image" "$@"
