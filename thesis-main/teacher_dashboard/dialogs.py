import customtkinter as ctk
from .network_utils import send_command
from ui_utils import center_window
def open_text_message_dialog(master):
    dialog = ctk.CTkToplevel(master)
    dialog.title("Send Text Message to Students")
    center_window(dialog, 400, 250)
    dialog.attributes("-topmost", True)
    ctk.CTkLabel(dialog, text="I-type ang mensahe para sa lahat ng estudyante:", font=("Arial", 12, "bold")).pack(pady=15)
    msg_entry = ctk.CTkTextbox(dialog, width=350, height=100)
    msg_entry.pack(pady=5)

    def send_msg():
        message = msg_entry.get("1.0", "end-1c").strip()
        if message:
            for ip in master.student_cards.keys():
                send_command(ip, f"MSG:{message}")
            dialog.destroy()

    ctk.CTkButton(dialog, text="Broadcast Message", fg_color="green", command=send_msg).pack(pady=15)

def open_single_text_message_dialog(master, ip):
    dialog = ctk.CTkToplevel(master)
    dialog.title(f"Send Message to {ip}")
    dialog.geometry("400x250")
    dialog.attributes("-topmost", True)
    ctk.CTkLabel(dialog, text=f"I-type ang mensahe para sa PC ({ip}):", font=("Arial", 12, "bold")).pack(pady=15)
    msg_entry = ctk.CTkTextbox(dialog, width=350, height=100)
    msg_entry.pack(pady=5)

    def send_single_msg():
        message = msg_entry.get("1.0", "end-1c").strip()
        if message:
            send_command(ip, f"MSG:{message}")
            dialog.destroy()

    ctk.CTkButton(dialog, text="Send Message", fg_color="green", command=send_single_msg).pack(pady=15)

def open_website_dialog(master):
    dialog = ctk.CTkToplevel(master)
    dialog.title("Open Website on All Students")
    dialog.geometry("400x200")
    dialog.attributes("-topmost", True)
    ctk.CTkLabel(dialog, text="I-type ang URL (hal. https://www.facebook.com):", font=("Arial", 12, "bold")).pack(pady=15)
    url_entry = ctk.CTkEntry(dialog, width=350, placeholder_text="https://...")
    url_entry.pack(pady=5)

    def send_url():
        url = url_entry.get().strip()
        if url:
            for ip in master.student_cards.keys():
                send_command(ip, f"URL:{url}")
            dialog.destroy()

    ctk.CTkButton(dialog, text="Open Website", fg_color="green", command=send_url).pack(pady=15)

def open_single_website_dialog(master, ip):
    dialog = ctk.CTkToplevel(master)
    dialog.title(f"Open Website on {ip}")
    dialog.geometry("400x200")
    dialog.attributes("-topmost", True)
    ctk.CTkLabel(dialog, text=f"I-type ang URL para sa PC ({ip}):", font=("Arial", 12, "bold")).pack(pady=15)
    url_entry = ctk.CTkEntry(dialog, width=350, placeholder_text="https://...")
    url_entry.pack(pady=5)

    def send_single_url():
        url = url_entry.get().strip()
        if url:
            send_command(ip, f"URL:{url}")
            dialog.destroy()

    ctk.CTkButton(dialog, text="Open Website", fg_color="green", command=send_single_url).pack(pady=15)