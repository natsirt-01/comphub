import json
import ipaddress
import os
import sys

if getattr(sys, "frozen", False):
    _CONFIG_PATH = os.path.join(os.path.dirname(sys.executable), "network_config.json")
    _REGISTRY_PATH = os.path.join(os.environ.get("PROGRAMDATA", os.path.expanduser("~")), "CompHub", "network_registry.json")
else:
    _CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "network_config.json")
    _REGISTRY_PATH = os.path.join(os.path.dirname(_CONFIG_PATH), "ip_registry.json")

def load_config():
    with open(_CONFIG_PATH, "r") as f:
        config = json.load(f)
    if os.path.exists(_REGISTRY_PATH):
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as registry_file:
            registry = json.load(registry_file)
        for role in ("student", "teacher"):
            key = f"{role}_pc_ip"
            if key in registry:
                config[key] = registry[key]
    return config


def save_ip_registry(role, address, remove=False):
    if role not in ("student", "teacher"):
        raise ValueError("IP role must be student or teacher.")
    address = str(ipaddress.IPv4Address(address.strip()))
    config = load_config()
    key = f"{role}_pc_ip"
    addresses = list(dict.fromkeys(config.get(key, [])))
    if remove:
        addresses = [item for item in addresses if item != address]
    elif address not in addresses:
        addresses.append(address)
    config[key] = addresses
    if not remove:
        other_key = "teacher_pc_ip" if role == "student" else "student_pc_ip"
        config[other_key] = [item for item in config.get(other_key, []) if item != address]
    os.makedirs(os.path.dirname(_REGISTRY_PATH), exist_ok=True)
    with open(_REGISTRY_PATH, "w", encoding="utf-8") as config_file:
        json.dump({
            "student_pc_ip": config.get("student_pc_ip", []),
            "teacher_pc_ip": config.get("teacher_pc_ip", []),
        }, config_file, indent=4)
    CONFIG.update(config)
    return address


def get_registered_ip_role(address):
    for role in ("teacher", "student"):
        if address in CONFIG.get(f"{role}_pc_ip", []):
            return role
    return None


CONFIG = load_config()
TEACHER_IP = CONFIG["teacher_ip"]
LOG_PORT = CONFIG["log_port"]
COMMAND_PORT = CONFIG["command_port"]
BROADCAST_PORT = CONFIG["broadcast_port"]
STREAM_PORT = CONFIG["stream_port"]
REMOTE_VIEW_PORT = CONFIG["remote_view_port"]
STUDENT_PC_IP = CONFIG.get("student_pc_ip", [])
CONTROL_PORT = CONFIG["control_port"]
ADMIN_IP = CONFIG["admin_ip"]