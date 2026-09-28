import threading
import time
import socket
import numpy as np
import cv2
import mss
import pyautogui

from network_config import ADMIN_IP, STREAM_PORT, REMOTE_VIEW_PORT

pyautogui.FAILSAFE = False

_stop_flag = {"stop": False}


def _stream_loop(target_port, teacher_name, fps_delay, resize_dim, quality, include_cursor, send_handshake):
    print(f"[DEBUG teacher_stream] Starting stream loop -> {ADMIN_IP}:{target_port}")
    while not _stop_flag["stop"]:
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client.connect((ADMIN_IP, target_port))
            print(f"[DEBUG teacher_stream] Connected successfully to {ADMIN_IP}:{target_port}")
            if send_handshake:
                client.sendall(f"NAME: {teacher_name}|ROLE:teacher\n".encode('utf-8'))

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                while not _stop_flag["stop"]:
                    img = np.array(sct.grab(monitor))
                    img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

                    if include_cursor:
                        cur_x, cur_y = pyautogui.position()
                        cv2.circle(img_bgr, (cur_x, cur_y), 10, (0, 0, 255), -1)

                    img_bgr = cv2.resize(img_bgr, resize_dim, interpolation=cv2.INTER_AREA)
                    _, encoded = cv2.imencode('.jpg', img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
                    data = encoded.tobytes()
                    client.sendall(len(data).to_bytes(4, byteorder='big') + data)
                    time.sleep(fps_delay)
        except Exception as e:
            print(f"[DEBUG teacher_stream] FAILED to connect to {ADMIN_IP}:{target_port} -> {e}")
            time.sleep(2)
        if _stop_flag["stop"]:
            break


def start_teacher_streaming(teacher_name):
    """Call once when TeacherDashboard opens. Streams the teacher's own screen
    to Admin: a thumbnail feed (STREAM_PORT, needs the NAME/ROLE handshake so
    handle_client can identify it) and a remote-view feed (REMOTE_VIEW_PORT,
    NO handshake — handle_remote_client reads raw length-prefixed frames only,
    exactly like students' start_live_monitoring does)."""
    _stop_flag["stop"] = False
    threading.Thread(
        target=_stream_loop,
        args=(STREAM_PORT, teacher_name, 0.04, (1280, 720), 75, False, True),
        daemon=True,
    ).start()
    threading.Thread(
        target=_stream_loop,
        args=(REMOTE_VIEW_PORT, teacher_name, 0.06, (960, 540), 70, True, False),
        daemon=True,
    ).start()


def stop_teacher_streaming():
    """Call when TeacherDashboard closes."""
    _stop_flag["stop"] = True