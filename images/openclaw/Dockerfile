FROM ghcr.io/openclaw/openclaw:2026.9.3
USER root
ADD --chmod=755 https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 /usr/local/bin/ttyd
COPY --chmod=755 start.sh /usr/local/bin/heimdall-start
COPY workspace /opt/heimdall/workspace
USER node
EXPOSE 7681
ENTRYPOINT ["tini", "-s", "--", "heimdall-start"]
