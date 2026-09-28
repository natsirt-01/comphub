import socket
import threading
import time
import struct
import mss
import numpy as np
import cv2
import pyautogui
from .network_utils import send_command
from network_config import BROADCAST_PORT

def toggle_teacher_broadcast(self):
    """Veyon-Style Realtime Broadcast Server (Optimized & Non-Blocking)"""
    def broadcast_server_loop():
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        try:
            server_sock.bind(('0.0.0.0', BROADCAST_PORT))
            server_sock.listen(15)
            server_sock.settimeout(0.5)
        except Exception as e:
            print(f"Broadcast bind error: {e}")
            return

        clients = []

        def accept_clients():
            while self.is_broadcasting_demo:
                try:
                    conn, addr = server_sock.accept()
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    conn.setblocking(False)
                    clients.append(conn)
                except socket.timeout:
                    continue
                except:
                    break

        accept_thread = threading.Thread(target=accept_clients, daemon=True)
        accept_thread.start()

        with mss.mss() as sct:
            monitor = sct.monitors[1]

            while self.is_broadcasting_demo:
                loop_start = time.time()
                try:
                    img = sct.grab(monitor)
                    frame = np.array(img)
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                    try:
                        mouse_x, mouse_y = pyautogui.position()
                        cv2.circle(frame_bgr, (mouse_x, mouse_y), 14, (0, 0, 255), -1)
                        cv2.circle(frame_bgr, (mouse_x, mouse_y), 16, (255, 255, 255), 2)
                    except:
                        pass

                    frame_resized = cv2.resize(frame_bgr, (1280, 720), interpolation=cv2.INTER_AREA)
                    _, img_encoded = cv2.imencode('.jpg', frame_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                    img_data = img_encoded.tobytes()
                    header = struct.pack("!I", len(img_data))
                    payload = header + img_data

                    dead_clients = []
                    for client in clients:
                        try:
                            client.sendall(payload)
                        except:
                            dead_clients.append(client)

                    for dead in dead_clients:
                        if dead in clients:
                            clients.remove(dead)
                        try:
                            dead.close()
                        except:
                            pass

                except Exception as e:
                    print(f"Broadcast loop error: {e}")

                elapsed = time.time() - loop_start
                if elapsed < 0.03:
                    time.sleep(0.03 - elapsed)

        try:
            server_sock.close()
        except:
            pass

        for client in clients:
            try:
                client.close()
            except:
                pass

    if not self.is_broadcasting_demo:
        self.is_broadcasting_demo = True
        if self.btn_fullscreen_demo:
            self.btn_fullscreen_demo.configure(text="STOP", fg_color="#a83232", hover_color="#c94444")

        for ip in self.student_cards.keys():
            send_command(ip, "START_DEMO")

        time.sleep(0.2)
        threading.Thread(target=broadcast_server_loop, daemon=True).start()
        print("[DEBUG] Nagsimula na ang na-optimize na Broadcast Server.")
    else:
        self.is_broadcasting_demo = False
        if self.btn_fullscreen_demo:
            self.btn_fullscreen_demo.configure(text="Fullscreen demo", fg_color="#383838", hover_color="#505050")

        for ip in self.student_cards.keys():
            send_command(ip, "STOP_DEMO")