import customtkinter as ctk
import tkinter as tk
import threading, io
import socket
from datetime import datetime
from PIL import Image, ImageTk, ImageFile
from .network_utils import send_control_command

ImageFile.LOAD_TRUNCATED_IMAGES = True

class ScreenViewer(ctk.CTkToplevel):
    def __init__(self, student_ip, control_mode=False):
        super().__init__()
        self.student_ip = student_ip
        self.control_mode = control_mode  # False = Remote View, True = Remote Control
        
        mode_title = "Remote Control" if self.control_mode else "Remote View"
        self.title(f"{mode_title} - {student_ip}")
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        
        self.latest_image = None
        self.running = True
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        self.label = tk.Label(self, bg="black")
        self.label.grid(row=0, column=0, sticky="nsew")
        
        # --- TOP CONTROLS OVERLAY ---
        self.top_control_frame = ctk.CTkFrame(self, fg_color="#1f1f1f", corner_radius=8, border_width=1, border_color="#383838")
        self.top_control_frame.place(relx=0.97, rely=0.03, anchor="ne")

        self.btn_screenshot = ctk.CTkButton(
            self.top_control_frame, text="Screenshot", width=90, height=30,
            fg_color="#383838", hover_color="#505050", command=self.take_screenshot
        )
        self.btn_screenshot.pack(side="left", padx=6, pady=6)
       
        self.btn_exit = ctk.CTkButton(
            self.top_control_frame, text="Exit", width=70, height=30,
            fg_color="#A83232", hover_color="#C84242", command=self.on_closing
        )
        self.btn_exit.pack(side="left", padx=(0, 6), pady=6)
       
        self.bind("<Escape>", lambda e: self.on_closing())
        self.label.bind("<Configure>", self.on_resize)
        
        if self.control_mode:
            self.setup_mouse_control()
            try:
                send_control_command(self.student_ip, "START_CONTROL")
            except:
                pass

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def update_image(self, pil_image):
        """Receives a raw PIL image (not a PhotoImage) so the only PhotoImage
        conversion happens here, once, on the main GUI thread."""
        try:
            new_width = self.label.winfo_width()
            new_height = self.label.winfo_height()
            if new_width > 1 and new_height > 1:
                self.latest_image = pil_image
                resized_img = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(resized_img)
                self.label.config(image=photo)
                self.label.image = photo
        except Exception as e:
            print(f"Error sa pag-update ng image sa viewer: {e}")

    def on_resize(self, event):
        if self.latest_image:
            try:
                new_width = self.label.winfo_width()
                new_height = self.label.winfo_height()
                if new_width > 1 and new_height > 1:
                    resized_img = self.latest_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(resized_img)
                    self.label.config(image=photo)
                    self.label.image = photo
            except:
                pass

    def take_screenshot(self):
        try:
            if self.latest_image:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{self.student_ip}_{timestamp}.png"
                self.latest_image.save(filename)
                print(f"Screenshot saved as {filename}")
        except Exception as e:
            print(f"Error taking screenshot: {e}")
    def on_closing(self):
        self.running = False
        if self.control_mode:
            try:
                send_control_command(self.student_ip, "STOP_CONTROL")
            except:
                pass
        self.destroy()

    def setup_mouse_control(self):
        self.label.bind("<Motion>", self.on_mouse_move)
        self.label.bind("<B1-Motion>", self.on_mouse_move)
        self.label.bind("<Button-1>", lambda e: self.send_mouse("CLICK"))

    def on_mouse_move(self, event):
        if self.control_mode:
            send_control_command(self.student_ip, f"MOVE:{event.x}:{event.y}")

    def send_mouse(self, command):
        if self.control_mode:
            send_control_command(self.student_ip, command)