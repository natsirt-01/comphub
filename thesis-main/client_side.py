import socket
import threading
import customtkinter as ctk
import datetime
import time
import cv2
import mss
import numpy as np
import ctypes
import json

from network_config import ADMIN_IP, LOG_PORT, TEACHER_IP, STREAM_PORT, REMOTE_VIEW_PORT


_stream_stop = threading.Event()


STREAM_DESTINATIONS = tuple(dict.fromkeys((TEACHER_IP, ADMIN_IP)))


def _stream_loop(target_host, target_port, username, send_handshake, resize_dim, quality, fps_delay):
    while not _stream_stop.is_set():
        client = None
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(5)
            client.connect((target_host, target_port))
            client.settimeout(None)
            if send_handshake:
                client.sendall(f"NAME: {username}|ROLE:student\n".encode("utf-8"))

            with mss.mss() as capture:
                monitor = capture.monitors[1]
                while not _stream_stop.is_set():
                    frame = np.array(capture.grab(monitor))
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    frame = cv2.resize(frame, resize_dim, interpolation=cv2.INTER_AREA)
                    encoded_ok, encoded = cv2.imencode(
                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality]
                    )
                    if not encoded_ok:
                        continue
                    data = encoded.tobytes()
                    client.sendall(len(data).to_bytes(4, byteorder="big") + data)
                    time.sleep(fps_delay)
        except Exception as error:
            if not _stream_stop.is_set():
                print(f"[DEBUG student_stream] {target_host}:{target_port} -> {error}")
                time.sleep(2)
        finally:
            if client is not None:
                try:
                    client.close()
                except OSError:
                    pass


def start_student_streaming(username):
    _stream_stop.clear()
    for target_host in STREAM_DESTINATIONS:
        threading.Thread(
            target=_stream_loop,
            args=(target_host, STREAM_PORT, username, True, (640, 400), 65, 0.08),
            daemon=True,
        ).start()
        threading.Thread(
            target=_stream_loop,
            args=(target_host, REMOTE_VIEW_PORT, username, False, (960, 540), 70, 0.06),
            daemon=True,
        ).start()


def stop_student_streaming():
    _stream_stop.set()


def send_student_logout(username):
    try:
        with socket.create_connection((ADMIN_IP, LOG_PORT), timeout=3) as client:
            client.sendall(f"ACTION: LOGOUT | USER: {username}".encode("utf-8"))
    except OSError as error:
        print(f"[DEBUG student logout] Cannot notify Admin: {error}")


def _visible_window_titles(excluded_hwnd=None):
    if not hasattr(ctypes, "windll"):
        return []
    user32 = ctypes.windll.user32
    titles = []
    enum_windows = user32.EnumWindows
    enum_windows.argtypes = [ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p), ctypes.c_void_p]
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def collect(hwnd, _lparam):
        if hwnd == excluded_hwnd or not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if title.value.strip():
            titles.append(title.value.strip())
        return True

    enum_windows(callback_type(collect), 0)
    return titles


def _foreground_window_title():
    """Return only the title of the currently active window/tab."""
    if not hasattr(ctypes, "windll"):
        return ""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title, length + 1)
    return title.value.strip()


def _fetch_blocklist():
    try:
        with socket.create_connection((ADMIN_IP, LOG_PORT), timeout=5) as client:
            client.sendall(b"ACTION: GET_BLOCKLIST")
            response = client.recv(65536).decode("utf-8")
        return json.loads(response) if response else []
    except (OSError, ValueError) as error:
        print(f"[DEBUG detection] Cannot fetch blocklist: {error}")
        return []


def _send_site_alert(username, matched_text, category, status):
    try:
        with socket.create_connection((ADMIN_IP, LOG_PORT), timeout=5) as client:
            payload = (
                f"ACTION: SITE_ALERT | USER: {username} | TEXT: {matched_text} | "
                f"CATEGORY: {category} | STATUS: {status}"
            )
            client.sendall(payload.encode("utf-8"))
    except OSError as error:
        print(f"[DEBUG detection] Cannot send site alert: {error}")


class RestrictedSiteWarning(ctk.CTkToplevel):
    def __init__(self, master, site_text, category, is_site_open):
        super().__init__(master)
        self.site_text = site_text
        self.is_site_open = is_site_open
        self.title("Restricted Site Detected")
        self.geometry("520x240")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.bind("<Escape>", lambda event: "break")
        ctk.CTkLabel(self, text="RESTRICTED SITE DETECTED", text_color="#ff3333",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(28, 12))
        ctk.CTkLabel(self, text=f"Category: {category}\n{site_text}", wraplength=460,
                     justify="center").pack(pady=8)
        ctk.CTkLabel(self, text="Close the restricted site to remove this warning.",
                     text_color="#ffcc00", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=12)


def _start_site_detection(master, username):
    blocklist = _fetch_blocklist()
    if not blocklist:
        return

    state = {"matched": None, "warning": None}

    def poll():
        title = _foreground_window_title()
        warning = state["warning"]
        if warning is not None and warning.winfo_exists() and title == warning.title():
            previous_keyword = state["matched"][1] if state["matched"] else ""
            title = next(
                (candidate for candidate in _visible_window_titles(warning.winfo_id())
                 if previous_keyword and previous_keyword.lower() in candidate.lower()),
                "",
            )
        match = next(
            ((entry["keyword"], entry["category"]) for entry in blocklist
             if entry.get("keyword", "").lower() in title.lower()),
            None,
        ) if title else None
        if match:
            current_match = (title, match[0])
            if state["matched"] != current_match:
                if state["matched"] is not None:
                    _send_site_alert(username, state["matched"][0], "", "CLOSED")
                state["matched"] = (title, match[0])
                _send_site_alert(username, title, match[1], "OPEN")
            if (state["warning"] is None or not state["warning"].winfo_exists()
                    or state["warning"].site_text != title):
                if state["warning"] is not None and state["warning"].winfo_exists():
                    state["warning"].destroy()
                state["warning"] = RestrictedSiteWarning(master, title, match[1], True)
        elif state["matched"] is not None:
            _send_site_alert(username, state["matched"][0], "", "CLOSED")
            state["matched"] = None
            if state["warning"] is not None and state["warning"].winfo_exists():
                state["warning"].destroy()
            state["warning"] = None
        master.after(500, poll)

    master.after(1000, poll)

class LoginWindow(ctk.CTk):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.title("Student Login")
        self.geometry("300x250")
        
        ctk.CTkLabel(self, text="Username").pack(pady=10)
        self.user_entry = ctk.CTkEntry(self)
        self.user_entry.pack(pady=5)
        
        ctk.CTkButton(self, text="Login", command=self.attempt_login).pack(pady=20)

    def attempt_login(self):
        user = self.user_entry.get().strip()
        if user:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((ADMIN_IP, LOG_PORT))
                s.sendall(
                    f"ACTION: LOGIN | USER: {user} | PC: {socket.gethostname()} | "
                    f"TIME: {datetime.datetime.now().strftime('%H:%M:%S')}".encode()
                )
                s.close()
            except OSError as error:
                print(f"Cannot connect to Admin for logging: {error}")
            start_student_streaming(user)
            self.callback(user)
            self.destroy()

class ClientApp(ctk.CTk):
    def __init__(self, username):
        super().__init__()
        self.username = username
        self.title("Student Terminal")
        self.geometry("300x200")
        self.lock_window = None
        ctk.CTkLabel(self, text="System Online").pack(pady=50)
        threading.Thread(target=self.start_listener, daemon=True).start()
        _start_site_detection(self, username)
        self.protocol("WM_DELETE_WINDOW", self.close_app)

    def start_listener(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("0.0.0.0", 5000))
        server.listen(5)
        while True:
            conn, addr = server.accept()
            command = conn.recv(1024).decode()
            if command == "LOCK": self.after(0, self.show_lock)
            elif command == "UNLOCK": self.after(0, self.hide_lock)
            conn.close()

    def show_lock(self):
        if not self.lock_window:
            self.lock_window = ctk.CTkToplevel(self)
            self.lock_window.attributes("-fullscreen", True)
            self.lock_window.attributes("-topmost", True)
            ctk.CTkLabel(self.lock_window, text="TERMINAL LOCKED", font=("Arial", 80, "bold"), text_color="red").pack(expand=True)

    def hide_lock(self):
        if self.lock_window:
            self.lock_window.destroy()
            self.lock_window = None

    def close_app(self):
        stop_student_streaming()
        send_student_logout(self.username)
        self.destroy()

def run_app(username):
    app = ClientApp(username)
    app.mainloop()

if __name__ == "__main__":
    login = LoginWindow(callback=run_app)
    login.mainloop()