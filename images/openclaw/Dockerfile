FROM ghcr.io/openclaw/openclaw:2026.9.3
USER root
# Docker sets TARGETARCH to amd64 or arm64; ttyd names its builds x86_64 / aarch64.
ARG TARGETARCH
RUN case "$TARGETARCH" in \
      amd64) arch=x86_64 ;; \
      arm64) arch=aarch64 ;; \
      *) echo "no ttyd build for $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl -fsSL -o /usr/local/bin/ttyd \
      "https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.$arch" \
 && chmod 755 /usr/local/bin/ttyd
COPY --chmod=755 start.sh /usr/local/bin/heimdall-start
COPY workspace /opt/heimdall/workspace
USER node
EXPOSE 7681
ENTRYPOINT ["tini", "-s", "--", "heimdall-start"]
