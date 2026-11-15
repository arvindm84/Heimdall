FROM python:3.11-slim
RUN pip install --no-cache-dir "mcp==1.*" mitmproxy
COPY server.py addon.py run.py /app/
EXPOSE 8000 8080
CMD ["python", "/app/run.py"]
