"""Run one Python script with an audit hook that writes every network event to a log.

    python3 -I audit_run.py LOG SCRIPT [ARGS ...]

Events logged: socket.connect, socket.bind, socket.getaddrinfo, socket.gethostbyname,
socket.sendto, urllib.Request, http.client.connect (Python audit events,
https://docs.python.org/3/library/audit_events.html). The hook logs and does not block:
the network namespace (unshare -rn) blocks, and the log shows any attempt that the script
then caught.
"""
import os
import runpy
import sys

NETWORK_EVENTS = {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.gethostbyname", "socket.sendto",
                  "urllib.Request", "http.client.connect"}
log_path, script, *args = sys.argv[1:]


def hook(event, details):
    if event in NETWORK_EVENTS:
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(f"{os.getpid()} {event} {details!r}\n")


sys.addaudithook(hook)
sys.argv = [script, *args]
sys.path.insert(0, os.path.dirname(os.path.abspath(script)))
runpy.run_path(script, run_name="__main__")
