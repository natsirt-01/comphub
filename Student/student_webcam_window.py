import cv2
import customtkinter as ctk
import importlib
from PIL import Image, ImageTk
import threading
import time
import socket
from ui_utils import COLORS

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
        self.last_sent_time = 0.0
        self.last_expression = None
        self.current_expression = "Starting camera..."
        self.frame_lock = threading.Lock()
        self.latest_frame = None
        self.running = True
        self.stop_event = threading.Event()
        self.camera_error = None
        
        self.overrideredirect(True)
        
        # Sukat at pwesto sa kanang ibaba (Bottom-Right) para sa Normal state
        width = 400
        height = 300
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        self.normal_x = screen_width - width - 20
        self.normal_y = screen_height - height - 70
        
        self.geometry(f"{width}x{height}+{self.normal_x}+{self.normal_y}")
        self.attributes("-topmost", True)
        
        self.is_maximized = False
        self.is_minimized = False
        self.normal_geometry = f"{width}x{height}+{self.normal_x}+{self.normal_y}"
        
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        
        # --- VIDEO CONTAINER ---
        self.video_label = ctk.CTkLabel(self, text="", fg_color=COLORS["navy"])
        self.video_label.grid(row=0, column=0, sticky="nsew")
        
        # Dragging functionality
        self.video_label.bind("<ButtonPress-1>", self.start_move)
        self.video_label.bind("<B1-Motion>", self.do_move)

        # --- FLOATING CONTROL BUTTONS ---
        self.btn_frame = ctk.CTkFrame(self, fg_color=COLORS["navy_panel"], corner_radius=4)
        self.update_buttons_layout()

        # Minimize / Restore Small Button (-)
        self.min_btn = ctk.CTkButton(self.btn_frame, text="_", width=24, height=22, font=("Arial", 10, "bold"), fg_color="transparent", hover_color=COLORS["blue_hover"], command=self.toggle_minimize)
        self.min_btn.pack(side="left", padx=1, pady=1)
        
        # Fullscreen / Restore Button ([ ] / ❐)
        self.full_btn = ctk.CTkButton(self.btn_frame, text="□", width=24, height=22, font=("Arial", 10, "bold"), fg_color="transparent", hover_color=COLORS["pink_hover"], command=self.toggle_fullscreen)
        self.full_btn.pack(side="left", padx=1, pady=1)

        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.camera_error = "Camera unavailable"
            self.cap.release()
            self.cap = None
        else:
            self.current_expression = (
                "Waiting for face" if DeepFace is not None else "Emotion analysis unavailable"
            )
            self.thread = threading.Thread(target=self.update_video, daemon=True)
            self.thread.start()
            if DeepFace is not None:
                self.analysis_thread = threading.Thread(target=self.analyze_emotion_loop, daemon=True)
                self.analysis_thread.start()

        self.protocol("WM_DELETE_WINDOW", self.close_camera)
        self.after(30, self.render_video_frame)

    def update_buttons_layout(self):
        if self.is_minimized:
            self.btn_frame.place(relx=0.96, rely=0.92, anchor="se")
        else:
            self.btn_frame.place(relx=0.97, rely=0.95, anchor="se")

    def start_move(self, event):
        if not self.is_maximized:
            self.x = event.x_root
            self.y = event.y_root

    def do_move(self, event):
        if not self.is_maximized:
            deltax = event.x_root - self.x
            deltay = event.y_root - self.y
            x = self.winfo_x() + deltax
            y = self.winfo_y() + deltay
            self.geometry(f"+{x}+{y}")
            self.x = event.x_root
            self.y = event.y_root

    def toggle_minimize(self):
        if not self.is_minimized:
            if not self.is_maximized:
                self.normal_geometry = self.geometry()
            
            mini_w = 160
            mini_h = 120
            
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            
            min_x = screen_width - mini_w - 20
            min_y = screen_height - mini_h - 70
            
            self.geometry(f"{mini_w}x{mini_h}+{min_x}+{min_y}")
            self.is_minimized = True
            self.is_maximized = False
            self.min_btn.configure(text="❐")
            self.full_btn.configure(text="□")
            self.update_buttons_layout()
        else:
            self.geometry(self.normal_geometry)
            self.is_minimized = False
            self.min_btn.configure(text="_")
            self.update_buttons_layout()

    def toggle_fullscreen(self):
        if not self.is_minimized:
            if not self.is_maximized:
                self.normal_geometry = self.geometry()
                screen_width = self.winfo_screenwidth()
                screen_height = self.winfo_screenheight()
                self.geometry(f"{screen_width}x{screen_height}+0+0")
                self.is_maximized = True
                self.full_btn.configure(text="❐")
                self.update_buttons_layout()
            else:
                self.geometry(self.normal_geometry)
                self.is_maximized = False
                self.full_btn.configure(text="□")
                self.update_buttons_layout()

    def send_expression(self, expression):
        if not self.teacher_ip:
            return
        try:
            with socket.create_connection((self.teacher_ip, self.log_port), timeout=2.0) as client:
                pc_name = socket.gethostname()
                msg = f"EXPRESSION: {pc_name} - {self.username} | {expression}"
                client.sendall(msg.encode("utf-8"))
        except OSError as error:
            print(f"[webcam expression] Could not notify Teacher: {error}")

    def analyze_emotion_loop(self):
        """Hiwalay na thread para suriin ang emosyon gamit ang DeepFace bawat 2 segundo"""
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
            try:
                with self.frame_lock:
                    frame = None if self.latest_frame is None else self.latest_frame.copy()
                if frame is not None:
                    analysis = DeepFace.analyze(
                        frame, actions=["emotion"], enforce_detection=True, silent=True
                    )
                    if isinstance(analysis, list) and analysis:
                        analysis = analysis[0]
                        raw_emotion = analysis.get("dominant_emotion", "neutral")
                        self.current_expression = emotion_map.get(raw_emotion, raw_emotion.capitalize())
                    else:
                        self.current_expression = "No face detected"
            except Exception:
                self.current_expression = "No face detected"

    def update_video(self):
        while not self.stop_event.is_set():
            cap = self.cap
            if cap is None or not cap.isOpened():
                break
            ret, frame = cap.read()
            if not ret:
                self.camera_error = "Camera capture stopped"
                break
            with self.frame_lock:
                self.latest_frame = frame.copy()
            time.sleep(0.03)

    def render_video_frame(self):
        if not self.running or not self.winfo_exists():
            return
        with self.frame_lock:
            frame = None if self.latest_frame is None else self.latest_frame.copy()

        if frame is None:
            if self.camera_error:
                self.video_label.configure(text=self.camera_error, image=None)
            self.after(100, self.render_video_frame)
            return

        frame = cv2.flip(frame, 1)
        expression = self.current_expression or "No face detected"
        cv2.putText(frame, f"Emotion: {expression}", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 255), 2, cv2.LINE_AA)
        width = self.video_label.winfo_width()
        height = self.video_label.winfo_height()
        if width > 1 and height > 1:
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        photo = ImageTk.PhotoImage(image=image)
        self.video_label.configure(image=photo, text="")
        self.video_label.image = photo

        now = time.monotonic()
        if expression != self.last_expression or now - self.last_sent_time >= 2.0:
            self.last_expression = expression
            self.last_sent_time = now
            threading.Thread(target=self.send_expression, args=(expression,), daemon=True).start()
        self.after(30, self.render_video_frame)

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