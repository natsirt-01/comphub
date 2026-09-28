import mss
import cv2
import socket
import numpy as np
import time
import pyautogui
import os
import json

from network_config import ADMIN_IP

pyautogui.FAILSAFE = False

def get_current_username():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        session_file = os.path.join(base_dir, "active_session.json")
        if os.path.exists(session_file):
            with open(session_file, "r") as f:
                data = json.load(f)
                return data.get("username", "Student")
    except:
        pass
    return None

def start_control_listener():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", 9999))
    server.listen(5)
    
    control_active = False 
    while True:
        try:
            conn, addr = server.accept()
            while True:
                data = conn.recv(1024).decode()
                if not data: break
                
                commands = data.split("\n")
                for line in commands:
                    line = line.strip()
                    if not line: continue
                    
                    if line == "START_CONTROL":
                        control_active = True
                        if on_pov_start:
                            on_pov_start()
                    elif line == "STOP_CONTROL":
                        control_active = False
                        if on_pov_stop:
                            on_pov_stop()
                    elif control_active:
                        if line.startswith("MOVE"):
                            parts = line.split(":")
                            if len(parts) == 3:
                                pyautogui.moveTo(int(parts[1]), int(parts[2]), duration=0.0)
                        elif line == "CLICK":
                            pyautogui.click()
            conn.close()
        except Exception:
            pass

def start_live_monitoring(admin_ip):
    """Port 9997 para sa Remote View / Remote Control (Naka-optimize sa 15 FPS)"""
    while True:
        username = get_current_username()
        if not username:
            time.sleep(2)
            continue
            
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client.connect((admin_ip, 9997))
            
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                while True:
                    if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_session.json")):
                        client.close()
                        break
                        
                    img = np.array(sct.grab(monitor))
                    
                    cur_x, cur_y = pyautogui.position()
                    cv2.circle(img, (cur_x, cur_y), 10, (0, 0, 255), -1)
                    
                    img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    
                    # Bawasan ang resolution at kalidad para hindi bumagal ang network
                    img_bgr = cv2.resize(img_bgr, (960, 540), interpolation=cv2.INTER_AREA)
                    _, encoded = cv2.imencode('.jpg', img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    data = encoded.tobytes()
                    
                    client.sendall(len(data).to_bytes(4, byteorder='big') + data)
                    time.sleep(0.06) # ~15 FPS limit para sa monitoring
        except Exception:
            time.sleep(2)

def stream_to_target(target_ip, target_port):
    """Optimized stream para sa guro (Binabaan ang quality at nilagyan ng FPS limit)"""
    while True:
        username = get_current_username()
        if not username:
            time.sleep(2)
            continue
            
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client.connect((target_ip, target_port))
            
            name_msg = f"NAME: {username}\n"
            client.sendall(name_msg.encode('utf-8'))
            
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                while True:
                    if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_session.json")):
                        client.close()
                        break
                    
                    img = np.array(sct.grab(monitor))
                    img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    
                    # I-resize sa 720p at 75% quality para hindi mag-lag o mag-freeze ang buong app
                    img_bgr = cv2.resize(img_bgr, (1280, 720), interpolation=cv2.INTER_AREA)
                    _, encoded = cv2.imencode('.jpg', img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    data = encoded.tobytes()
                    
                    client.sendall(len(data).to_bytes(4, byteorder='big') + data)
                    time.sleep(0.04) # ~25 FPS limit
        except Exception as e:
            time.sleep(2)

def start_stream(teacher_ip):
    stream_to_target(teacher_ip, 9998)

def start_admin_stream():
    stream_to_target(ADMIN_IP, 9998)