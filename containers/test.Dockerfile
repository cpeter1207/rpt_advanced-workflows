# syntax=docker/dockerfile:1.7
ARG DEBIAN_VERSION=13
FROM debian:${DEBIAN_VERSION} AS clean
ARG DEBIAN_VERSION
LABEL org.opencontainers.image.source="https://github.com/cpeter1207/rpt_advanced-workflows"
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates wget && \
    wget -qO /tmp/asl-repo.deb \
      "https://repo.allstarlink.org/public/asl-apt-repos.deb${DEBIAN_VERSION}_all.deb" && \
    dpkg -i /tmp/asl-repo.deb && apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends asl3-asterisk && \
    rm -rf /var/lib/apt/lists/* /tmp/asl-repo.deb

FROM ghcr.io/cpeter1207/rpt-advanced-quality-debian${DEBIAN_VERSION}:latest AS build
WORKDIR /source
# The caller binds this named context to the exact tested production revision.
COPY --from=production Makefile COPYING ./
COPY --from=production src ./src
COPY --from=production module ./module
COPY --from=production tests ./tests
COPY --from=production examples ./examples
# Build the released shared playout-ring implementation in the same image as
# the module so the installed test artifact has its required runtime library.
COPY --from=rpcr . /rpcr
RUN make -j4 RPCR_SOURCE=/rpcr all build/chan_rpt_fixture.so && \
    make RPCR_SOURCE=/rpcr DESTDIR=/stage prefix=/usr install

FROM clean AS installed
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ffmpeg python3 && rm -rf /var/lib/apt/lists/*
COPY --from=build /stage/ /
RUN ldconfig
WORKDIR /opt/rpt-testing
# Test fixtures remain separate from the installed module and its configuration.
COPY --from=build /source/build/chan_rpt_fixture.so ./build/
COPY --from=build /source/tests/test_asterisk_integration.py ./tests/
RUN mkdir -p build/stage/usr/lib/asterisk/modules \
      build/stage/usr/share/doc/rpt_advanced/examples && \
    cp /usr/lib/*/asterisk/modules/app_rpt_advanced.so build/stage/usr/lib/asterisk/modules/ && \
    cp /usr/share/doc/rpt_advanced/examples/rpt_advanced.conf \
      build/stage/usr/share/doc/rpt_advanced/examples/ && \
    ldd /usr/lib/*/asterisk/modules/app_rpt_advanced.so
ENV RPT_TEST_MODULE_DIR=/opt/rpt-testing/build/stage/usr/lib/asterisk/modules
CMD ["python3", "tests/test_asterisk_integration.py"]
