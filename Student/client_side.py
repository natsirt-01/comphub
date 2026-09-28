import datetime
import socket
import threading
import time
import customtkinter as ctk
from screen_sender import start_stream
import pygetwindow as gw
from network_config import TEACHER_IP, LOG_PORT, LISTENER_PORT



class LoginWindow(ctk.CTk):

  def __init__(self, callback):
    super().__init__()
    self.callback = callback
    self.title("Student Login")
    self.attributes("-fullscreen", True)
    self.attributes("-topmost", True)

    # UI Elements
    ctk.CTkLabel(self, text="STUDENT LOGIN", font=("Arial", 40)).pack(
        pady=100
    )
    self.user_entry = ctk.CTkEntry(
        self, placeholder_text="Username", width=300
    )
    self.user_entry.pack(pady=20)

    ctk.CTkButton(
        self, text="LOGIN", command=self.attempt_login, width=300
    ).pack(pady=20)

  def attempt_login(self):
    user = self.user_entry.get()
    if user:
      try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((TEACHER_IP, LOG_PORT))
        msg = f"ACTION: LOGIN | USER: {user} | PC: {socket.gethostname()} | TIME: {datetime.datetime.now().strftime('%H:%M:%S')}"
        s.sendall(msg.encode())
        s.close()
      except Exception as e:
        print(f"Cannot connect to Teacher for logging: {e}")

      self.withdraw()
      self.callback(user)


class ClientApp(ctk.CTk):

  def __init__(self, username):
    super().__init__()
    self.username = username
    self.title(f"Student Terminal - {username}")
    self.geometry("300x200")
    self.lock_window = None

    ctk.CTkLabel(
        self, text=f"Welcome, {username}\nSystem Online", font=("Arial", 14)
    ).pack(pady=40)

    # Simulan ang screen streaming patungo sa Teacher PC
    threading.Thread(
        target=start_stream, args=(TEACHER_IP,), daemon=True
    ).start()

    # Simulan ang background listener para sa mga utos ng Teacher
    threading.Thread(target=self.start_listener, daemon=True).start()

    # Simulan ang active window tracker para sa Teacher's Inbox (Tiyaking may ACTIVITY: prefix)
    threading.Thread(target=self.track_active_window, daemon=True).start()

  def track_active_window(self):
    last_window = ""
    while True:
      try:
        active_win = gw.getActiveWindow()
        if active_win and active_win.title:
          current_window = active_win.title
          if current_window != last_window and current_window.strip() != "":
            last_window = current_window

            # Eksaktong format na may ACTIVITY: para masalo ng network listener sa port 5001
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((TEACHER_IP, LOG_PORT))
            message = f"ACTIVITY: {socket.gethostname()} ({self.username}) - {current_window}"
            s.sendall(message.encode("utf-8"))
            s.close()
            print(f"[DEBUG STUDENT] Na-send na sa Teacher: {message}")
      except Exception as e:
        print(f"[DEBUG STUDENT] Track error: {e}")
      time.sleep(3)

  def start_listener(self):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", LISTENER_PORT))
    server.listen(5)
    print("Client Listener is running...")

    while True:
      try:
        conn, addr = server.accept()
        command = conn.recv(1024).decode().strip()

        if command == "LOCK":
          self.after(0, self.show_lock)
        elif command == "UNLOCK":
          self.after(0, self.hide_lock)
        elif command.startswith("MSG:"):
          msg_content = command.replace("MSG:", "", 1)
          self.after(0, lambda: self.show_teacher_message(msg_content))

        conn.close()
      except Exception as e:
        print(f"Listener error: {e}")

  def show_teacher_message(self, message):
    msg_win = ctk.CTkToplevel(self)
    msg_win.title("Mensahe mula sa Guro")
    msg_win.geometry("400x200")
    msg_win.attributes("-topmost", True)
    msg_win.grab_set()

    ctk.CTkLabel(
        msg_win,
        text="📢 ANUNSYO MULA SA GURO",
        font=("Arial", 14, "bold"),
        text_color="#1f6aa5",
    ).pack(pady=15)

    txt_box = ctk.CTkTextbox(msg_win, width=350, height=80)
    txt_box.insert("1.0", message)
    txt_box.configure(state="disabled")
    txt_box.pack(pady=5)

    ctk.CTkButton(msg_win, text="OK", command=msg_win.destroy).pack(pady=15)

  def show_lock(self):
    if not self.lock_window:
      self.lock_window = ctk.CTkToplevel(self)
      self.lock_window.attributes("-fullscreen", True)
      self.lock_window.attributes("-topmost", True)
      ctk.CTkLabel(
          self.lock_window,
          text="TERMINAL LOCKED",
          font=("Arial", 80, "bold"),
          text_color="red",
      ).pack(expand=True)

  def hide_lock(self):
    if self.lock_window:
      self.lock_window.destroy()
      self.lock_window = None


if __name__ == "__main__":

  def run_app(username):
    app = ClientApp(username=username)
    app.mainloop()

  login = LoginWindow(callback=run_app)
  login.mainloop()