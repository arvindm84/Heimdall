"""Runs the tool server and the model proxy. If either stops, the container stops."""

import subprocess
import sys
import time

processes = [
    subprocess.Popen([sys.executable, "/app/server.py"]),
    subprocess.Popen(["mitmdump", "-q", "-s", "/app/addon.py", "-p", "8080", "--set", "confdir=/ca"]),
]
while all(process.poll() is None for process in processes):
    time.sleep(1)
for process in processes:
    process.terminate()
sys.exit(1)
