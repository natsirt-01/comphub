import importlib
import socket
import threading
import time

import cv2
import customtkinter as ctk
from PIL import Image, ImageTk

from config import COLORS

try:
    DeepFace = importlib.import_module("deepface").DeepFace
except ImportError:
    DeepFace = None


class StudentWebcamOverlay(ctk.CTkToplevel):
    def __init__(self, master=None, username="Student", teacher_ip="", log_port=5001):
        super().__init__(master)
        self.username = username
        self.teacher_ip = teacher_ip
        self.log_port = log_port
        self.running = True
        self.stop_event = threading.Event()
        self.frame_lock = threading.Lock()
        self.latest_frame = None
        self.current_expression = "Starting camera..."
        self.last_sent_expression = None
        self.last_sent_at = 0.0
        self.is_maximized = False
        self.is_minimized = False

        self.title("Student Camera")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(self._corner_geometry(400, 300))
        self.normal_geometry = self.geometry()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.video_label = ctk.CTkLabel(
            self,
            text="Opening camera...",
            fg_color=COLORS["navy"],
            text_color=COLORS["white"],
        )
        self.video_label.grid(row=0, column=0, sticky="nsew")
        self.video_label.bind("<ButtonPress-1>", self.start_move)
        self.video_label.bind("<B1-Motion>", self.do_move)

        self.btn_frame = ctk.CTkFrame(self, fg_color=COLORS["navy_panel"], corner_radius=4)
        self.min_btn = ctk.CTkButton(
            self.btn_frame, text="_", width=28, height=24,
            fg_color="transparent", hover_color=COLORS["blue_hover"],
            command=self.toggle_minimize,
        )
        self.min_btn.pack(side="left", padx=2, pady=2)
        self.full_btn = ctk.CTkButton(
            self.btn_frame, text="□", width=28, height=24,
            fg_color="transparent", hover_color=COLORS["pink_hover"],
            command=self.toggle_fullscreen,
        )
        self.full_btn.pack(side="left", padx=2, pady=2)
        self.close_btn = ctk.CTkButton(
            self.btn_frame, text="×", width=28, height=24,
            fg_color=COLORS["danger"], hover_color=COLORS["pink_hover"],
            command=self.close_camera,
        )
        self.close_btn.pack(side="left", padx=2, pady=2)

        self.update_buttons_layout()
        self.protocol("WM_DELETE_WINDOW", self.close_camera)
        self.bind("<Escape>", lambda _event: self.close_camera())

        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.current_expression = "Camera unavailable"
            self.video_label.configure(text=self.current_expression)
            self.cap.release()
            self.cap = None
            self.stop_event.set()
            return

        if DeepFace is None:
            self.current_expression = "Emotion analysis unavailable"

        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        if DeepFace is not None:
            self.analysis_thread = threading.Thread(target=self._analyze_loop, daemon=True)
            self.analysis_thread.start()
        self.after(30, self._render_frame)

    def _corner_geometry(self, width, height):
        x = max(0, self.winfo_screenwidth() - width - 20)
        y = max(0, self.winfo_screenheight() - height - 70)
        return f"{width}x{height}+{x}+{y}"

    def update_buttons_layout(self):
        self.btn_frame.place(relx=0.99, rely=0.99, anchor="se")

    def start_move(self, event):
        self._drag_x = event.x_root
        self._drag_y = event.y_root

    def do_move(self, event):
        dx = event.x_root - self._drag_x
        dy = event.y_root - self._drag_y
        self.geometry(f"+{self.winfo_x() + dx}+{self.winfo_y() + dy}")
        self._drag_x = event.x_root
        self._drag_y = event.y_root

    def toggle_minimize(self):
        if self.is_minimized:
            self.geometry(self.normal_geometry)
            self.is_minimized = False
            self.min_btn.configure(text="_")
            return

        if not self.is_maximized:
            self.normal_geometry = self.geometry()
        self.geometry(self._corner_geometry(180, 135))
        self.is_minimized = True
        self.is_maximized = False
        self.min_btn.configure(text="□")
        self.full_btn.configure(text="□")

    def toggle_fullscreen(self):
        if self.is_minimized:
            self.is_minimized = False
        if self.is_maximized:
            self.geometry(self.normal_geometry)
            self.is_maximized = False
            self.full_btn.configure(text="□")
            return

        self.normal_geometry = self.geometry()
        self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        self.is_maximized = True
        self.full_btn.configure(text="❐")

    def _capture_loop(self):
        while not self.stop_event.is_set():
            cap = self.cap
            if cap is None or not cap.isOpened():
                break
            success, frame = cap.read()
            if not success:
                self.current_expression = "Camera capture stopped"
                break
            with self.frame_lock:
                self.latest_frame = frame.copy()
            time.sleep(0.03)

    def _analyze_loop(self):
        emotion_map = {
            "happy": "Smiling",
            "sad": "Sad",
            "angry": "Angry",
            "surprise": "Surprised",
            "fear": "Fearful",
            "disgust": "Disgusted",
            "neutral": "Neutral",
        }
        while not self.stop_event.wait(2.0):
            with self.frame_lock:
                frame = None if self.latest_frame is None else self.latest_frame.copy()
            if frame is None:
                continue
            try:
                analysis = DeepFace.analyze(
                    frame, actions=["emotion"], enforce_detection=True, silent=True
                )
                if isinstance(analysis, list):
                    analysis = analysis[0] if analysis else {}
                raw_emotion = analysis.get("dominant_emotion", "neutral")
                self.current_expression = emotion_map.get(raw_emotion, raw_emotion.capitalize())
            except Exception:
                self.current_expression = "No face detected"

    def _render_frame(self):
        if not self.running or not self.winfo_exists():
            return
        with self.frame_lock:
            frame = None if self.latest_frame is None else self.latest_frame.copy()

        if frame is not None:
            frame = cv2.flip(frame, 1)
            label = self.current_expression
            cv2.putText(
                frame, f"Emotion: {label}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (0, 220, 255), 2, cv2.LINE_AA,
            )
            width = self.video_label.winfo_width()
            height = self.video_label.winfo_height()
            if width > 1 and height > 1:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            photo = ImageTk.PhotoImage(image)
            self.video_label.configure(image=photo, text="")
            self.video_label.image = photo

            now = time.monotonic()
            if label != self.last_sent_expression or now - self.last_sent_at >= 2.0:
                self.last_sent_expression = label
                self.last_sent_at = now
                threading.Thread(target=self.send_expression, args=(label,), daemon=True).start()
        elif self.current_expression not in ("Starting camera...", "Camera unavailable"):
            self.video_label.configure(text=self.current_expression, image=None)

        self.after(30, self._render_frame)

    def send_expression(self, expression):
        if not self.teacher_ip:
            return
        try:
            with socket.create_connection((self.teacher_ip, self.log_port), timeout=2.0) as client:
                pc_name = socket.gethostname()
                message = f"EXPRESSION: {pc_name} - {self.username} | {expression}"
                client.sendall(message.encode("utf-8"))
        except OSError as error:
            print(f"[webcam expression] Could not notify Teacher: {error}")

    def close_camera(self):
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        cap = self.cap
        self.cap = None
        if cap is not None:
            cap.release()
        try:
            self.destroy()
        except Exception:
            pass