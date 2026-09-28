import customtkinter as ctk
import socket
import json
from network_config import ADMIN_IP, LOG_PORT
from ui_utils import center_window


def _send_request(payload, expect_response=True):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((ADMIN_IP, LOG_PORT))
        s.sendall(payload.encode())
        if expect_response:
            response = s.recv(8192).decode()
            s.close()
            return json.loads(response) if response else None
        s.close()
    except Exception as e:
        print(f"[ERROR account_approvals network request]: {e}")
        return [] if expect_response else None


def open_account_approvals(master_teacher):
    window = ctk.CTkToplevel(master_teacher)
    window.title("Account Approvals Management")
    center_window(window, 750, 550)
    window.attributes("-topmost", True)

    teacher_id = getattr(master_teacher.master_app, "current_teacher_user_id", None)

    ctk.CTkLabel(window, text="Student Account Requests", font=("Arial", 18, "bold")).pack(pady=15)

    tabview = ctk.CTkTabview(window, width=700, height=380)
    tabview.pack(padx=20, pady=5)

    tab_pending = tabview.add("Pending")
    tab_accepted = tabview.add("Accepted")
    tab_declined = tabview.add("Declined")

    def load_data():
        for widget in tab_pending.winfo_children(): widget.destroy()
        for widget in tab_accepted.winfo_children(): widget.destroy()
        for widget in tab_declined.winfo_children(): widget.destroy()

        pending = _send_request(f"ACTION: GET_PENDING | TEACHERID: {teacher_id}") or []
        for acc in pending:
            frm = ctk.CTkFrame(tab_pending)
            frm.pack(fill="x", padx=10, pady=5)
            label_text = f"{acc['full_name']} ({acc['username']}) — {acc['course_section']}"
            ctk.CTkLabel(frm, text=label_text, font=("Arial", 12)).pack(side="left", padx=10)

            ctk.CTkButton(frm, text="Decline", fg_color="red", width=80,
                          command=lambda uid=acc["id"]: update_status(uid, "declined")).pack(side="right", padx=5)
            ctk.CTkButton(frm, text="Accept", fg_color="green", width=80,
                          command=lambda uid=acc["id"]: update_status(uid, "approved")).pack(side="right", padx=5)

        accepted = _send_request(f"ACTION: GET_TEACHER_STUDENTS | TEACHERID: {teacher_id} | STATUS: approved") or []
        for acc in accepted:
            frm = ctk.CTkFrame(tab_accepted)
            frm.pack(fill="x", padx=10, pady=5)
            ctk.CTkLabel(frm, text=f"{acc['full_name']} ({acc['username']}) (Approved)",
                         text_color="green", font=("Arial", 12)).pack(side="left", padx=10)

        declined = _send_request(f"ACTION: GET_TEACHER_STUDENTS | TEACHERID: {teacher_id} | STATUS: declined") or []
        for acc in declined:
            frm = ctk.CTkFrame(tab_declined)
            frm.pack(fill="x", padx=10, pady=5)
            ctk.CTkLabel(frm, text=f"{acc['full_name']} ({acc['username']}) (Rejected)",
                         text_color="red", font=("Arial", 12)).pack(side="left", padx=10)

    def update_status(user_id, new_status):
        action = "APPROVE_STUDENT" if new_status == "approved" else "DECLINE_STUDENT"
        _send_request(f"ACTION: {action} | USERID: {user_id}", expect_response=False)
        load_data()

    ctk.CTkButton(window, text="Refresh List", fg_color="#1f6aa5", command=load_data).pack(pady=10)

    load_data()