#!/bin/bash
set -euo pipefail
architecture=$(dpkg --print-architecture)
[[ "$architecture" == "$EXPECTED_ARCH" ]]
diff -u "$RUNNER_TEMP/caller-before" <(rustc -vV; cargo -V)
rustc -vV
cargo -V
packages=dependencies/packages
check_pair() {
  local version=$1
  shift
  local package
  for package; do
    local archive="$packages/${package}_${version}_${architecture}.deb"
    [[ $(dpkg-deb -f "$archive" Package) == "$package" ]]
    [[ $(dpkg-deb -f "$archive" Version) == "$version" ]]
    [[ $(dpkg-deb -f "$archive" Architecture) == "$architecture" ]]
    [[ $(dpkg-query -W -f='${Status} ${Version} ${Architecture}' "$package") == "install ok installed $version $architecture" ]]
    sha256sum "$archive"
  done
}
check_pair '0.2.0~alpha3-1' librptadv-samplerate-adapter2 librptadv-samplerate-adapter-dev
check_pair '3.0.0~alpha6-1' librate-adjusting-pcm-ring3 librate-adjusting-pcm-ring3-dev
check_pair '0.1.0~alpha3-1' librptadvschedule1 librptadvschedule-dev
check_pair '0.1.0~alpha36-1' libusbradioplus-product1 libusbradioplus-product-dev
[[ $(pkg-config --variable=recurrence_abi_version rptadvschedule) == 1 ]]
# The project .pc files supply compiler/linker arguments.
# shellcheck disable=SC2046
cc -std=c11 -Wall -Wextra -Werror tools/task-37/sdk-proof.c -o "$RUNNER_TEMP/sdk-proof" \
  $(pkg-config --cflags --libs rptadvschedule usbradioplus_product)
"$RUNNER_TEMP/sdk-proof"
