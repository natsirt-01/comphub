import customtkinter as ctk
import json
import socket
from network_config import LOG_PORT, get_admin_ip
from ui_utils import center_window
from config import COLORS
from .date_filters import matches_date_range, parse_date_range


def _fetch_alerts(master_dashboard):
    teacher_id = getattr(master_dashboard.master_app, 'current_teacher_user_id', None)
    request = "ACTION: GET_ALERTS"
    if teacher_id:
        request += f" | TEACHERID: {teacher_id}"
    try:
        admin_ip = get_admin_ip()
        if not admin_ip:
            return []
        with socket.create_connection((admin_ip, LOG_PORT), timeout=5) as client:
            client.sendall(request.encode())
            response = client.recv(65536).decode()
        return json.loads(response) if response else []
    except (OSError, ValueError) as error:
        print(f"[ERROR fetching alerts from admin]: {error}")
        return []


def _acknowledge_alert(alert_id):
    try:
        admin_ip = get_admin_ip()
        if not admin_ip:
            return False
        with socket.create_connection((admin_ip, LOG_PORT), timeout=5) as client:
            client.sendall(f"ACTION: ACK_ALERT | ALERTID: {alert_id}".encode())
            return client.recv(64).decode() == "SUCCESS"
    except OSError as error:
        print(f"[ERROR acknowledging alert]: {error}")
        return False
def open_inbox_window(master_dashboard):
    if hasattr(master_dashboard, 'current_inbox_win') and master_dashboard.current_inbox_win:
        try:
            master_dashboard.current_inbox_win.destroy()
        except:
            pass

    inbox_win = ctk.CTkToplevel(master_dashboard)
    master_dashboard.current_inbox_win = inbox_win

    inbox_win.title("Teacher's Student Activity Inbox")
    center_window(inbox_win, 600, 450)
    inbox_win.configure(fg_color=COLORS["surface"])
    
    ctk.CTkLabel(inbox_win, text="REAL-TIME STUDENT ACTIVITY", text_color=COLORS["ink"],
                 font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

    date_row = ctk.CTkFrame(inbox_win, fg_color="transparent")
    date_row.pack(fill="x", padx=12, pady=(0, 4))
    start_entry = ctk.CTkEntry(date_row, placeholder_text="From (YYYY-MM-DD)", width=150)
    start_entry.pack(side="left", padx=(0, 6))
    end_entry = ctk.CTkEntry(date_row, placeholder_text="To (YYYY-MM-DD)", width=150)
    end_entry.pack(side="left", padx=6)
    filter_status = ctk.CTkLabel(date_row, text="", anchor="w")
    filter_status.pack(side="left", padx=8)

    frame = ctk.CTkScrollableFrame(inbox_win, width=550, height=320)
    frame.pack(pady=10, padx=10, fill="both", expand=True)

    alerts = _fetch_alerts(master_dashboard)

    def render_items():
        for widget in frame.winfo_children():
            widget.destroy()
        try:
            start, end = parse_date_range(start_entry.get(), end_entry.get())
        except ValueError as error:
            filter_status.configure(text=str(error), text_color=COLORS["danger"])
            return

        filtered_alerts = [a for a in alerts
                           if matches_date_range(a.get("timestamp"), start, end)]
        logs = list(reversed(getattr(master_dashboard, "inbox_logs_data", [])))
        filtered_logs = [log for log in logs
                         if matches_date_range(log.get("time"), start, end)]

        if filtered_alerts:
            ctk.CTkLabel(frame, text="RESTRICTED SITE ALERTS", font=("Arial", 13, "bold"), text_color=COLORS["danger"]).pack(anchor="w", pady=(5, 5))
            for a in filtered_alerts:
                display_name = a["full_name"] or a["username"]
                text = f"[{a['timestamp']}] {display_name}: {a['matched_text']} ({a['category']})"
                lbl = ctk.CTkLabel(frame, text=text, anchor="w", justify="left", font=("Arial", 12, "bold"),
                                    text_color="white", fg_color=COLORS["danger"], corner_radius=6, wraplength=520)
                lbl.pack(fill="x", padx=5, pady=3, ipady=6)

        if filtered_logs:
            for log in filtered_logs:
                log_text = f"[{log.get('time', '')}] {log.get('message', '')}"
                lbl = ctk.CTkLabel(frame, text=log_text, anchor="w", justify="left", font=("Arial", 12))
                lbl.pack(fill="x", padx=5, pady=2)

        if not filtered_alerts and not filtered_logs:
            ctk.CTkLabel(frame, text="No activity matches this date range.", text_color="gray").pack(pady=20)
        filter_status.configure(text=f"{len(filtered_alerts) + len(filtered_logs)} item(s)", text_color=COLORS["muted"])

    ctk.CTkButton(date_row, text="Apply", width=80, command=render_items).pack(side="left", padx=6)
    ctk.CTkButton(date_row, text="Clear", width=70, command=lambda: (
        start_entry.delete(0, "end"), end_entry.delete(0, "end"), render_items()
    )).pack(side="left", padx=6)

    render_items()

    def clear_inbox():
        if hasattr(master_dashboard, 'inbox_logs_data'):
            master_dashboard.inbox_logs_data.clear()
        master_dashboard.current_inbox_win = None
        inbox_win.destroy()
        open_inbox_window(master_dashboard)

    def acknowledge_alerts():
        for a in alerts:
            _acknowledge_alert(a["id"])
        master_dashboard.current_inbox_win = None
        inbox_win.destroy()
        open_inbox_window(master_dashboard)

    def on_close():
        master_dashboard.current_inbox_win = None
        inbox_win.destroy()

    inbox_win.protocol("WM_DELETE_WINDOW", on_close)

    btn_row = ctk.CTkFrame(inbox_win, fg_color="transparent")
    btn_row.pack(pady=10)
    ctk.CTkButton(btn_row, text="Clear Activity", fg_color=COLORS["danger"], hover_color=COLORS["pink_hover"], command=clear_inbox).pack(side="left", padx=5)
    if alerts:
        ctk.CTkButton(btn_row, text="Acknowledge Alerts", fg_color=COLORS["blue"], hover_color=COLORS["blue_hover"], command=acknowledge_alerts).pack(side="left", padx=5)