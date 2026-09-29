import json
import ipaddress
import os
import secrets
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

if getattr(sys, "frozen", False):
    _CONFIG_PATH = os.path.join(os.path.dirname(sys.executable), "network_config.json")
else:
    _CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "network_config.json")

def load_config():
    with open(_CONFIG_PATH, "r") as f:
        return json.load(f)


def discover_admin_ip(timeout=3.0):
    nonce = secrets.token_hex(8)
    request = f"COMPHUB_DISCOVER|ADMIN|{nonce}".encode("ascii")
    interface_networks = []
    broadcast_targets = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as discovery_socket:
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        destinations = set()
        if sys.platform == "win32":
            command = (
                "Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred "
                "| Select-Object IPAddress,PrefixLength,InterfaceAlias | ConvertTo-Json -Compress"
            )
            try:
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                interfaces = json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else []
                if isinstance(interfaces, dict):
                    interfaces = [interfaces]
                for interface in interfaces:
                    address = interface.get("IPAddress", "")
                    prefix = interface.get("PrefixLength")
                    try:
                        ip_interface = ipaddress.IPv4Interface(f"{address}/{int(prefix)}")
                    except (ValueError, TypeError):
                        continue
                    if not ip_interface.ip.is_loopback and not ip_interface.ip.is_link_local:
                        alias = str(interface.get("InterfaceAlias", "")).lower()
                        priority = 0 if any(tag in alias for tag in ("wi-fi", "wifi", "wlan", "wireless")) else 1
                        interface_networks.append((priority, ip_interface.network))
                        broadcast = str(ip_interface.network.broadcast_address)
                        if broadcast not in destinations:
                            destinations.add(broadcast)
                            broadcast_targets.append((priority, broadcast))
            except (OSError, subprocess.SubprocessError, ValueError, TypeError) as error:
                print(f"[LAN discovery] Could not enumerate interface broadcasts: {error}")

        broadcast_targets.sort(key=lambda item: item[0])
        broadcast_targets.append((2, "255.255.255.255"))
        for _priority, destination in broadcast_targets:
            try:
                discovery_socket.sendto(request, (destination, 37020))
            except OSError as error:
                print(f"[LAN discovery] Broadcast to {destination} failed: {error}")

        deadline = time.monotonic() + min(1.0, timeout)
        fallback_ip = None
        fallback_deadline = None
        try:
            while True:
                remaining = deadline - time.monotonic()
                if fallback_deadline is not None:
                    remaining = min(remaining, fallback_deadline - time.monotonic())
                if remaining <= 0:
                    return fallback_ip
                discovery_socket.settimeout(remaining)
                response, address = discovery_socket.recvfrom(256)
                if response.decode("ascii", errors="ignore") == f"COMPHUB_SERVICE|ADMIN|{nonce}":
                    response_ip = ipaddress.IPv4Address(address[0])
                    matching_priorities = [
                        priority for priority, network in interface_networks
                        if response_ip in network
                    ]
                    response_priority = min(matching_priorities, default=2)
                    if response_priority == 0:
                        return address[0]
                    if fallback_ip is None or response_priority < fallback_priority:
                        fallback_ip = address[0]
                        fallback_priority = response_priority
                        fallback_deadline = time.monotonic() + min(0.4, timeout)
        except socket.timeout:
            if fallback_ip:
                return fallback_ip

    return _discover_admin_over_tcp(interface_networks, timeout)


def _discover_admin_over_tcp(interface_networks, timeout):
    networks = sorted(interface_networks, key=lambda item: item[0])
    candidates = []
    seen = set()
    for _priority, network in networks:
        if not network.is_private or network.prefixlen < 22:
            continue
        for host in network.hosts():
            address = str(host)
            if address not in seen:
                seen.add(address)
                candidates.append(address)
                if len(candidates) >= 1024:
                    break
        if len(candidates) >= 1024:
            break

    def probe(address):
        try:
            with socket.create_connection((address, LOG_PORT), timeout=0.25) as client:
                client.settimeout(0.25)
                client.sendall(b"ACTION: DISCOVER_ADMIN")
                if client.recv(64).decode("ascii", errors="ignore").strip() == "COMPHUB_ADMIN":
                    return address
        except OSError:
            return None
        return None

    deadline = time.monotonic() + min(timeout, 2.5)
    with ThreadPoolExecutor(max_workers=64) as executor:
        futures = {executor.submit(probe, address) for address in candidates}
        try:
            for future in as_completed(futures, timeout=max(0.1, deadline - time.monotonic())):
                address = future.result()
                if address:
                    return address
        except TimeoutError:
            pass
    return None


_cached_admin_ip = None
_cached_admin_ip_at = 0.0


def get_admin_ip(timeout=3.0):
    global _cached_admin_ip, _cached_admin_ip_at
    if time.monotonic() - _cached_admin_ip_at >= 5.0:
        _cached_admin_ip = discover_admin_ip(timeout)
        _cached_admin_ip_at = time.monotonic()
    return _cached_admin_ip


CONFIG = load_config()
TEACHER_IP = CONFIG.get("teacher_ip", "")
LOG_PORT = CONFIG["log_port"]
COMMAND_PORT = CONFIG["command_port"]
BROADCAST_PORT = CONFIG["broadcast_port"]
STREAM_PORT = CONFIG["stream_port"]
REMOTE_VIEW_PORT = CONFIG["remote_view_port"]
STUDENT_PC_IP = []
CONTROL_PORT = CONFIG["control_port"]
ADMIN_IP = CONFIG.get("admin_ip", "")