# syntax=docker/dockerfile:1.7
ARG DEBIAN_VERSION=13
FROM debian:${DEBIAN_VERSION} AS clean
ARG DEBIAN_VERSION
# Associate published images with the production repository so its workflow
# token owns the corresponding GHCR packages.
LABEL org.opencontainers.image.source="https://github.com/cpeter1207/rpt_advanced"
COPY --from=dependencies . /tmp/dependencies/
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates wget && \
    wget -qO /tmp/asl-repo.deb \
      "https://repo.allstarlink.org/public/asl-apt-repos.deb${DEBIAN_VERSION}_all.deb" && \
    dpkg -i /tmp/asl-repo.deb && apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      asl3-asterisk /tmp/dependencies/*.deb && \
    rm -rf /var/lib/apt/lists/* /tmp/asl-repo.deb /tmp/dependencies

FROM ghcr.io/cpeter1207/rpt-advanced-quality-debian${DEBIAN_VERSION}:latest AS build
WORKDIR /source
# The caller binds this named context to the exact tested production revision.
COPY --from=production . ./
RUN DEB_BUILD_OPTIONS=nocheck dpkg-buildpackage -us -uc -b && make build/chan_rpt_fixture.so

FROM clean AS installed
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ffmpeg python3 && rm -rf /var/lib/apt/lists/*
COPY --from=build /rpt-advanced_*.deb /librptadv-product1_*.deb \
  /librptadv-file-adapter1_*.deb /librptadv-speech-adapter1_*.deb \
  /librptadv-control-asterisk-adapter1_*.deb /tmp/packages/
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends /tmp/packages/*.deb && \
    rm -rf /var/lib/apt/lists/* /tmp/packages
RUN ldconfig
WORKDIR /opt/rpt-testing
# Test fixtures remain separate from the installed module and its configuration.
COPY --from=build /source/build/chan_rpt_fixture.so ./build/
COPY --from=build /source/tests/test_rust_asterisk_lifecycle.py /source/tests/test_asterisk_integration.py /source/tests/test_link_integration.py ./tests/
RUN mkdir -p lib/asterisk/modules lib/rpt_advanced \
      build/stage/usr/share/doc/rpt-advanced/examples && \
    cp /usr/lib/*/asterisk/modules/app_rpt_advanced.so lib/asterisk/modules/ && \
    cp /usr/lib/*/rpt_advanced/librptadv_*.so.1* lib/rpt_advanced/ && \
    cp build/chan_rpt_fixture.so lib/asterisk/modules/ && \
    cp /usr/share/doc/rpt-advanced/examples/rpt_advanced.conf \
      build/stage/usr/share/doc/rpt-advanced/examples/ && \
    ldd lib/asterisk/modules/app_rpt_advanced.so
ENV RPT_TEST_MODULE_DIR=/opt/rpt-testing/lib/asterisk/modules
CMD ["sh", "-ec", "python3 tests/test_rust_asterisk_lifecycle.py && python3 tests/test_asterisk_integration.py && python3 tests/test_link_integration.py"]
