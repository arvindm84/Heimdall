FROM nousresearch/hermes-agent:v0.23.1
ADD --chmod=755 https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 /usr/local/bin/ttyd
COPY --chmod=755 start.sh /usr/local/bin/heimdall-start
COPY SOUL.md /opt/heimdall/SOUL.md
RUN grep -q 'print(f"⚠ {problem}", file=sys.stderr)' /opt/hermes/hermes_cli/main.py \
 && sed -i 's/print(f"⚠ {problem}", file=sys.stderr)/pass/' /opt/hermes/hermes_cli/main.py
USER hermes
WORKDIR /opt/data
EXPOSE 7681
ENTRYPOINT ["heimdall-start"]
