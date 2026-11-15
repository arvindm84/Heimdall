FROM python:3.11-slim
RUN pip install --no-cache-dir "mcp==1.*"
COPY server.py /app/server.py
EXPOSE 8080
CMD ["python", "/app/server.py"]
