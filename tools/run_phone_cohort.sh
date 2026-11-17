#!/bin/bash
# CI-only source qualification. Never install or publish the resulting libraries.
set -euo pipefail
# BEGIN Rust warning policy
# Encoded flags override RUSTFLAGS, including provider Makefile SONAME options.
# Reject even an empty encoded override rather than silently dropping flags.
if [[ ${CARGO_ENCODED_RUSTFLAGS+x} ]]; then
    echo "CARGO_ENCODED_RUSTFLAGS is unsupported; use RUSTFLAGS for this cohort" >&2
    exit 1
fi
export RUSTFLAGS="${RUSTFLAGS:+$RUSTFLAGS }-Dwarnings"
# END Rust warning policy
root=$(pwd)
sources="$root/sources"
out="$root/qualification-output"
runtime="$out/runtime"
arch=${EXPECTED_ARCH:?native architecture required}
test "$(dpkg --print-architecture)" = "$arch"
test -n "${QUALIFICATION_IMAGE:?resolved image required}"
test -f "${RPTADV_SOFIA_PREFIX:?private Sofia must be prepared}/include/sofia-sip-1.13/sofia-sip/su.h"
test ! -e "$runtime"
mkdir -p "$runtime" "$out/logs"
python3 tools/phone_cohort.py headers --output "$out/include"
export BINDGEN_EXTRA_CLANG_ARGS="${BINDGEN_EXTRA_CLANG_ARGS:+$BINDGEN_EXTRA_CLANG_ARGS }-I$out/include"
unset CARGO_TARGET_DIR CARGO_BUILD_TARGET
export CARGO_BUILD_JOBS=1 RUST_TEST_THREADS=1 CARGO_INCREMENTAL=0
export CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MAKEFLAGS=-j1
# Separate native dependencies by SONAME; do not overwrite installed packages.
for role in rnnoise radio adapter; do
    (cd "$sources/$role" && make -j1 all)
    cp -a "$sources/$role"/build/lib*.so* "$runtime/"
done
(cd "$sources/codec" && make -j1 external all)
cp -a "$sources/codec"/build/lib*.so* "$runtime/"
cp -a "$sources/codec"/build/backends/lib/lib*.so* "$runtime/"
export LIBRARY_PATH="$runtime:$RPTADV_SOFIA_PREFIX/lib"
export LD_LIBRARY_PATH="$LIBRARY_PATH"
export USBRADIOPLUS_AGC_PLUGIN_PATH="$runtime/usbradioplus_agc.so"
(
    cd "$sources/sdk"
    cargo rustc --locked -p usbradioplus_agc -- -C link-arg=-Wl,-soname,usbradioplus_agc.so
    cp target/debug/libusbradioplus_agc.so "$USBRADIOPLUS_AGC_PLUGIN_PATH"
    cargo rustc --locked -p usbradioplus-product -- -C link-arg=-Wl,-soname,libusbradioplus_product.so.1
    cp target/debug/libusbradioplus_product.so "$runtime/libusbradioplus_product.so.1"
    ln -s libusbradioplus_product.so.1 "$runtime/libusbradioplus_product.so"
)
export URP_PRODUCT_INCLUDE="$sources/sdk/rust/product/include"
export RPTADV_CODEC_INCLUDE="$sources/codec/include"
export RPT_ADVANCED_LIBDIR="$runtime"
export RPTADV_SIP_TEST_PROVIDER="$runtime/librptadv_sip_adapter.so.1"
(
    cd "$sources/controller"
    cargo build --locked --workspace --lib
    cp target/debug/librptadv_product.so "$runtime/librptadv_product.so.3"
    for adapter in asterisk control_asterisk control_standalone file speech resolver jitter gpiod hwmon sip; do
        cp "target/debug/librptadv_${adapter}_adapter.so" "$runtime/librptadv_${adapter}_adapter.so.1"
    done
)
python3 tools/phone_cohort.py receipt --manifest qualification/phone-downlink.json     --sources "$sources" --runtime "$runtime" --arch "$arch"     --image "$QUALIFICATION_IMAGE" --output "$out/before.json"
(
    cd "$sources/controller"
    cargo test --locked -p rptadv-product --lib downlink_ -- --test-threads=1 --nocapture
) 2>&1 | tee "$out/logs/downlink.log"
python3 tools/phone_cohort.py tests --log "$out/logs/downlink.log" --expected 5
(
    cd "$sources/controller"
    cargo test --locked -p rpt-advanced-standalone --lib real_product_sip_call_ -- --test-threads=1 --nocapture
) 2>&1 | tee "$out/logs/native-sip.log"
python3 tools/phone_cohort.py tests --log "$out/logs/native-sip.log" --expected 2
python3 tools/phone_cohort.py receipt --manifest qualification/phone-downlink.json     --sources "$sources" --runtime "$runtime" --arch "$arch"     --image "$QUALIFICATION_IMAGE" --output "$out/after.json"
cmp "$out/before.json" "$out/after.json"
echo "Scoped native phone cohort passed; NOT a full quality gate or hardware test."
