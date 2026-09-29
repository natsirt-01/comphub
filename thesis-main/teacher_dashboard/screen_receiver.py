import customtkinter as ctk
import tkinter as tk
import threading, io
import socket
import queue
from datetime import datetime
from PIL import Image, ImageTk, ImageFile
from network_config import CONTROL_PORT
from config import COLORS

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
        self.pending_image = None
        self.pending_image_lock = threading.Lock()
        self.frame_callback_pending = False
        self.running = True
        self.control_commands = queue.Queue(maxsize=32)
        self.pending_mouse_position = None
        self.mouse_update_after = None
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        self.label = tk.Label(self, bg="black")
        self.label.grid(row=0, column=0, sticky="nsew")
        
        # --- TOP CONTROLS OVERLAY ---
        self.top_control_frame = ctk.CTkFrame(self, fg_color=COLORS["navy"], corner_radius=8, border_width=1, border_color=COLORS["navy_panel"])
        self.top_control_frame.place(relx=0.97, rely=0.03, anchor="ne")

        self.btn_screenshot = ctk.CTkButton(
            self.top_control_frame, text="Screenshot", width=90, height=30,
            fg_color=COLORS["blue"], hover_color=COLORS["blue_hover"], command=self.take_screenshot
        )
        self.btn_screenshot.pack(side="left", padx=6, pady=6)
       
        self.btn_exit = ctk.CTkButton(
            self.top_control_frame, text="Exit", width=70, height=30,
            fg_color=COLORS["pink"], hover_color=COLORS["pink_hover"], command=self.on_closing
        )
        self.btn_exit.pack(side="left", padx=(0, 6), pady=6)
       
        self.bind("<Escape>", lambda e: self.on_closing())
        self.label.bind("<Configure>", self.on_resize)
        
        if self.control_mode:
            self.setup_mouse_control()
            threading.Thread(target=self._control_sender_loop, daemon=True).start()
            self._queue_control_command("START_CONTROL")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def queue_image(self, pil_image):
        if not self.running:
            return
        with self.pending_image_lock:
            self.pending_image = pil_image
            if self.frame_callback_pending:
                return
            self.frame_callback_pending = True
        try:
            self.after(0, self._render_pending_image)
        except tk.TclError:
            with self.pending_image_lock:
                self.pending_image = None
                self.frame_callback_pending = False

    def _render_pending_image(self):
        with self.pending_image_lock:
            pil_image = self.pending_image
            self.pending_image = None
            self.frame_callback_pending = False
        if self.running and pil_image is not None:
            self.update_image(pil_image)

    def update_image(self, pil_image):
        try:
            new_width = self.label.winfo_width()
            new_height = self.label.winfo_height()
            if new_width > 1 and new_height > 1:
                self.latest_image = pil_image
                resized_img = pil_image.resize((new_width, new_height), Image.Resampling.BILINEAR)
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
                    resized_img = self.latest_image.resize((new_width, new_height), Image.Resampling.BILINEAR)
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
        if self.control_mode:
            self._queue_control_command("STOP_CONTROL")
        self.running = False
        self.destroy()

    def setup_mouse_control(self):
        self.label.bind("<Motion>", self.on_mouse_move)
        self.label.bind("<B1-Motion>", self.on_mouse_move)
        self.label.bind("<Button-1>", lambda e: self.send_mouse("CLICK"))

    def on_mouse_move(self, event):
        if not self.control_mode:
            return
        self.pending_mouse_position = (event.x, event.y)
        if self.mouse_update_after is None:
            self.mouse_update_after = self.after(16, self._flush_mouse_position)

    def _flush_mouse_position(self):
        self.mouse_update_after = None
        if not self.control_mode or not self.running or self.pending_mouse_position is None:
            return
        x, y = self.pending_mouse_position
        self.pending_mouse_position = None
        view_width = max(1, self.label.winfo_width())
        view_height = max(1, self.label.winfo_height())
        x = max(0, min(x, view_width - 1))
        y = max(0, min(y, view_height - 1))
        self._queue_control_command(f"MOVE:{x}:{y}:{view_width}:{view_height}")

    def _queue_control_command(self, command):
        try:
            self.control_commands.put_nowait(command)
        except queue.Full:
            if command.startswith("MOVE:"):
                return
            try:
                self.control_commands.get_nowait()
                self.control_commands.put_nowait(command)
            except queue.Empty:
                pass
            except queue.Full:
                pass

    def _control_sender_loop(self):
        control_socket = None
        while self.running or not self.control_commands.empty():
            try:
                command = self.control_commands.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if control_socket is None:
                    control_socket = socket.create_connection(
                        (self.student_ip, CONTROL_PORT), timeout=1.0
                    )
                    control_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    control_socket.settimeout(None)
                    if command != "START_CONTROL":
                        control_socket.sendall(b"START_CONTROL\n")
                control_socket.sendall(f"{command}\n".encode())
            except OSError:
                if control_socket is not None:
                    control_socket.close()
                control_socket = None
            finally:
                self.control_commands.task_done()
        if control_socket is not None:
            control_socket.close()

    def send_mouse(self, command):
        if self.control_mode:
            send_control_command(self.student_ip, command)