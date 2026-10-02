import os
import cv2
import customtkinter as ctk
from PIL import Image, ImageTk
import threading
import time
import socket
from ui_utils import COLORS


class SimpleExpressionDetector:
    def __init__(self):
        self.face_cascade = None
        self.available = False

        cascade_root = os.path.join(os.path.dirname(cv2.__file__), "data")
        cascade_dir = os.path.join(cascade_root, "haarcascades")
        os.makedirs(cascade_dir, exist_ok=True)

        cascade_path = os.path.join(cascade_dir, "haarcascade_frontalface_default.xml")
        if not os.path.exists(cascade_path):
            try:
                import requests
                response = requests.get(
                    "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml",
                    timeout=20,
                )
                response.raise_for_status()
                with open(cascade_path, "wb") as file:
                    file.write(response.content)
            except Exception as error:
                print(f"[emotion detector] Could not download Haar cascade: {error}")

        if os.path.exists(cascade_path):
            self.face_cascade = cv2.CascadeClassifier(cascade_path)
            self.available = self.face_cascade is not None and not self.face_cascade.empty()

    def detect(self, frame):
        if frame is None or self.face_cascade is None or self.face_cascade.empty():
            return "No face detected"

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(60, 60),
        )

        if len(faces) == 0:
            return "No face detected"

        x, y, w, h = faces[0]
        mouth_y = y + int(h * 0.58)
        mouth_h = max(8, int(h * 0.15))
        mouth_x = x + int(w * 0.22)
        mouth_w = max(10, int(w * 0.56))
        mouth_region = gray[mouth_y:mouth_y + mouth_h, mouth_x:mouth_x + mouth_w]

        if mouth_region.size == 0:
            return "Neutral"

        _, mouth_mask = cv2.threshold(mouth_region, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(mouth_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        mouth_area = max((cv2.contourArea(cnt) for cnt in contours), default=0.0)
        mouth_ratio = mouth_region.shape[1] / max(1, mouth_region.shape[0])

        if mouth_area > 60 and mouth_ratio >= 2.1:
            return "Smiling"
        if mouth_area > 80 and mouth_ratio <= 1.4:
            return "Sad"
        if mouth_area > 40 and mouth_ratio >= 1.7:
            return "Surprised"
        return "Neutral"


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

        self.expression_detector = SimpleExpressionDetector()

        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.camera_error = "Camera unavailable"
            self.current_expression = self.camera_error
            self.cap.release()
            self.cap = None
        else:
            self.current_expression = "Loading expression tracker..."
            self.thread = threading.Thread(target=self.update_video, daemon=True)
            self.thread.start()
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
        """Hiwalay na thread para matantiya ang ekspresyon gamit ang OpenCV-based heuristic detector."""
        while not self.stop_event.wait(1.2):
            try:
                with self.frame_lock:
                    frame = None if self.latest_frame is None else self.latest_frame.copy()
                if frame is not None:
                    self.current_expression = self.expression_detector.detect(frame)
            except Exception as error:
                self.current_expression = "No face detected"
                print(f"[emotion analysis] {type(error).__name__}: {error}")

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
        expression = self.current_expression or "No face detected"
        now = time.monotonic()
        if expression != self.last_expression or now - self.last_sent_time >= 2.0:
            self.last_expression = expression
            self.last_sent_time = now
            threading.Thread(target=self.send_expression, args=(expression,), daemon=True).start()

        with self.frame_lock:
            frame = None if self.latest_frame is None else self.latest_frame.copy()

        if frame is None:
            if self.camera_error:
                self.video_label.configure(text=self.camera_error, image=None)
            self.after(100, self.render_video_frame)
            return

        frame = cv2.flip(frame, 1)
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