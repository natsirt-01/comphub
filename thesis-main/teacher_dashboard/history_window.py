import customtkinter as ctk
import tkinter.ttk as ttk
import socket
import json
from network_config import LOG_PORT, get_admin_ip
from ui_utils import center_window
from config import COLORS
from .date_filters import matches_date_range, parse_date_range


def _fetch_history_from_admin():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        admin_ip = get_admin_ip()
        if not admin_ip:
            return []
        s.connect((admin_ip, LOG_PORT))
        s.sendall("ACTION: GET_ALL_HISTORY".encode())
        response = s.recv(65536).decode()
        s.close()
        return json.loads(response) if response else []
    except Exception as e:
        print(f"[ERROR fetching history from admin]: {e}")
        return []


def open_history_window(master, login_history_data=None):
    """login_history_data param kept for compatibility with the existing
    call site, but is no longer used — real history now comes from Admin's
    database over the network, same as Admin's own Logs & History tab."""
    history_win = ctk.CTkToplevel(master)
    history_win.title("Student Login & Logout History")
    center_window(history_win, 750, 450)
    history_win.configure(fg_color=COLORS["surface"])

    lbl_title = ctk.CTkLabel(history_win, text="LAB USER SESSION HISTORY", text_color=COLORS["ink"], font=ctk.CTkFont(size=16, weight="bold"))
    lbl_title.pack(pady=10)

    table_frame = ctk.CTkFrame(history_win)
    table_frame.pack(fill="both", expand=True, padx=20, pady=10)

    columns = ("Name", "Role", "Lab", "Login Time", "Logout Time", "Duration")
    tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=12)

    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=110, anchor="center")

    tree.pack(side="left", fill="both", expand=True)

    date_row = ctk.CTkFrame(history_win, fg_color="transparent")
    date_row.pack(fill="x", padx=20, pady=(0, 5))
    start_entry = ctk.CTkEntry(date_row, placeholder_text="From (YYYY-MM-DD)", width=150)
    start_entry.pack(side="left", padx=(0, 6))
    end_entry = ctk.CTkEntry(date_row, placeholder_text="To (YYYY-MM-DD)", width=150)
    end_entry.pack(side="left", padx=6)
    status = ctk.CTkLabel(date_row, text="", anchor="w")
    status.pack(side="left", padx=8)

    def load_data():
        history = _fetch_history_from_admin()
        try:
            start, end = parse_date_range(start_entry.get(), end_entry.get())
        except ValueError as error:
            status.configure(text=str(error), text_color=COLORS["danger"])
            return
        history = [item for item in history
                   if matches_date_range(item.get("login_time"), start, end)]
        for row in tree.get_children():
            tree.delete(row)

        for item in history:
            display_name = item.get("full_name") or item.get("username")
            duration = item.get("duration_secs") or 0
            mins, secs = divmod(duration, 60)
            hrs, mins = divmod(mins, 60)
            duration_str = f"{hrs}h {mins}m {secs}s" if item.get("logout_time") else "Active"

            tree.insert("", "end", values=(
                display_name,
                item.get("role", ""),
                item.get("lab_name") or "N/A",
                item.get("login_time", ""),
                item.get("logout_time") or "Still active",
                duration_str,
            ))
        status.configure(text=f"{len(history)} session(s)", text_color=COLORS["muted"])

    ctk.CTkButton(date_row, text="Apply dates", width=100, command=load_data).pack(side="left", padx=6)
    ctk.CTkButton(date_row, text="Clear", width=70, command=lambda: (
        start_entry.delete(0, "end"), end_entry.delete(0, "end"), load_data()
    )).pack(side="left", padx=6)
    ctk.CTkButton(history_win, text="Refresh", width=140, fg_color=COLORS["blue"],
                  hover_color=COLORS["blue_hover"], command=load_data).pack(pady=10)

    load_data()