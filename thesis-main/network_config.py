import json
import os
import sys

if getattr(sys, "frozen", False):
    _CONFIG_PATH = os.path.join(os.path.dirname(sys.executable), "network_config.json")
else:
    _CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "network_config.json")

def load_config():
    with open(_CONFIG_PATH, "r") as f:
        return json.load(f)

CONFIG = load_config()
TEACHER_IP = CONFIG["teacher_ip"]
LOG_PORT = CONFIG["log_port"]
COMMAND_PORT = CONFIG["command_port"]
BROADCAST_PORT = CONFIG["broadcast_port"]
STREAM_PORT = CONFIG["stream_port"]
REMOTE_VIEW_PORT = CONFIG["remote_view_port"]
STUDENT_PC_IP = CONFIG["student_pc_ip"]
CONTROL_PORT = CONFIG["control_port"]
ADMIN_IP = CONFIG["admin_ip"]