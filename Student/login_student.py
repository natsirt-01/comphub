import customtkinter as ctk
import socket
import threading
import json
import os
import re
import webbrowser
import struct
import cv2
import time
import ctypes
from datetime import datetime
import numpy as np
import tkinter as tk
from ctypes import wintypes
from PIL import Image, ImageTk
import screen_sender
from student_webcam_window import StudentWebcamOverlay
import pygetwindow as gw
from ui_utils import center_window, apply_theme, COLORS
from network_config import LOG_PORT, LISTENER_PORT, BROADCAST_PORT, get_admin_ip
apply_theme()

_keyboard_hook = None
_keyboard_hook_callback = None


def _make_fullscreen(window):
    window.overrideredirect(True)
    window.attributes("-fullscreen", True)


def _make_borderless(window):
    window.overrideredirect(True)


def _install_alt_tab_blocker():
    global _keyboard_hook, _keyboard_hook_callback
    if not hasattr(ctypes, "windll"):
        return

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    class KeyboardEvent(ctypes.Structure):
        _fields_ = [
            ("vk_code", wintypes.DWORD),
            ("scan_code", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("extra_info", ctypes.c_size_t),
        ]

    hook_proc_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, hook_proc_type, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    def keyboard_hook(code, message, event_pointer):
        if code >= 0 and message in (0x0100, 0x0104):
            event = ctypes.cast(event_pointer, ctypes.POINTER(KeyboardEvent)).contents
            if event.vk_code == 0x09 and user32.GetAsyncKeyState(0x12) & 0x8000:
                foreground = user32.GetForegroundWindow()
                process_id = wintypes.DWORD()
                user32.GetWindowThreadProcessId(foreground, ctypes.byref(process_id))
                if process_id.value == os.getpid():
                    return 1
        return user32.CallNextHookEx(_keyboard_hook, code, message, event_pointer)

    _keyboard_hook_callback = hook_proc_type(keyboard_hook)
    module = kernel32.GetModuleHandleW(None)
    _keyboard_hook = user32.SetWindowsHookExW(13, _keyboard_hook_callback, module, 0)


def _get_window_title(hwnd):
    if not hasattr(ctypes, "windll") or not hwnd:
        return ""
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd):
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title, length + 1)
    return title.value.strip()


class LockScreen(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        _make_fullscreen(self)
        self.attributes("-topmost", True)
        self.title("Terminal Locked")
        ctk.CTkLabel(self, text="TERMINAL LOCKED", font=("Arial", 60, "bold"), text_color="red").pack(expand=True)


class TeacherPOVViewer(ctk.CTkToplevel):
    """Shown to a student only while the teacher is actively Remote
    Controlling them. Displays the teacher's live screen. Not closable by
    the student, and excluded from Alt+Tab via overrideredirect."""
    def __init__(self, master, teacher_ip, broadcast_port):
        super().__init__(master)
        self.teacher_ip = teacher_ip
        self.broadcast_port = broadcast_port
        self.overrideredirect(True)  # no window frame -> not in Alt+Tab switcher
        self.attributes("-topmost", True)
        self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

        self.label = tk.Label(self, bg="black")
        self.label.pack(fill="both", expand=True)

        self.latest_image = None
        self._frame_pending = False
        self.running = True
        self._sock = None

        self._refocus_loop()
        threading.Thread(target=self._receive_loop, daemon=True).start()

    def _refocus_loop(self):
        if not self.running:
            return
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass
        self.after(500, self._refocus_loop)

    def _receive_loop(self):
        while self.running:
            try:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._sock.connect((self.teacher_ip, self.broadcast_port))

                while self.running:
                    header = self._sock.recv(4)
                    if not header:
                        break
                    frame_length = struct.unpack("!I", header)[0]

                    data = bytearray()
                    while len(data) < frame_length:
                        packet = self._sock.recv(frame_length - len(data))
                        if not packet:
                            break
                        data.extend(packet)

                    if len(data) == frame_length and self.running:
                        self.after(0, lambda d=bytes(data): self._update_frame(d))
            except Exception:
                time.sleep(1)
            finally:
                try:
                    if self._sock:
                        self._sock.close()
                except Exception:
                    pass

    def _update_frame(self, data):
        if self._frame_pending or not self.running:
            return
        self._frame_pending = True
        try:
            nparr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame)
                new_w = self.label.winfo_width()
                new_h = self.label.winfo_height()
                if new_w > 10 and new_h > 10:
                    image = image.resize((new_w, new_h), Image.Resampling.BILINEAR)
                photo = ImageTk.PhotoImage(image)
                self.label.config(image=photo)
                self.label.image = photo
        except Exception as e:
            print(f"[ERROR TeacherPOVViewer frame]: {e}")
        finally:
            self._frame_pending = False

    def close_pov(self):
        self.running = False
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

class DemoViewer(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

        self.video_label = tk.Label(self, bg="black")
        self.video_label.pack(fill="both", expand=True)

        self.latest_image = None
        self._frame_pending = False
        self.running = True

        self._refocus_loop()

    def _refocus_loop(self):
        if not self.running:
            return
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass
        self.after(500, self._refocus_loop)

    def update_frame(self, data):
        if self._frame_pending or not self.running:
            return
        self._frame_pending = True
        try:
            nparr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame)
                self.latest_image = image

                new_w = self.video_label.winfo_width()
                new_h = self.video_label.winfo_height()
                if new_w > 10 and new_h > 10:
                    image = image.resize((new_w, new_h), Image.Resampling.BILINEAR)

                photo = ImageTk.PhotoImage(image)
                self.video_label.config(image=photo)
                self.video_label.image = photo
        except Exception as e:
            print(f"Error sa pag-update ng live demo frame: {e}")
        finally:
            self._frame_pending = False

    def close_demo(self):
        self.running = False
        try:
            self.destroy()
        except Exception:
            pass

class RegisterWindow(ctk.CTkToplevel):
    def __init__(self, master, teacher_ip, log_port):
        super().__init__(master)
        self.teacher_ip = teacher_ip
        self.log_port = log_port
        self.title("Student Registration")
        center_window(self, 400, 680)
        _make_borderless(self)
        self.transient(master)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.close_window)

        ctk.CTkLabel(self, text="Create Student Account", font=("Arial", 20, "bold")).pack(pady=20)

        self.user_entry = ctk.CTkEntry(self, placeholder_text="Username", width=300)
        self.user_entry.pack(pady=5)
        self.pass_entry = ctk.CTkEntry(self, placeholder_text="Password", show="*", width=300)
        self.pass_entry.pack(pady=5)
        self.repass_entry = ctk.CTkEntry(self, placeholder_text="Re-type Password", show="*", width=300)
        self.repass_entry.pack(pady=5)
        self.fullname_entry = ctk.CTkEntry(self, placeholder_text="Full Name", width=300)
        self.fullname_entry.pack(pady=5)
        self.schoolid_entry = ctk.CTkEntry(self, placeholder_text="School ID Number", width=300)
        self.schoolid_entry.pack(pady=5)
        self.email_entry = ctk.CTkEntry(self, placeholder_text="Email", width=300)
        self.email_entry.pack(pady=5)
        self.contact_entry = ctk.CTkEntry(self, placeholder_text="Contact Number", width=300)
        self.contact_entry.pack(pady=5)
        self.course_entry = ctk.CTkEntry(self, placeholder_text="Course & Section", width=300)
        self.course_entry.pack(pady=5)
        self.year_entry = ctk.CTkEntry(self, placeholder_text="Year Level", width=300)
        self.year_entry.pack(pady=5)

        ctk.CTkLabel(self, text="Select your Teacher:").pack(pady=(10, 0))
        self.teacher_map = {}
        self.teacher_dropdown = ctk.CTkOptionMenu(self, values=["Loading..."], width=300)
        self.teacher_dropdown.pack(pady=5)
        self.after(100, self.fetch_teachers)

        ctk.CTkButton(self, text="Submit Registration", fg_color="green", command=self.submit_reg).pack(pady=20)
        self.status_lbl = ctk.CTkLabel(self, text="", text_color="white", wraplength=350)
        self.status_lbl.pack()

        self.lift()
        self.focus_force()
        self.grab_set()

    def close_window(self):
        self.grab_release()
        self.destroy()

    def fetch_teachers(self):
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(3)
            client.connect((self.teacher_ip, self.log_port))
            client.send("ACTION: GET_TEACHERS".encode())
            response = client.recv(4096).decode()
            client.close()

            teachers = json.loads(response)
            if teachers:
                self.teacher_map = {f"{t['full_name']} ({t['username']})": t["id"] for t in teachers}
                self.teacher_dropdown.configure(values=list(self.teacher_map.keys()))
                self.teacher_dropdown.set(list(self.teacher_map.keys())[0])
            else:
                self.teacher_dropdown.configure(values=["No teachers available"])
                self.teacher_dropdown.set("No teachers available")
        except Exception as e:
            self.teacher_dropdown.configure(values=["Connection failed"])
            self.teacher_dropdown.set("Connection failed")
            print(f"[ERROR fetch_teachers]: {e}")

    def submit_reg(self):
        user = self.user_entry.get().strip()
        pwd = self.pass_entry.get().strip()
        repwd = self.repass_entry.get().strip()
        full_name = self.fullname_entry.get().strip()
        school_id = self.schoolid_entry.get().strip()
        email = self.email_entry.get().strip()
        contact = self.contact_entry.get().strip()
        course = self.course_entry.get().strip()
        year = self.year_entry.get().strip()
        selected_teacher = self.teacher_dropdown.get()

        required = [user, pwd, repwd, full_name, school_id, email, contact, course, year]
        if not all(required):
            self.status_lbl.configure(text="Complete all fields.", text_color="orange")
            return

        if pwd != repwd:
            self.status_lbl.configure(text="Passwords do not match.", text_color="orange")
            return

        if len(pwd) < 8:
            self.status_lbl.configure(text="Password must be at least 8 characters.", text_color="orange")
            return

        email = email.lower()
        email_local_part = email.partition("@")[0]
        if (not re.fullmatch(r"[a-z0-9][a-z0-9.+-]*@gmail\.com", email)
            or ".." in email_local_part or email_local_part.endswith(".")
            or len(email_local_part) > 64):
            self.status_lbl.configure(text="Enter a valid Gmail address ending in @gmail.com.", text_color="orange")
            return

        if not re.fullmatch(r"\+?[0-9\s().-]+", contact) or not 10 <= len(re.sub(r"\D", "", contact)) <= 15:
            self.status_lbl.configure(text="Enter a valid contact number with 10 to 15 digits.", text_color="orange")
            return

        teacher_id = self.teacher_map.get(selected_teacher)
        if not teacher_id:
            self.status_lbl.configure(text="Select a valid teacher.", text_color="orange")
            return

        try:
            with socket.create_connection((self.teacher_ip, self.log_port), timeout=5) as client:
                msg = (
                    f"ACTION: REGISTER | USER: {user} | PWD: {pwd} | FULLNAME: {full_name} | "
                    f"SCHOOLID: {school_id} | EMAIL: {email} | CONTACT: {contact} | "
                    f"COURSE: {course} | YEAR: {year} | TEACHERID: {teacher_id}"
                )
                client.sendall(msg.encode())
                response = client.recv(512).decode("utf-8", errors="replace").strip()
            if response == "SUCCESS":
                self.status_lbl.configure(text="Registration submitted. Please wait for approval.", text_color="green")
            else:
                message = response.removeprefix("FAILED:").strip() or "Registration could not be saved."
                self.status_lbl.configure(text=message, text_color="orange")
        except Exception as e:
            self.status_lbl.configure(text=f"Connection failed: {e}", text_color="red")


class LabSelectionDialog(ctk.CTkToplevel):
    def __init__(self, master, teacher_ip, log_port, username, on_selected):
        super().__init__(master)
        self.teacher_ip = teacher_ip
        self.log_port = log_port
        self.username = username
        self.on_selected = on_selected
        self.title("Select Computer Lab")
        self.geometry("350x220")
        _make_borderless(self)
        self.attributes("-topmost", True)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # must pick a lab, can't just close this
        self.bind_all("<Control-Shift-F4>", lambda e: self.destroy())
        self.focus_force()

        ctk.CTkLabel(self, text="Which lab are you in?", font=("Arial", 16, "bold")).pack(pady=20)

        self.lab_map = {}
        self.lab_dropdown = ctk.CTkOptionMenu(self, values=["Loading..."], width=250)
        self.lab_dropdown.pack(pady=10)
        self.after(100, self.fetch_labs)

        ctk.CTkButton(self, text="Confirm", command=self.confirm).pack(pady=20)
        self.status_lbl = ctk.CTkLabel(self, text="", text_color="red")
        self.status_lbl.pack()

    def fetch_labs(self):
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(3)
            client.connect((self.teacher_ip, self.log_port))
            client.send("ACTION: GET_LABS".encode())
            response = client.recv(4096).decode()
            client.close()

            labs = json.loads(response)
            if labs:
                self.lab_map = {lab["name"]: lab["id"] for lab in labs}
                self.lab_dropdown.configure(values=list(self.lab_map.keys()))
                self.lab_dropdown.set(list(self.lab_map.keys())[0])
            else:
                self.lab_dropdown.configure(values=["No labs found"])
        except Exception as e:
            self.lab_dropdown.configure(values=["Connection failed"])
            print(f"[ERROR fetch_labs]: {e}")

    def confirm(self):
        selected = self.lab_dropdown.get()
        lab_id = self.lab_map.get(selected)
        if not lab_id:
            self.status_lbl.configure(text="Please wait for labs to load.")
            return
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((self.teacher_ip, self.log_port))
            client.send(f"ACTION: SET_LAB | USER: {self.username} | LABID: {lab_id}".encode())
            client.recv(1024)
            client.close()
        except Exception as e:
            print(f"[ERROR set_lab]: {e}")

        self.destroy()
        self.on_selected()

class StudentDashboard(ctk.CTkToplevel):
    def __init__(self, username, master_app):
        super().__init__()
        self.username = username
        self.master_app = master_app
        self.title(f"Student Portal - {self.username}")
        self.configure(fg_color=COLORS["surface"])
        self.protocol("WM_DELETE_WINDOW", self.logout)
        center_window(self, 1100, 760)
        
        tabview = ctk.CTkTabview(self)
        tabview.pack(expand=True, fill="both", padx=20, pady=20)
        tabview.add("My Account")
        tabview.add("History")
        tabview.add("Settings")
        
        ctk.CTkLabel(tabview.tab("My Account"), text=f"Welcome back, {self.username}",
                 text_color=COLORS["ink"], font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(55, 10))
        ctk.CTkLabel(tabview.tab("My Account"), text="Your lab session is active.",
                 text_color=COLORS["muted"]).pack(pady=4)
        ctk.CTkButton(tabview.tab("My Account"), text="Log Out", width=180, height=40,
                  fg_color=COLORS["danger"], hover_color=COLORS["pink_hover"], command=self.logout).pack(pady=28)
        history_date_row = ctk.CTkFrame(tabview.tab("History"), fg_color="transparent")
        history_date_row.pack(fill="x", padx=10, pady=(10, 0))
        self.history_start_date = ctk.CTkEntry(history_date_row, placeholder_text="From (YYYY-MM-DD)", width=150)
        self.history_start_date.pack(side="left", padx=(0, 6))
        self.history_end_date = ctk.CTkEntry(history_date_row, placeholder_text="To (YYYY-MM-DD)", width=150)
        self.history_end_date.pack(side="left", padx=6)
        ctk.CTkButton(history_date_row, text="Apply", width=80, command=self.load_history).pack(side="left", padx=6)
        ctk.CTkButton(history_date_row, text="Clear", width=70, command=self.clear_history_dates).pack(side="left", padx=6)
        self.history_filter_status = ctk.CTkLabel(history_date_row, text="", anchor="w")
        self.history_filter_status.pack(side="left", padx=8)

        history_frame = ctk.CTkScrollableFrame(tabview.tab("History"), width=440, height=300)
        history_frame.pack(padx=10, pady=10, fill="both", expand=True)
        self.history_frame = history_frame
        ctk.CTkButton(tabview.tab("History"), text="Refresh History", width=160,
                  fg_color=COLORS["blue"], hover_color=COLORS["blue_hover"], command=self.load_history).pack(pady=8)
        self.after(200, self.load_history)
        
        self.old_p = ctk.CTkEntry(tabview.tab("Settings"), placeholder_text="Old Password", show="*")
        self.old_p.pack(pady=5)
        self.new_p = ctk.CTkEntry(tabview.tab("Settings"), placeholder_text="New Password", show="*")
        self.new_p.pack(pady=5)
        self.re_p = ctk.CTkEntry(tabview.tab("Settings"), placeholder_text="Re-type New", show="*")
        self.re_p.pack(pady=5)
        ctk.CTkButton(tabview.tab("Settings"), text="Update Password", width=180, height=38,
                  fg_color=COLORS["blue"], hover_color=COLORS["blue_hover"], command=self.change_password).pack(pady=16)
        self.profile_password = ctk.CTkEntry(tabview.tab("Settings"), placeholder_text="Current Password", show="*")
        self.profile_password.pack(pady=(20, 5))
        self.profile_name = ctk.CTkEntry(tabview.tab("Settings"), placeholder_text="New Display Name")
        self.profile_name.pack(pady=5)
        ctk.CTkButton(tabview.tab("Settings"), text="Update Display Name", width=180, height=38,
                  fg_color=COLORS["blue"], hover_color=COLORS["blue_hover"],
                  command=self.update_profile).pack(pady=10)
        self.msg = ctk.CTkLabel(tabview.tab("Settings"), text="")    
        self.msg.pack()

    def change_password(self):
        old_pwd = self.old_p.get().strip()
        new_pwd = self.new_p.get().strip()
        re_pwd = self.re_p.get().strip()

        if not old_pwd or not new_pwd or not re_pwd:
            self.msg.configure(text="Complete all fields.", text_color="orange")
            return
        if new_pwd != re_pwd:
            self.msg.configure(text="New passwords do not match.", text_color="red")
            return

        try:
            admin_ip = self.master_app.refresh_admin_ip()
            if not admin_ip:
                self.msg.configure(text="Admin is not available on this local network.", text_color="red")
                return
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((self.master_app.admin_ip, LOG_PORT))
            msg = f"ACTION: CHANGE_PWD | USER: {self.username} | OLDPWD: {old_pwd} | NEWPWD: {new_pwd}"
            client.send(msg.encode())
            response = client.recv(1024).decode().strip()
            client.close()

            if response == "SUCCESS":
                self.msg.configure(text="Success!", text_color="green")
            else:
                self.msg.configure(text="Wrong current password!", text_color="red")
        except Exception as e:
            self.msg.configure(text=f"Connection error: {e}", text_color="red")

    def update_profile(self):
        password = self.profile_password.get().strip()
        full_name = self.profile_name.get().strip()
        if not password or not full_name:
            self.msg.configure(text="Enter your current password and a display name.", text_color="orange")
            return
        try:
            admin_ip = self.master_app.refresh_admin_ip()
            if not admin_ip:
                self.msg.configure(text="Admin is not available on this local network.", text_color="red")
                return
            with socket.create_connection((admin_ip, LOG_PORT), timeout=3) as client:
                request = f"ACTION: UPDATE_PROFILE | USER: {self.username} | PWD: {password} | FULLNAME: {full_name}"
                client.sendall(request.encode())
                response = client.recv(1024).decode().strip()
            if response == "SUCCESS":
                self.msg.configure(text="Display name updated.", text_color="green")
                self.profile_password.delete(0, "end")
            else:
                self.msg.configure(text="Current password is incorrect.", text_color="red")
        except OSError as error:
            self.msg.configure(text=f"Connection error: {error}", text_color="red")

    def load_history(self):
        for widget in self.history_frame.winfo_children():
            widget.destroy()

        try:
            admin_ip = self.master_app.refresh_admin_ip()
            if not admin_ip:
                raise OSError("Admin is not available on this local network.")
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(3)
            client.connect((self.master_app.admin_ip, LOG_PORT))
            client.send(f"ACTION: GET_HISTORY | USER: {self.username}".encode())
            response = client.recv(8192).decode()
            client.close()

            records = json.loads(response)
            try:
                start_text = self.history_start_date.get().strip()
                end_text = self.history_end_date.get().strip()
                start = datetime.strptime(start_text, "%Y-%m-%d").date() if start_text else None
                end = datetime.strptime(end_text, "%Y-%m-%d").date() if end_text else None
                if start and end and start > end:
                    raise ValueError("Start date must not be after end date.")
            except ValueError as error:
                self.history_filter_status.configure(text=str(error), text_color="red")
                return

            records = [record for record in records if (
                (start is None and end is None)
                or (record.get("login_time") and
                    (start is None or datetime.strptime(record["login_time"][:10], "%Y-%m-%d").date() >= start)
                    and (end is None or datetime.strptime(record["login_time"][:10], "%Y-%m-%d").date() <= end))
            )]
            self.history_filter_status.configure(text=f"{len(records)} session(s)", text_color=COLORS["muted"])
            if not records:
                ctk.CTkLabel(self.history_frame, text="No history yet.", text_color="gray").pack(pady=10)
                return

            for r in records:
                mins, secs = divmod(r["duration_secs"], 60)
                hrs, mins = divmod(mins, 60)
                duration_str = f"{hrs}h {mins}m {secs}s"
                text = (
                    f"Teacher: {r['teacher']}\n"
                    f"Lab: {r['lab_name']}\n"
                    f"Login: {r['login_time']}   Logout: {r['logout_time']}\n"
                    f"Duration: {duration_str}"
                )
                frm = ctk.CTkFrame(self.history_frame)
                frm.pack(fill="x", padx=5, pady=5)
                ctk.CTkLabel(frm, text=text, justify="left", anchor="w").pack(fill="x", padx=10, pady=8)
        except Exception as e:
            ctk.CTkLabel(self.history_frame, text=f"Error loading history: {e}", text_color="red").pack(pady=10)

    def clear_history_dates(self):
        self.history_start_date.delete(0, "end")
        self.history_end_date.delete(0, "end")
        self.load_history()

    def logout(self):
        session_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_session.json")
        if os.path.exists(session_path):
            try:
                os.remove(session_path)
            except:
                pass
        
        if hasattr(self.master_app, 'webcam_overlay') and self.master_app.webcam_overlay:
            self.master_app.webcam_overlay.close_camera()
            self.master_app.webcam_overlay = None

        self.master_app.notify_teacher("LOGOUT", self.username)
        self.destroy()
        self.master_app.deiconify()        
        self.master_app.after(100, self.master_app.fetch_teachers_and_labs)

class LoginApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Student Login")
        self.configure(fg_color=COLORS["navy"])
        center_window(self, 700, 740)
        
        self.active_lock = None
        self.demo_window = None
        self.webcam_overlay = None
        self.in_demo_mode = False
        self.admin_ip = None
        self.teacher_ip = None
        self.window_tracker_started = False
        self.blocklist_cache = []
        threading.Thread(target=self.refresh_blocklist_periodically, daemon=True).start()
        
        threading.Thread(target=self.start_server, daemon=True).start()
        threading.Thread(target=self.start_broadcast_listener, daemon=True).start()
        threading.Thread(target=screen_sender.start_control_listener, daemon=True).start()
        
        header = ctk.CTkFrame(self, fg_color=COLORS["navy_panel"], corner_radius=0, height=92)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="COMPHUB STUDENT", text_color=COLORS["white"],
                 font=ctk.CTkFont(size=25, weight="bold")).pack(anchor="w", padx=42, pady=(22, 0))
        ctk.CTkLabel(header, text="Connect to your teacher and computer lab", text_color="#e6d9f1").pack(anchor="w", padx=44, pady=(2, 14))

        login_panel = ctk.CTkFrame(self, width=520, height=520, corner_radius=14,
                       fg_color=COLORS["white"], border_width=1,
                       border_color=COLORS["surface_alt"])
        login_panel.pack(expand=True, padx=24, pady=(22, 38))
        login_panel.pack_propagate(False)
        ctk.CTkLabel(login_panel, text="STUDENT SIGN IN", text_color=COLORS["navy"],
                 font=ctk.CTkFont(size=21, weight="bold")).pack(anchor="w", padx=34, pady=(22, 12))

        ctk.CTkLabel(login_panel, text="Select Teacher", text_color=COLORS["ink"], font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=36)
        self.teacher_map = {}
        self.teacher_dropdown = ctk.CTkOptionMenu(login_panel, values=["Loading..."], height=38)
        self.teacher_dropdown.pack(pady=(5, 12), padx=34, fill="x")

        ctk.CTkLabel(login_panel, text="Select Computer Lab", text_color=COLORS["ink"], font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=36)
        self.lab_map = {}
        self.lab_dropdown = ctk.CTkOptionMenu(login_panel, values=["Loading..."], height=38)
        self.lab_dropdown.pack(pady=(5, 12), padx=34, fill="x")

        self.after(100, self.fetch_teachers_and_labs)

        self.user_entry = ctk.CTkEntry(login_panel, placeholder_text="Username", height=40)
        self.user_entry.pack(pady=6, padx=34, fill="x")
        password_row = ctk.CTkFrame(login_panel, fg_color="transparent")
        password_row.pack(pady=6, padx=34, fill="x")
        self.pass_entry = ctk.CTkEntry(password_row, placeholder_text="Password", show="*", height=40)
        self.pass_entry.pack(side="left", fill="x", expand=True)
        self.password_visible = False
        self.password_toggle = ctk.CTkButton(
            password_row, text="👁", width=42, height=40,
            fg_color=COLORS["surface_alt"], text_color=COLORS["ink"],
            hover_color=COLORS["surface"], command=self.toggle_password_visibility,
        )
        self.password_toggle.pack(side="left", padx=(6, 0))

        ctk.CTkButton(login_panel, text="Sign In", height=42, fg_color=COLORS["blue"],
              hover_color=COLORS["blue_hover"], command=self.check_login).pack(pady=(16, 8), padx=34, fill="x")
        
        self.error_label = ctk.CTkLabel(login_panel, text="", text_color=COLORS["danger"])
        self.error_label.pack(pady=3)
        
        ctk.CTkButton(login_panel, text="Create an Account", fg_color="transparent", text_color=COLORS["navy_panel"], 
              hover_color=COLORS["surface_alt"], command=self.open_registration).pack(pady=3)

    def toggle_password_visibility(self):
        self.password_visible = not self.password_visible
        self.pass_entry.configure(show="" if self.password_visible else "*")

    def refresh_admin_ip(self):
        self.admin_ip = get_admin_ip(timeout=1.0)
        return self.admin_ip

    def track_active_window(self):
        last_window = ""
        last_restricted = None
        last_username = ""
        restricted_hwnd = None
        pending_site_alerts = []

        def queue_site_alert(username, text, category, status):
            alert = (username, text, category, status)
            if pending_site_alerts:
                pending_site_alerts.append(alert)
            elif not self.notify_site_alert(*alert):
                pending_site_alerts.append(alert)

        while True:
            try:
                if pending_site_alerts and self.notify_site_alert(*pending_site_alerts[0]):
                    pending_site_alerts.pop(0)

                session_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_session.json")
                if not os.path.exists(session_path):
                    self.after(0, self.clear_restricted_warning)
                    if last_restricted and last_username:
                        queue_site_alert(last_username, last_restricted[0], last_restricted[1], "CLOSED")
                    last_restricted = None
                    restricted_hwnd = None
                    last_window = ""
                    time.sleep(3)
                    continue

                try:
                    with open(session_path, "r") as sf:
                        username_val = json.load(sf).get("username", "Student")
                except (OSError, ValueError):
                    username_val = "Student"
                last_username = username_val

                user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
                current_hwnd = user32.GetForegroundWindow() if user32 else None
                current_window = _get_window_title(current_hwnd)
                if not current_window:
                    active_win = gw.getActiveWindow()
                    current_window = active_win.title.strip() if active_win and active_win.title else ""
                if restricted_hwnd:
                    tracked_title = _get_window_title(restricted_hwnd)
                    if tracked_title:
                        current_hwnd = restricted_hwnd
                        current_window = tracked_title

                if current_window:
                    restricted_entry = next(
                        (entry for entry in self.blocklist_cache
                         if entry["keyword"].lower() in current_window.lower()),
                        None,
                    )
                    if restricted_entry:
                        self.after(0, lambda t=current_window, c=restricted_entry["category"]: self.show_restricted_warning(t, c))
                        if last_restricted != (current_window, restricted_entry["category"]):
                            queue_site_alert(username_val, current_window, restricted_entry["category"], "OPEN")
                        last_restricted = (current_window, restricted_entry["category"])
                        restricted_hwnd = current_hwnd
                    elif last_restricted:
                        self.after(0, self.clear_restricted_warning)
                        queue_site_alert(username_val, last_restricted[0], last_restricted[1], "CLOSED")
                        last_restricted = None
                        restricted_hwnd = None

                    if current_window != last_window:
                        last_window = current_window

                        admin_ip = self.refresh_admin_ip()
                        if not admin_ip:
                            time.sleep(1)
                            continue

                        for entry in self.blocklist_cache:
                            if entry["keyword"].lower() in current_window.lower():
                                self.after(0, lambda t=current_window, c=entry["category"]: self.show_restricted_warning(t, c))
                                break

                        activity = json.dumps({
                            "username": username_val,
                            "activity_type": "window_change",
                            "details": current_window,
                        })
                        with socket.create_connection((admin_ip, LOG_PORT), timeout=3) as client:
                            client.sendall(f"ACTION: LOG_ACTIVITY | DATA: {activity}".encode("utf-8"))
                            response = client.recv(32).decode("utf-8", errors="ignore")
                        if response != "SUCCESS":
                            print(f"[DEBUG STUDENT ACTIVITY] Event was not saved: {current_window}")
                elif last_restricted:
                    self.after(0, self.clear_restricted_warning)
                    queue_site_alert(username_val, last_restricted[0], last_restricted[1], "CLOSED")
                    last_restricted = None
                    restricted_hwnd = None
                    last_window = ""
            except Exception as e:
                print(f"[DEBUG STUDENT ACTIVITY ERROR]: {e}")
            time.sleep(3)



    def _open_pov_viewer(self):
        if self.pov_viewer and self.pov_viewer.winfo_exists():
            return
        if self.teacher_ip and self.refresh_admin_ip():
            self.pov_viewer = TeacherPOVViewer(self, self.teacher_ip, BROADCAST_PORT)

    def _close_pov_viewer(self):
        if self.pov_viewer:
            self.pov_viewer.close_pov()
            self.pov_viewer = None        

    def start_broadcast_listener(self):
        while True:
            while not self.in_demo_mode:
                time.sleep(0.2)
                
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                if not self.teacher_ip or not self.refresh_admin_ip():
                    time.sleep(0.5)
                    continue
                s.connect((self.teacher_ip, BROADCAST_PORT))
                
                while self.in_demo_mode:
                    header = s.recv(4)
                    if not header:
                        break
                    frame_length = struct.unpack("!I", header)[0]
                    
                    data = bytearray()
                    while len(data) < frame_length:
                        packet = s.recv(frame_length - len(data))
                        if not packet:
                            break
                        data.extend(packet)
                    
                    if len(data) == frame_length and self.demo_window and self.demo_window.winfo_exists():
                        self.after(0, lambda d=bytes(data): self.demo_window.update_frame(d))
            except Exception:
                time.sleep(0.5)
            finally:
                try:
                    s.close()
                except Exception:
                    pass

    def fetch_blocklist(self):
        try:
            admin_ip = self.refresh_admin_ip()
            if not admin_ip:
                self.blocklist_cache = []
                return
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(3)
            client.connect((admin_ip, LOG_PORT))
            client.send("ACTION: GET_BLOCKLIST".encode())
            response = client.recv(4096).decode()
            client.close()
            self.blocklist_cache = json.loads(response)
        except Exception as e:
            print(f"[ERROR fetch_blocklist]: {e}")
            self.blocklist_cache = []

    def refresh_blocklist_periodically(self):
        while True:
            self.fetch_blocklist()
            time.sleep(30)

    def open_registration(self):
        admin_ip = self.refresh_admin_ip()
        if not admin_ip:
            self.error_label.configure(text="Admin server not found on the local network.", text_color=COLORS["danger"])
            return
        RegisterWindow(self, admin_ip, LOG_PORT)
    def show_restricted_warning(self, window_text, category):
        if hasattr(self, "restricted_warning") and self.restricted_warning and self.restricted_warning.winfo_exists():
            return
        previous_foreground = ctypes.windll.user32.GetForegroundWindow() if hasattr(ctypes, "windll") else None
        warn = ctk.CTkToplevel(self)
        self.restricted_warning = warn
        warn.title("WARNING")
        center_window(warn, 450, 220)
        warn.attributes("-topmost", True)
        warn.resizable(False, False)
        warn.overrideredirect(True)  # removes the title bar entirely, so there's nothing to grab and drag
        warn.configure(fg_color="#c62828")
        ctk.CTkLabel(warn, text="RESTRICTED SITE DETECTED", font=("Arial", 18, "bold"), text_color="white").pack(pady=15)
        ctk.CTkLabel(warn, text=f"Category: {category.upper()}", font=("Arial", 13, "bold"), text_color=COLORS["sky"]).pack()
        ctk.CTkLabel(warn, text=window_text, font=("Arial", 11), text_color="white", wraplength=400).pack(pady=10)
        ctk.CTkLabel(warn, text="This activity has been reported to your teacher.", text_color="white").pack(pady=5)
        ctk.CTkLabel(
            warn,
            text="Close the restricted tab or leave the site to remove this warning.",
            text_color="white",
        ).pack(pady=10)
        warn.after(0, self._set_warning_no_activate, warn, previous_foreground)

    @staticmethod
    def _set_warning_no_activate(warning, previous_foreground=None):
        if not hasattr(ctypes, "windll") or not warning.winfo_exists():
            return
        try:
            user32 = ctypes.windll.user32
            hwnd = warning.winfo_id()
            extended_style = user32.GetWindowLongW(hwnd, -20)
            user32.SetWindowLongW(hwnd, -20, extended_style | 0x08000000)
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0033)
            if previous_foreground:
                user32.SetForegroundWindow(previous_foreground)
        except (AttributeError, OSError):
            pass

    def clear_restricted_warning(self):
        warning = getattr(self, "restricted_warning", None)
        if warning and warning.winfo_exists():
            warning.destroy()
        self.restricted_warning = None

    def start_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", LISTENER_PORT))
        server.listen(5)
        while True:
            try:
                conn, addr = server.accept()
                command = conn.recv(1024).decode().strip()
                
                session_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_session.json")
                is_logged_in = os.path.exists(session_path)
                
                if not is_logged_in and command in ["LOCK", "UNLOCK", "SHUTDOWN", "REBOOT", "SLEEP", "START_DEMO", "STOP_DEMO"]:
                    conn.close()
                    continue

                if command == "LOCK": 
                    self.after(0, self.show_lock)
                elif command == "UNLOCK":
                    self.after(0, self.hide_lock)
                elif command == "START_DEMO":
                    self.in_demo_mode = True
                    self.after(0, self.open_demo_viewer)
                elif command == "STOP_DEMO":
                    self.in_demo_mode = False
                    self.after(0, self.close_demo_viewer)
                elif command.startswith("MSG:"):
                    msg_content = command.replace("MSG:", "", 1)
                    self.after(0, lambda: self.show_teacher_message(msg_content))
                elif command.startswith("URL:"):
                    url_content = command.replace("URL:", "", 1)
                    self.after(0, lambda: self.open_student_browser(url_content))
                elif command == "SHUTDOWN":
                    try:
                        with open(session_path, "r") as session_file:
                            username = json.load(session_file).get("username")
                        if username:
                            self.notify_teacher("LOGOUT", username)
                    except (OSError, ValueError):
                        pass
                    try:
                        os.remove(session_path)
                    except OSError:
                        pass
                    os.system("shutdown /s /t 1")
                elif command == "REBOOT":
                    os.system("shutdown /r /t 1")
                elif command == "SLEEP":
                    os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
                conn.close()
            except: break

    def open_demo_viewer(self):
        if not self.demo_window or not self.demo_window.winfo_exists():
            self.demo_window = DemoViewer(self)

    def close_demo_viewer(self):
        if self.demo_window and self.demo_window.winfo_exists():
            self.demo_window.close_demo()
            self.demo_window = None

    def show_lock(self):
        if not self.active_lock:
            self.active_lock = LockScreen(self)

    def hide_lock(self):
        if self.active_lock:
            self.active_lock.destroy()
            self.active_lock = None

    def show_teacher_message(self, message):
        msg_win = ctk.CTkToplevel(self)
        msg_win.title("Message from Teacher")
        center_window(msg_win, 400, 200)
        msg_win.attributes("-topmost", True)
        msg_win.grab_set()
        
        ctk.CTkLabel(msg_win, text="TEACHER ANNOUNCEMENT", font=("Arial", 14, "bold"), text_color="#1f6aa5").pack(pady=15)
        
        txt_box = ctk.CTkTextbox(msg_win, width=350, height=80)
        txt_box.insert("1.0", message)
        txt_box.configure(state="disabled")
        txt_box.pack(pady=5)
        
        ctk.CTkButton(msg_win, text="OK", command=msg_win.destroy).pack(pady=15)

    def open_student_browser(self, url):
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        webbrowser.open_new_tab(url)

    def fetch_teachers_and_labs(self):
        self.admin_ip = get_admin_ip(timeout=3)
        if not self.admin_ip:
            self.teacher_dropdown.configure(values=["Admin not found on this LAN"])
            self.lab_dropdown.configure(values=["Admin not found on this LAN"])
            self.error_label.configure(text="Cannot find the Admin app. Make sure it is running on the same local network.", text_color=COLORS["danger"])
            self.after(5000, self.fetch_teachers_and_labs)
            return
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(3)
            client.connect((self.admin_ip, LOG_PORT))
            client.send("ACTION: GET_TEACHERS".encode())
            response = client.recv(4096).decode()
            client.close()
            teachers = json.loads(response)
            online_teachers = [teacher for teacher in teachers if teacher.get("ip_address")]
            if online_teachers:
                self.teacher_map = {f"{t['full_name']} ({t['username']})": t["id"] for t in online_teachers}
                self.teacher_ip_map = {f"{t['full_name']} ({t['username']})": t["ip_address"] for t in online_teachers}
                self.teacher_dropdown.configure(values=list(self.teacher_map.keys()))
                self.teacher_dropdown.set(list(self.teacher_map.keys())[0])
            else:
                self.teacher_map = {}
                self.teacher_ip_map = {}
                self.teacher_dropdown.configure(values=["No online teachers"])
        except Exception as e:
            self.teacher_dropdown.configure(values=["Connection failed"])
            print(f"[ERROR fetch_teachers]: {e}")

        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(3)
            client.connect((self.admin_ip, LOG_PORT))
            client.send("ACTION: GET_LABS".encode())
            response = client.recv(4096).decode()
            client.close()
            labs = json.loads(response)
            if labs:
                self.lab_map = {lab["name"]: lab["id"] for lab in labs}
                self.lab_dropdown.configure(values=list(self.lab_map.keys()))
                self.lab_dropdown.set(list(self.lab_map.keys())[0])
            else:
                self.lab_dropdown.configure(values=["No labs found"])
        except Exception as e:
            self.lab_dropdown.configure(values=["Connection failed"])
            print(f"[ERROR fetch_labs]: {e}")

        if not getattr(self, "teacher_ip_map", {}):
            self.after(5000, self.fetch_teachers_and_labs)

    def check_login(self):
        user = self.user_entry.get().strip()
        pwd = self.pass_entry.get().strip()

        if not user or not pwd:
            self.error_label.configure(text="Complete all fields.", text_color="orange")
            return

        if not self.refresh_admin_ip():
            self.error_label.configure(text="Admin server not found on the local network.", text_color=COLORS["danger"])
            return

        selected_teacher_name = self.teacher_dropdown.get()
        selected_lab_name = self.lab_dropdown.get()
        teacher_id = self.teacher_map.get(selected_teacher_name)
        teacher_ip = getattr(self, "teacher_ip_map", {}).get(selected_teacher_name)
        lab_id = self.lab_map.get(selected_lab_name)

        if not teacher_id or not lab_id or not teacher_ip:
            self.error_label.configure(text="Select an online teacher and a lab on this network.", text_color="orange")
            return

        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(4)
            client.connect((self.admin_ip, LOG_PORT))

            msg = f"ACTION: LOGIN_CHECK | USER: {user} | PWD: {pwd} | TEACHERID: {teacher_id} | LABID: {lab_id}"
            client.send(msg.encode())

            response = client.recv(1024).decode().strip()
            client.close()

            if response == "SUCCESS":
                session_data = {"username": user}
                session_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_session.json")
                with open(session_path, "w") as f:
                    json.dump(session_data, f)

                if not self.window_tracker_started:
                    self.window_tracker_started = True
                    threading.Thread(target=self.track_active_window, daemon=True).start()

                self.notify_teacher("LOGIN", user)

                self.teacher_ip = teacher_ip
                threading.Thread(target=screen_sender.start_admin_stream, args=(self.admin_ip,), daemon=True).start()
                threading.Thread(target=screen_sender.start_live_monitoring, args=(teacher_ip,), daemon=True).start()
                threading.Thread(target=screen_sender.start_live_monitoring, args=(self.admin_ip, True), daemon=True).start()

                self.withdraw()
                self.webcam_overlay = StudentWebcamOverlay(self, username=user, teacher_ip=teacher_ip, log_port=LOG_PORT)
                StudentDashboard(username=user, master_app=self)

            elif response == "TEACHER_OFFLINE":
                self.error_label.configure(text="No teacher is online yet. Please wait.", text_color="red")
            elif response == "LAB_MISMATCH":
                self.error_label.configure(text="The selected teacher or lab is invalid.", text_color="red")
            elif response == "ADMIN_OFFLINE":
                self.error_label.configure(text="The Admin and Teacher must sign in first.", text_color="red")
            else:
                self.error_label.configure(text="Invalid credentials or account not yet approved.", text_color="red")
        except Exception as e:
            self.error_label.configure(text=f"Could not connect to the Teacher: {e}", text_color="red")
        
    def notify_teacher(self, action, username):
        try:
            admin_ip = self.refresh_admin_ip()
            if not admin_ip:
                return
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(3)
            client.connect((admin_ip, LOG_PORT))
            msg = f"ACTION: {action} | USER: {username}"
            client.send(msg.encode())
            client.close()
        except Exception:
            pass

    def notify_site_alert(self, username, text, category, status):
        try:
            admin_ip = self.refresh_admin_ip()
            if not admin_ip:
                return False
            with socket.create_connection((admin_ip, LOG_PORT), timeout=3) as client:
                client.sendall(
                    f"ACTION: SITE_ALERT | USER: {username} | TEXT: {text} | "
                    f"CATEGORY: {category} | STATUS: {status}".encode()
                )
                return client.recv(32).decode("utf-8", errors="ignore") == "SUCCESS"
        except OSError:
            return False

if __name__ == "__main__":
    app = LoginApp()
    app.mainloop()