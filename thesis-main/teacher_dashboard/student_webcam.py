import cv2
import customtkinter as ctk
from PIL import Image, ImageTk
import threading
import time
import socket
from deepface import DeepFace

class StudentWebcamOverlay(ctk.CTkToplevel):
    def __init__(self, master=None, username="Student", teacher_ip="192.168.100.71", log_port=5001):
        super().__init__(master)
        self.username = username
        self.teacher_ip = teacher_ip
        self.log_port = log_port
        self.last_sent_time = 0
        self.last_expression = ""
        self.current_expression = None
        self.frame_lock = threading.Lock()
        self.latest_frame = None
        
        self.overrideredirect(True)
        
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
        self.video_label = ctk.CTkLabel(self, text="", fg_color="#111111")
        self.video_label.grid(row=0, column=0, sticky="nsew")
        
        self.video_label.bind("<ButtonPress-1>", self.start_move)
        self.video_label.bind("<B1-Motion>", self.do_move)

        # --- FLOATING CONTROL BUTTONS ---
        self.btn_frame = ctk.CTkFrame(self, fg_color="#222222", corner_radius=4)
        self.update_buttons_layout()

        self.min_btn = ctk.CTkButton(self.btn_frame, text="_", width=20, height=18, font=("Arial", 10, "bold"), fg_color="transparent", hover_color="#444444", command=self.toggle_minimize)
        self.min_btn.pack(side="left", padx=1, pady=1)
        
        self.full_btn = ctk.CTkButton(self.btn_frame, text="□", width=20, height=18, font=("Arial", 10, "bold"), fg_color="transparent", hover_color="#444444", command=self.toggle_fullscreen)
        self.full_btn.pack(side="left", padx=1, pady=1)

        self.cap = cv2.VideoCapture(0)
        self.running = True
        
        self.thread = threading.Thread(target=self.update_video, daemon=True)
        self.thread.start()
        
        self.analysis_thread = threading.Thread(target=self.analyze_emotion_loop, daemon=True)
        self.analysis_thread.start()

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
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(1.0)
            client.connect((self.teacher_ip, self.log_port))
            
            pc_name = socket.gethostname()
            msg = f"EXPRESSION: {pc_name} - {self.username} | {expression}"
            client.sendall(msg.encode('utf-8'))
            client.close()
        except Exception as e:
            print(f"Error sa pagpadala ng expression: {e}")

    def analyze_emotion_loop(self):
        while self.running:
            try:
                with self.frame_lock:
                    frame = None if self.latest_frame is None else self.latest_frame.copy()
                if frame is not None:
                    analysis = DeepFace.analyze(frame, actions=['emotion'], enforce_detection=True, silent=True)
                    if isinstance(analysis, list) and len(analysis) > 0:
                        analysis = analysis[0]
                        raw_emotion = analysis.get('dominant_emotion', 'neutral')
                        
                        emotion_map = {
                            "happy": "Smiling",
                            "sad": "Sad",
                            "angry": "Angry",
                            "surprise": "Surprised",
                            "fear": "Fearful",
                            "disgust": "Disgusted",
                            "neutral": "Neutral"
                        }
                        self.current_expression = emotion_map.get(raw_emotion, raw_emotion.capitalize())
                    else:
                        self.current_expression = None
            except Exception as e:
                self.current_expression = None
            
            time.sleep(2.0)

    def update_video(self):
        while self.running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                break

            with self.frame_lock:
                self.latest_frame = frame.copy()
            
            frame = cv2.flip(frame, 1)
            
            current_time = time.time()
            expression = self.current_expression or "Waiting..."
            if expression != self.last_expression or (current_time - self.last_sent_time > 2.0):
                threading.Thread(target=self.send_expression, args=(expression,), daemon=True).start()
                self.last_expression = expression
                self.last_sent_time = current_time
            
            try:
                if not self.winfo_exists():
                    break
                width = self.video_label.winfo_width()
                height = self.video_label.winfo_height()
                
                if width > 10 and height > 10:
                    frame = cv2.resize(frame, (width, height))
                
                if self.current_expression:
                    cv2.putText(frame, f"Emotion: {self.current_expression}", (15, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
                else:
                    cv2.putText(frame, f"Emotion: No face detected", (15, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
                
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb_frame)
                imgtk = ImageTk.PhotoImage(image=img)
                
                self.video_label.configure(image=imgtk)
                self.video_label.image = imgtk
            except Exception:
                break
                
            time.sleep(0.03)
                
    def close_camera(self):
        self.running = False
        if self.cap.isOpened():
            self.cap.release()
        try:
            self.destroy()
        except:
            pass