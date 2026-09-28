import json
import os
import secrets
import socket
import sys
import time

if getattr(sys, "frozen", False):
    _CONFIG_PATH = os.path.join(os.path.dirname(sys.executable), "network_config.json")
else:
    _CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "network_config.json")

def load_config():
    with open(_CONFIG_PATH, "r") as f:
        return json.load(f)

CONFIG = load_config()


def discover_admin_ip(timeout=4.0):
    nonce = secrets.token_hex(8)
    request = f"COMPHUB_DISCOVER|ADMIN|{nonce}".encode("ascii")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as discovery_socket:
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        discovery_socket.settimeout(timeout)
        discovery_socket.sendto(request, ("255.255.255.255", 37020))
        try:
            while True:
                response, address = discovery_socket.recvfrom(256)
                if response.decode("ascii", errors="ignore") == f"COMPHUB_SERVICE|ADMIN|{nonce}":
                    return address[0]
        except socket.timeout:
            return None


_cached_admin_ip = None
_cached_admin_ip_at = 0.0


def get_admin_ip(timeout=4.0):
    global _cached_admin_ip, _cached_admin_ip_at
    if time.monotonic() - _cached_admin_ip_at >= 5.0:
        _cached_admin_ip = discover_admin_ip(timeout)
        _cached_admin_ip_at = time.monotonic()
    return _cached_admin_ip


TEACHER_IP = ""
LOG_PORT = CONFIG["log_port"]
LISTENER_PORT = CONFIG["listener_port"]
BROADCAST_PORT = CONFIG["broadcast_port"]
STREAM_PORT = CONFIG["stream_port"]
REMOTE_VIEW_PORT = CONFIG["remote_view_port"]
CONTROL_PORT = CONFIG["control_port"]
ADMIN_IP = ""