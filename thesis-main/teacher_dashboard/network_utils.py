# network_utils.py
import socket
from network_config import COMMAND_PORT, CONTROL_PORT

def send_command(target_student_ip, command):
    """Para sa LOCK/UNLOCK/SLEEP/REBOOT/SHUTDOWN (Port from network_config)"""
    print(f"[DEBUG send_command] Attempting to send '{command}' to {target_student_ip}:{COMMAND_PORT}")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2) 
            s.connect((target_student_ip, COMMAND_PORT))
            s.sendall(command.encode())
            print(f"[DEBUG send_command] SUCCESS: '{command}' sent to {target_student_ip}")
            return True
    except Exception as e:
        print(f"[DEBUG send_command] FAILED to connect to {target_student_ip}:{COMMAND_PORT} -> {e}")
        return False

def send_control_command(target_ip, command):
    """Para sa Control Commands (Port 9999)[cite: 5]"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect((target_ip, CONTROL_PORT))
            s.sendall(f"{command}\n".encode())
            print(f"Control command '{command}' sent to {target_ip}")
    except Exception as e:
        print(f"Control command error: {e}")