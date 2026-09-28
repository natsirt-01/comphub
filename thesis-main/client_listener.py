import socket
import threading
import customtkinter as ctk

class LockScreen(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self.title("Terminal Locked")
        ctk.CTkLabel(self, text="TERMINAL LOCKED", font=("Arial", 60, "bold"), text_color="red").pack(expand=True)
        ctk.CTkLabel(self, text="Naghihintay ng pahintulot mula sa Admin...", font=("Arial", 20)).pack(pady=20)

class ClientApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Student System")
        self.geometry("300x200")
        self.lock_window = None
        
        # Simulan ang server sa background
        threading.Thread(target=self.start_server, daemon=True).start()

    def start_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("0.0.0.0", 5000))
        server.listen(5)
        print("Client Listener is running...")
        
        while True:
            conn, addr = server.accept()
            command = conn.recv(1024).decode()
            
            # Gamitin ang .after() para ipasa ang utos sa main UI thread
            if command == "LOCK":
                self.after(0, self.show_lock)
            elif command == "UNLOCK":
                self.after(0, self.hide_lock)
            conn.close()

    def show_lock(self):
        if self.lock_window is None:
            self.lock_window = LockScreen(self)

    def hide_lock(self):
        if self.lock_window:
            self.lock_window.destroy()
            self.lock_window = None

if __name__ == "__main__":
    app = ClientApp()
    app.mainloop()