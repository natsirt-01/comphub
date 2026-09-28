import socket
import threading
import subprocess
import os
import sys
import io
import struct
from PIL import Image, ImageTk
import customtkinter as ctk
from network_config import BROADCAST_PORT, LISTENER_PORT
# --- DEMO VIEWER CLASS PARA SA STUDENT ---
class DemoViewer(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Teacher Fullscreen Demo - Live")
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        
        self.video_label = ctk.CTkLabel(self, text="Naghihintay sa screen ng Teacher...", fg_color="black", text_color="white")
        self.video_label.pack(fill="both", expand=True)
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Escape>", lambda e: self.on_close())

    def update_frame(self, data):
        try:
            image = Image.open(io.BytesIO(data))

            new_w = self.winfo_width()
            new_h = self.winfo_height()
            if new_w > 10 and new_h > 10:
                image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Paggamit ng CTkImage para mawala ang HighDPI warning
            ctk_img = ctk.CTkImage(light_image=image, dark_image=image, size=(new_w if new_w > 10 else 800, new_h if new_h > 10 else 600))

            self.video_label.configure(image=ctk_img, text="")
            self.video_label.image = ctk_img
        except Exception as e:
            print(f"Error sa pag-render ng demo frame: {e}")

    def on_close(self):
        # I-withdraw muna sa halip na i-destroy para laging handa ang window
        try:
            self.withdraw()
        except:
            pass


# --- MAIN CLIENT COMMAND LISTENER ---
class ClientListener:
    def __init__(self, root_window=None):
        self.root_window = root_window
        self.is_running = True
        self.demo_window = None
        
        # 1. Simulan ang command listener sa Port 5000
        threading.Thread(target=self.start_listening, daemon=True).start()
        
        # 2. Simulan ang permanenteng broadcast listener sa Port 9996
        threading.Thread(target=self.start_broadcast_listener, daemon=True).start()

    def start_broadcast_listener(self):
        HOST = '0.0.0.0'
        PORT = BROADCAST_PORT
        
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_sock.bind((HOST, PORT))
            server_sock.listen(5)
            print(f"[CLIENT] Nakikinig ang demo broadcast sa port {PORT}...")
        except Exception as e:
            print(f"Demo viewer bind error: {e}")
            return

        while self.is_running:
            try:
                server_sock.settimeout(1.0)
                try:
                    conn, addr = server_sock.accept()
                except socket.timeout:
                    continue
                
                with conn:
                    header = conn.recv(4)
                    if not header:
                        continue
                    frame_length = struct.unpack("!I", header)[0]
                    
                    data = bytearray()
                    while len(data) < frame_length:
                        packet = conn.recv(frame_length - len(data))
                        if not packet:
                            break
                        data.extend(packet)
                    
                    if len(data) == frame_length:
                        # Kung bukas at visible ang demo window, ipasa ang frame
                        if self.demo_window and self.demo_window.winfo_exists():
                            if self.root_window:
                                self.root_window.after(0, lambda d=data: self.demo_window.update_frame(d))
            except Exception as e:
                print(f"Broadcast receive error: {e}")
                
        server_sock.close()

    def start_listening(self):
        HOST = '0.0.0.0'
        PORT = LISTENER_PORT    # Port kung saan tumatanggap ang student ng mga utos mula sa teacher
        
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server.bind((HOST, PORT))
            server.listen(5)
            print(f"[CLIENT] Nakikinig ang student command listener sa port {PORT}...")
        except Exception as e:
            print(f"[CLIENT ERROR] Hindi ma-bind ang port {PORT}: {e}")
            return

        while self.is_running:
            try:
                server.settimeout(1.0)
                try:
                    conn, addr = server.accept()
                except socket.timeout:
                    continue
                
                with conn:
                    data = conn.recv(1024)
                    if not data:
                        continue
                    
                    command = data.decode('utf-8').strip()
                    print(f"[CLIENT] Natanggap na utos: {command}")
                    
                    self.handle_command(command)
            except Exception as e:
                print(f"[CLIENT ERROR] Loop error: {e}")

    def handle_command(self, command):
        if command == "START_DEMO":
            if self.root_window:
                self.root_window.after(0, self.open_demo_viewer)
            else:
                if not self.demo_window or not self.demo_window.winfo_exists():
                    self.demo_window = DemoViewer()

        elif command == "STOP_DEMO":
            if self.demo_window and self.demo_window.winfo_exists():
                if self.root_window:
                    self.root_window.after(0, lambda: self.demo_window.withdraw())
                else:
                    self.demo_window.withdraw()

        elif command == "LOCK":
            print("[CLIENT] PC Locked")
        elif command == "UNLOCK":
            print("[CLIENT] PC Unlocked")
        elif command.startswith("MSG:"):
            msg_content = command.split(":", 1)[1]
            print(f"[CLIENT] Mensahe mula kay Teacher: {msg_content}")
        elif command.startswith("URL:"):
            url_content = command.split(":", 1)[1]
            import webbrowser
            webbrowser.open(url_content)

    def open_demo_viewer(self):
        if not self.demo_window or not self.demo_window.winfo_exists():
            self.demo_window = DemoViewer(self.root_window)
        else:
            self.demo_window.deiconify()  # Ipakita ulit kung naka-withdraw

# Para mapagana ito kapag direktang ni-run ang file na ito:
if __name__ == "__main__":
    app = ctk.CTk()
    app.title("Student Workstation")
    app.geometry("400x300")
    
    ctk.CTkLabel(app, text="Student Client Running...", font=("Arial", 14, "bold")).pack(expand=True)
    
    listener = ClientListener(app)
    
    app.mainloop()