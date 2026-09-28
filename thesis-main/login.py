import customtkinter as ctk
import json
import socket
import threading
import datetime
import struct
import time
import cv2
import numpy as np
import pyautogui
from config import apply_theme, apply_widget_theme, COLORS, maximize_window
from teacher_dashboard.teacher_dash import TeacherDashboard
from teacher_dashboard.network_listeners import handle_student_expression
from teacher_dashboard.network_listeners import start_persistent_stream_listeners, update_student_card_name
from admin_dashboard.admin_dash import AdminDashboard
from database import db
apply_theme()
db.init_db()
db.seed_defaults()
from teacher_dashboard.teacher_screen_sender import start_teacher_streaming, stop_teacher_streaming
from ui_utils import center_window
from network_config import discover_admin_ip

class LabSelectionDialog(ctk.CTkToplevel):
    def __init__(self, master, on_selected):
        super().__init__(master)
        self.title("Select Computer Lab")
        center_window(self, 350, 220)
        self.attributes("-topmost", True)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        ctk.CTkLabel(self, text="Which lab are you in today?", font=("Arial", 16, "bold")).pack(pady=20)

        labs = db.get_all_labs()
        self.lab_map = {lab["name"]: lab["id"] for lab in labs}
        self.lab_dropdown = ctk.CTkOptionMenu(self, values=list(self.lab_map.keys()) or ["No labs found"], width=250)
        self.lab_dropdown.pack(pady=10)
        if self.lab_map:
            self.lab_dropdown.set(list(self.lab_map.keys())[0])

        ctk.CTkButton(self, text="Confirm", command=lambda: self._confirm(on_selected)).pack(pady=20)

    def _confirm(self, on_selected):
        selected = self.lab_dropdown.get()
        lab_id = self.lab_map.get(selected)
        if lab_id:
            self.destroy()
            on_selected(lab_id)


class LoginApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        apply_widget_theme(self)
        db.init_db()
        db.seed_defaults()
        
        self.title("CompHub Login - Teacher/Admin")
        self.configure(fg_color=COLORS["navy"])
        center_window(self, 760, 560)
        maximize_window(self)
        self.USERS = {
            "student": {"password": "student123", "role": "Student"},
            "teacher": {"password": "teacher123", "role": "Teacher"},
            "admin": {"password": "admin123", "role": "Admin"}
        }
        
        self.all_logs = [] 
        self.active_sessions = {} 
        self.active_broadcast = False
        self.broadcast_socket = None
        self.active_teacher_dashboard = None  # <--- Reference para sa student expressions
        self.login_history_data = []
        self.online_teachers = {}  # lab_id -> {"teacher_id": ...}  (populated on Admin's machine via network)
        self.teacher_ips_by_lab = {}
        self.is_admin_node = False

    
        start_persistent_stream_listeners(self)
        
        # Simulan ang background log listener at broadcast server
        threading.Thread(target=self.start_log_listener, daemon=True).start()
        threading.Thread(target=self.broadcast_stream_server, daemon=True).start()
        threading.Thread(target=self.start_lan_discovery_listener, daemon=True).start()
        
        header = ctk.CTkFrame(self, fg_color=COLORS["navy_panel"], corner_radius=0, height=82)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="COMPHUB", text_color=COLORS["white"],
             font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=34, pady=(13, 0))
        ctk.CTkLabel(header, text="Teacher and administrator workspace", text_color="#e6d9f1",
             font=ctk.CTkFont(size=12)).pack(anchor="w", padx=36, pady=(0, 10))

        login_panel = ctk.CTkFrame(self, width=440, height=390, corner_radius=14,
                       fg_color=COLORS["white"], border_width=1,
                       border_color=COLORS["surface_alt"])
        login_panel.pack(expand=True, padx=24, pady=(24, 42))
        login_panel.pack_propagate(False)
        ctk.CTkLabel(login_panel, text="SIGN IN", text_color=COLORS["navy"],
             font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", padx=38, pady=(32, 4))
        ctk.CTkLabel(login_panel, text="Access the lab workspace", text_color=COLORS["muted"],
             font=ctk.CTkFont(size=12)).pack(anchor="w", padx=40, pady=(0, 18))

        self.user_entry = ctk.CTkEntry(login_panel, placeholder_text="Username", height=42)
        self.user_entry.pack(pady=7, padx=38, fill="x")
        self.pass_entry = ctk.CTkEntry(login_panel, placeholder_text="Password", show="*", height=42)
        self.pass_entry.pack(pady=7, padx=38, fill="x")
        self.btn_login = ctk.CTkButton(login_panel, text="Sign In", height=42, fg_color=COLORS["blue"],
                           hover_color=COLORS["blue_hover"], command=self.check_login)
        self.btn_login.pack(pady=(18, 8), padx=38, fill="x")
        self.error_label = ctk.CTkLabel(
            login_panel, text="", text_color=COLORS["danger"], wraplength=340,
            justify="center",
        )
        self.error_label.pack(pady=(0, 4))

    def start_log_listener(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", 5001))
        server.listen(5)
        print("==========================================")
        print("[DEBUG] Log & Command listener ay BUKAS sa port 5001")
        print("==========================================")
        while True:
            try:
                conn, addr = server.accept()
                data = conn.recv(2048).decode('utf-8', errors='ignore').strip()
                
                if "ACTION: LOGIN_CHECK" in data:
                    self.handle_login_check(conn, data)
                elif data == "ACTION: DISCOVER_ADMIN":
                    conn.sendall(b"COMPHUB_ADMIN")
                    conn.close()
                elif "ACTION: GET_TEACHERS" in data:
                    self.handle_get_teachers(conn)
                elif "ACTION: GET_LABS" in data:
                    self.handle_get_labs(conn)
                elif "ACTION: SET_LAB" in data:
                    self.handle_set_lab(conn, data)
                elif "ACTION: GET_HISTORY" in data:
                    self.handle_get_history(conn, data)
                elif "ACTION: CHANGE_PWD" in data:
                    self.handle_change_password(conn, data)
                elif "ACTION: UPDATE_PROFILE" in data:
                    self.handle_update_profile(conn, data)
                elif "ACTION: REGISTER" in data:
                    self.process_register(data)
                    conn.close()
                elif "ACTION: LOGIN" in data:
                    self.handle_student_login_event(data, addr)
                    conn.close()
                elif "ACTION: LOGOUT" in data:
                    self.handle_student_logout_event(data)
                elif "ACTION: TEACHER_ONLINE" in data:
                    self.handle_teacher_online(data, addr[0])
                    conn.close()
                elif "ACTION: TEACHER_OFFLINE" in data:
                    self.handle_teacher_offline(data)
                    conn.close()
                elif "ACTION: GET_USER_INFO" in data:
                    self.handle_get_user_info(conn, data)  
                elif "ACTION: STAFF_LOGIN_CHECK" in data:
                    self.handle_staff_login_check(conn, data)      
                elif "ACTION: GET_PENDING" in data:
                    self.handle_get_pending(conn, data)
                elif "ACTION: APPROVE_STUDENT" in data:
                    self.handle_approve_student(conn, data)
                elif "ACTION: DECLINE_STUDENT" in data:
                    self.handle_decline_student(conn, data)
                elif "ACTION: GET_TEACHER_STUDENTS" in data:
                    self.handle_get_teacher_students(conn, data)
                elif "ACTION: GET_ALL_HISTORY" in data:
                    self.handle_get_all_history(conn)
                    conn.close()
                elif "ACTION: GET_BLOCKLIST" in data:
                    self.handle_get_blocklist(conn)
                elif "ACTION: GET_ALERTS" in data:
                    self.handle_get_alerts(conn, data)
                elif "ACTION: ACK_ALERT" in data:
                    self.handle_ack_alert(conn, data)
                elif "ACTION: SITE_ALERT" in data:
                    self.handle_site_alert(data)
                    conn.close()

                elif "EXPRESSION:" in data:
                    expr_content = data.replace("EXPRESSION:", "").strip()
                    print(f"[STUDENT EXPRESSION] mula {addr[0]}: {expr_content}")
                    
                    if self.active_teacher_dashboard:
                        if not hasattr(self.active_teacher_dashboard, 'inbox_logs_data'):
                            self.active_teacher_dashboard.inbox_logs_data = []
                            
                        new_log = {
                            "time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            "message": f"[{addr[0]}] Expression: {expr_content}"
                        }
                        self.active_teacher_dashboard.inbox_logs_data.append(new_log)
                        
                        # I-refresh ang UI ng Inbox at Student Card nang sabay
                        self.active_teacher_dashboard.after(
                            0, lambda: self.active_teacher_dashboard.refresh_inbox_ui()
                        )
                        self.active_teacher_dashboard.after(
                            0, lambda e=expr_content, ip=addr[0]: handle_student_expression(self.active_teacher_dashboard, e, ip)
                        )
                    conn.close()
                else:
                    self.process_log(data)
                    conn.close()
            except: 
                break

    def start_lan_discovery_listener(self):
        discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            discovery_socket.bind(("0.0.0.0", 37020))
            discovery_socket.settimeout(1.0)
        except OSError as error:
            print(f"[LAN discovery] Cannot listen on UDP 37020: {error}")
            return

        while True:
            try:
                request, address = discovery_socket.recvfrom(256)
                parts = request.decode("ascii", errors="ignore").split("|")
                if len(parts) == 3 and parts[0:2] == ["COMPHUB_DISCOVER", "ADMIN"]:
                    discovery_socket.sendto(
                        f"COMPHUB_SERVICE|ADMIN|{parts[2]}".encode("ascii"), address
                    )
            except socket.timeout:
                continue
            except OSError as error:
                if getattr(error, "winerror", None) == 10054 or error.errno == 10054:
                    continue
                print(f"[LAN discovery] Listener stopped: {error}")
                break

    def handle_teacher_online(self, data, teacher_ip=""):
        try:
            teacher_id_str = lab_id_str = pc_name = ""
            for part in data.split("|"):
                if "TEACHERID:" in part:
                    teacher_id_str = part.split("TEACHERID:")[1].strip()
                elif "LABID:" in part:
                    lab_id_str = part.split("LABID:")[1].strip()
                elif "PCNAME:" in part:
                    pc_name = part.split("PCNAME:")[1].strip()

            if teacher_id_str.isdigit() and lab_id_str.isdigit():
                teacher_id = int(teacher_id_str)
                lab_id = int(lab_id_str)

                # Admin's own database is the single source of truth: create the
                # real session row HERE, not on the teacher's own machine.
                for old_lab_id, entry in list(self.online_teachers.items()):
                    if entry.get("teacher_id") == teacher_id:
                        if entry.get("session_id"):
                            db.end_session(entry["session_id"])
                        self.online_teachers.pop(old_lab_id, None)
                        self.teacher_ips_by_lab.pop(old_lab_id, None)
                session_id = db.start_session(teacher_id, lab_id=lab_id, pc_name=pc_name, ip_address=teacher_ip)
                entry = {
                    "teacher_id": teacher_id,
                    "session_id": session_id,
                    "ip_address": teacher_ip,
                }
                self.online_teachers[lab_id] = entry
                self.teacher_ips_by_lab[lab_id] = teacher_ip
                print(f"[DEBUG] Teacher {teacher_id} is now ONLINE in lab {lab_id} (session {session_id})")
        except Exception as e:
            print(f"[ERROR handle_teacher_online]: {e}")

    def handle_teacher_offline(self, data):
        try:
            lab_id_str = ""
            for part in data.split("|"):
                if "LABID:" in part:
                    lab_id_str = part.split("LABID:")[1].strip()
            if lab_id_str.isdigit():
                entry = self.online_teachers.pop(int(lab_id_str), None)
                if entry and entry.get("session_id"):
                    db.end_session(entry["session_id"])
                self.teacher_ips_by_lab.pop(int(lab_id_str), None)
                print(f"[DEBUG] Teacher OFFLINE for lab {lab_id_str}")
        except Exception as e:
            print(f"[ERROR handle_teacher_offline]: {e}")

    def _notify_admin_teacher_online(self, teacher_id, lab_id):
        try:
            admin_ip = discover_admin_ip(timeout=3)
            if not admin_ip:
                raise OSError("Admin server was not discovered on this LAN.")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((admin_ip, 5001))
            pc_name = socket.gethostname()
            s.sendall(f"ACTION: TEACHER_ONLINE | TEACHERID: {teacher_id} | LABID: {lab_id} | PCNAME: {pc_name}".encode())
            s.close()
        except Exception as e:
            print(f"[ERROR notifying admin teacher online]: {e}")

    def _notify_admin_teacher_offline(self, lab_id):
        try:
            admin_ip = discover_admin_ip(timeout=3)
            if not admin_ip:
                raise OSError("Admin server was not discovered on this LAN.")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((admin_ip, 5001))
            s.sendall(f"ACTION: TEACHER_OFFLINE | LABID: {lab_id}".encode())
            s.close()
        except Exception as e:
            print(f"[ERROR notifying admin teacher offline]: {e}")

    def handle_staff_login_check(self, conn, data):
        try:
            username = password = ""
            for part in data.split("|"):
                if "USER:" in part:
                    username = part.split("USER:")[1].strip()
                elif "PWD:" in part:
                    password = part.split("PWD:")[1].strip()

            user = db.verify_password(username, password)
            if user and user["role"] in ("teacher", "admin"):
                payload = {
                    "success": True,
                    "id": user["id"],
                    "role": user["role"],
                    "full_name": user["full_name"] or user["username"],
                }
            else:
                payload = {"success": False}
            conn.send(json.dumps(payload).encode())
        except Exception as e:
            print(f"[ERROR handle_staff_login_check]: {e}")
            conn.send(json.dumps({"success": False}).encode())
        finally:
            conn.close()

    def handle_login_check(self, conn, data):
        try:
            parts = data.split("|")
            username = ""
            password = ""
            teacher_id_str = ""
            lab_id_str = ""
            for part in parts:
                if "USER:" in part:
                    username = part.split("USER:")[1].strip()
                elif "PWD:" in part:
                    password = part.split("PWD:")[1].strip()
                elif "TEACHERID:" in part:
                    teacher_id_str = part.split("TEACHERID:")[1].strip()
                elif "LABID:" in part:
                    lab_id_str = part.split("LABID:")[1].strip()

            user = db.verify_password(username, password)
            if not user or user["role"] != "student":
                conn.send("FAILED".encode())
                return

            selected_teacher_id = int(teacher_id_str) if teacher_id_str.isdigit() else None
            selected_lab_id = int(lab_id_str) if lab_id_str.isdigit() else None

            online_entry = self.online_teachers.get(selected_lab_id)

            if not online_entry:
                conn.send("TEACHER_OFFLINE".encode())
                return

            if online_entry["teacher_id"] != selected_teacher_id:
                conn.send("LAB_MISMATCH".encode())
                return

            db.set_user_lab(user["id"], selected_lab_id)
            conn.send("SUCCESS".encode())
        except Exception as e:
            print(f"[ERROR sa login check]: {e}")
            conn.send("FAILED".encode())
        finally:
            conn.close()

    def handle_get_blocklist(self, conn):
        try:
            blocklist = db.get_blocklist()
            conn.send(json.dumps(blocklist).encode())
        except Exception as e:
            print(f"[ERROR sa get_blocklist]: {e}")
            conn.send(json.dumps([]).encode())
        finally:
            conn.close()

    def handle_get_alerts(self, conn, data):
        try:
            teacher_id = None
            active_only = "ACTIVE: 1" in data
            for part in data.split("|"):
                if "TEACHERID:" in part:
                    value = part.split("TEACHERID:", 1)[1].strip()
                    teacher_id = int(value) if value.isdigit() else None
            alerts = (db.get_alerts_for_teacher(teacher_id, active_only=active_only)
                      if teacher_id else db.get_alerts_for_admin(active_only=active_only))
            conn.send(json.dumps(alerts).encode())
        except Exception as e:
            print(f"[ERROR sa get_alerts]: {e}")
            conn.send(json.dumps([]).encode())
        finally:
            conn.close()

    def handle_ack_alert(self, conn, data):
        try:
            alert_id = None
            for part in data.split("|"):
                if "ALERTID:" in part:
                    value = part.split("ALERTID:", 1)[1].strip()
                    alert_id = int(value) if value.isdigit() else None
            if alert_id is not None:
                db.acknowledge_alert(alert_id)
                conn.send(b"SUCCESS")
            else:
                conn.send(b"FAILED")
        except Exception as e:
            print(f"[ERROR sa ack_alert]: {e}")
            conn.send(b"FAILED")
        finally:
            conn.close()

    def handle_site_alert(self, data):
        try:
            username = text = category = ""
            status = "OPEN"
            for part in data.split("|"):
                if "USER:" in part:
                    username = part.split("USER:")[1].strip()
                elif "TEXT:" in part:
                    text = part.split("TEXT:")[1].strip()
                elif "CATEGORY:" in part:
                    category = part.split("CATEGORY:")[1].strip()
                elif "STATUS:" in part:
                    status = part.split("STATUS:")[1].strip().upper()

            user = db.get_user_by_username(username)
            if not user:
                return
            if status == "CLOSED":
                db.close_active_site_alert(user["id"])
                return
            session_id = db.get_active_session_id(user["id"])
            db.log_site_alert(user["id"], session_id, text, category, active=True)

            dashboard = self.active_teacher_dashboard
            if dashboard and hasattr(dashboard, 'refresh_inbox_ui'):
                self.after(0, dashboard.refresh_inbox_ui)
        except Exception as e:
            print(f"[ERROR sa site_alert]: {e}")

    def handle_change_password(self, conn, data):
        try:
            parts = data.split("|")
            username = old_pwd = new_pwd = ""
            for part in parts:
                if "USER:" in part:
                    username = part.split("USER:")[1].strip()
                elif "OLDPWD:" in part:
                    old_pwd = part.split("OLDPWD:")[1].strip()
                elif "NEWPWD:" in part:
                    new_pwd = part.split("NEWPWD:")[1].strip()

            ok, msg = db.change_password(username, old_pwd, new_pwd)
            conn.send(("SUCCESS" if ok else "FAILED").encode())
        except Exception as e:
            print(f"[ERROR sa change_password]: {e}")
            conn.send("FAILED".encode())
        finally:
            conn.close()


    def handle_update_profile(self, conn, data):
        try:
            fields = {}
            for part in data.split("|"):
                if ":" in part:
                    key, value = part.split(":", 1)
                    fields[key.strip()] = value.strip()
            updated = db.update_own_full_name(
                fields.get("USER", ""), fields.get("PWD", ""), fields.get("FULLNAME", "")
            )
            conn.send(b"SUCCESS" if updated else b"FAILED")
        except Exception as e:
            print(f"[ERROR sa update_profile]: {e}")
            conn.send(b"FAILED")
        finally:
            conn.close()


    def handle_student_login_event(self, data, addr):
        try:
            username = ""
            for part in data.split("|"):
                if "USER:" in part:
                    username = part.split("USER:")[1].strip()

            user = db.get_user_by_username(username)
            if user:
                # A prior crash may have left a live flag behind; it must not
                # color a newly logged-in student's card red.
                db.close_active_site_alert(user["id"])
                existing_session = db.get_active_session_id(user["id"])
                if existing_session:
                    self.active_sessions[username] = existing_session
                    return
                session_id = db.start_session(
                    user["id"], lab_id=user.get("lab_id"),
                    pc_name=addr[0], ip_address=addr[0]
                )
                self.active_sessions[username] = session_id
        except Exception as e:
            print(f"[ERROR sa login event]: {e}")

    def handle_student_logout_event(self, data):
        try:
            username = ""
            for part in data.split("|"):
                if "USER:" in part:
                    username = part.split("USER:")[1].strip()

            session_id = self.active_sessions.pop(username, None)
            if session_id is None:
                user = db.get_user_by_username(username)
                if user:
                    session_id = db.get_active_session_id(user["id"])
            if session_id:
                db.end_session(session_id)
            user = db.get_user_by_username(username)
            if user:
                db.close_active_site_alert(user["id"])
        except Exception as e:
            print(f"[ERROR sa logout event]: {e}")


    def handle_get_all_history(self, conn):
        try:
            history = db.get_all_sessions_history()
            conn.send(json.dumps(history).encode())
        except Exception as e:
            print(f"[ERROR handle_get_all_history]: {e}")
            conn.send(json.dumps([]).encode())
        finally:
            conn.close()        

    def handle_get_history(self, conn, data):
        try:
            username = ""
            for part in data.split("|"):
                if "USER:" in part:
                    username = part.split("USER:")[1].strip()

            user = db.get_user_by_username(username)
            if not user:
                conn.send(json.dumps([]).encode())
                return

            sessions = db.get_history_for_user(user["id"])
            teachers = db.get_teachers_for_student(user["id"])
            teacher_names = ", ".join(t["full_name"] or t["username"] for t in teachers) or "N/A"

            payload = [
                {
                    "login_time": s["login_time"],
                    "logout_time": s["logout_time"] or "Still active",
                    "duration_secs": s["duration_secs"] or 0,
                    "lab_name": s["lab_name"] or "N/A",
                    "teacher": teacher_names,
                }
                for s in sessions
            ]
            conn.send(json.dumps(payload).encode())
        except Exception as e:
            print(f"[ERROR sa get_history]: {e}")
            conn.send(json.dumps([]).encode())
        finally:
            conn.close()

    def handle_get_pending(self, conn, data):
        try:
            teacher_id_str = ""
            for part in data.split("|"):
                if "TEACHERID:" in part:
                    teacher_id_str = part.split("TEACHERID:")[1].strip()
            teacher_id = int(teacher_id_str) if teacher_id_str.isdigit() else None
            pending = db.get_pending_registrations(teacher_id)
            conn.send(json.dumps(pending).encode())
        except Exception as e:
            print(f"[ERROR handle_get_pending]: {e}")
            conn.send(json.dumps([]).encode())
        finally:
            conn.close()

    def handle_approve_student(self, conn, data):
        try:
            user_id_str = ""
            for part in data.split("|"):
                if "USERID:" in part:
                    user_id_str = part.split("USERID:")[1].strip()
            if user_id_str.isdigit():
                db.approve_registration(int(user_id_str))
            conn.send("SUCCESS".encode())
        except Exception as e:
            print(f"[ERROR handle_approve_student]: {e}")
            conn.send("FAILED".encode())
        finally:
            conn.close()

    def handle_decline_student(self, conn, data):
        try:
            user_id_str = ""
            for part in data.split("|"):
                if "USERID:" in part:
                    user_id_str = part.split("USERID:")[1].strip()
            if user_id_str.isdigit():
                db.decline_registration(int(user_id_str))
            conn.send("SUCCESS".encode())
        except Exception as e:
            print(f"[ERROR handle_decline_student]: {e}")
            conn.send("FAILED".encode())
        finally:
            conn.close()

    def handle_get_teacher_students(self, conn, data):
        try:
            teacher_id_str = status = ""
            for part in data.split("|"):
                if "TEACHERID:" in part:
                    teacher_id_str = part.split("TEACHERID:")[1].strip()
                elif "STATUS:" in part:
                    status = part.split("STATUS:")[1].strip()
            teacher_id = int(teacher_id_str) if teacher_id_str.isdigit() else None
            with db.get_conn() as conn2:
                rows = conn2.execute(
                    """SELECT u.* FROM users u
                    JOIN teacher_student ts ON ts.student_id = u.id
                    WHERE u.role='student' AND u.status = ? AND ts.teacher_id = ?""",
                    (status, teacher_id),
                ).fetchall()
                result = [dict(r) for r in rows]
            conn.send(json.dumps(result).encode())
        except Exception as e:
            print(f"[ERROR handle_get_teacher_students]: {e}")
            conn.send(json.dumps([]).encode())
        finally:
            conn.close()


    def handle_get_user_info(self, conn, data):
        try:
            username = ""
            for part in data.split("|"):
                if "USER:" in part:
                    username = part.split("USER:")[1].strip()
            user = db.get_user_by_username(username)
            if user:
                payload = {"id": user["id"], "full_name": user["full_name"], "lab_id": user["lab_id"], "role": user["role"]}
                conn.send(json.dumps(payload).encode())
            else:
                conn.send(json.dumps(None).encode())
        except Exception as e:
            print(f"[ERROR handle_get_user_info]: {e}")
            conn.send(json.dumps(None).encode())
        finally:
            conn.close()

    def handle_get_teachers(self, conn):
        try:
            teachers = db.get_all_teachers()
            online_by_teacher = {
                entry["teacher_id"]: {
                    "ip_address": entry.get("ip_address"),
                    "lab_id": lab_id,
                }
                for lab_id, entry in self.online_teachers.items()
            }
            payload = [
                {
                    "id": t["id"],
                    "username": t["username"],
                    "full_name": t["full_name"] or t["username"],
                    "ip_address": online_by_teacher.get(t["id"], {}).get("ip_address"),
                    "lab_id": online_by_teacher.get(t["id"], {}).get("lab_id"),
                }
                for t in teachers
            ]
            conn.send(json.dumps(payload).encode())
        except Exception as e:
            print(f"[ERROR sa get_teachers]: {e}")
            conn.send(json.dumps([]).encode())
        finally:
            conn.close()

    def handle_get_labs(self, conn):
        try:
            labs = db.get_all_labs()
            conn.send(json.dumps(labs).encode())
        except Exception as e:
            print(f"[ERROR sa get_labs]: {e}")
            conn.send(json.dumps([]).encode())
        finally:
            conn.close()

    def handle_set_lab(self, conn, data):
        try:
            username = ""
            lab_id_str = ""
            for part in data.split("|"):
                if "USER:" in part:
                    username = part.split("USER:")[1].strip()
                elif "LABID:" in part:
                    lab_id_str = part.split("LABID:")[1].strip()

            user = db.get_user_by_username(username)
            if user and lab_id_str.isdigit():
                db.set_user_lab(user["id"], int(lab_id_str))
                conn.send("SUCCESS".encode())

                # If this student is already connected/visible, re-check visibility now
                ip_to_username = getattr(self, "ip_to_username", {})
                for ip, uname in list(ip_to_username.items()):
                    if uname == username:
                        self.after(0, lambda u=username, i=ip: update_student_card_name(self, u, i))
            else:
                conn.send("FAILED".encode())
        except Exception as e:
            print(f"[ERROR sa set_lab]: {e}")
            conn.send("FAILED".encode())
        finally:
            conn.close()

    def process_register(self, data):
        try:
            parts = data.split("|")
            fields = {}
            for part in parts:
                if ":" in part:
                    key, val = part.split(":", 1)
                    fields[key.strip()] = val.strip()

            teacher_id_str = fields.get("TEACHERID", "")
            teacher_ids = [int(teacher_id_str)] if teacher_id_str.isdigit() else []

            ok, result = db.register_student(
                username=fields.get("USER", ""),
                password=fields.get("PWD", ""),
                full_name=fields.get("FULLNAME", ""),
                school_id=fields.get("SCHOOLID", ""),
                email=fields.get("EMAIL", ""),
                contact_number=fields.get("CONTACT", ""),
                course_section=fields.get("COURSE", ""),
                year_level=fields.get("YEAR", ""),
                teacher_ids=teacher_ids,
            )
            if ok:
                print(f"[SUCCESS] Na-save sa database, naghihintay ng approval! (user id {result})")
            else:
                print(f"[FAILED] Registration error: {result}")
        except Exception as e:
            print(f"[ERROR sa pag-save ng registration]: {e}")

    def process_log(self, data):
        try:
            parts = {p.split(": ")[0].strip(): p.split(": ")[1].strip() for p in data.split(" | ")}
            action, user, time_str = parts.get("ACTION"), parts.get("USER"), parts.get("TIME")
            if action == "LOGIN":
                self.all_logs.append({"user": user, "login": time_str, "logout": "--", "duration": "--"})
            elif action == "LOGOUT":
                for entry in reversed(self.all_logs):
                    if entry['user'] == user and entry['logout'] == "--":
                        login_dt = datetime.datetime.strptime(entry['login'], "%H:%M:%S")
                        logout_dt = datetime.datetime.strptime(time_str, "%H:%M:%S")
                        entry.update({"logout": time_str, "duration": str(logout_dt - login_dt)})
                        break
        except: pass

    # --- FULL SCREEN DEMO BROADCAST SERVER ---
    def broadcast_stream_server(self):
        PORT = 9996
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("0.0.0.0", PORT))
            server.listen(10)
            self.broadcast_socket = server
            print(f"[DEBUG] Broadcast Stream Server ay aktibo sa port {PORT}")
        except Exception as e:
            print(f"[ERROR sa Broadcast Server]: {e}")
            return
        
        while True:
            try:
                server.settimeout(1.0)
                conn, addr = server.accept()
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                threading.Thread(target=self.stream_handler, args=(conn,), daemon=True).start()
            except socket.timeout:
                continue
            except:
                break

    def stream_handler(self, conn):
        self.active_broadcast = True
        while self.active_broadcast:
            try:
                screenshot = pyautogui.screenshot()
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                frame = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA)
                
                _, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
                data = encoded.tobytes()
                
                header = struct.pack("!I", len(data))
                conn.sendall(header + data)
                
                time.sleep(0.03)
            except:
                break
        try:
            conn.close()
        except:
            pass

    def check_login(self):
        username = self.user_entry.get()
        password = self.pass_entry.get()

        try:
            admin_ip = discover_admin_ip(timeout=4.0)
            if not admin_ip and username.strip().lower() == "admin":
                admin_ip = "127.0.0.1"
            if not admin_ip:
                raise OSError("Hindi makita ang Admin app. Tiyaking bukas ito at nasa parehong local network ang computers.")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((admin_ip, 5001))
            s.sendall(f"ACTION: STAFF_LOGIN_CHECK | USER: {username} | PWD: {password}".encode())
            response = s.recv(4096).decode()
            s.close()
            result = json.loads(response)
        except Exception as e:
            self.error_label.configure(text=f"Cannot reach Admin server: {e}", text_color="red")
            return

        if result.get("success"):
            user = {"id": result["id"], "role": result["role"], "full_name": result["full_name"], "username": username}
            self.is_admin_node = user["role"] == "admin"
            self.withdraw()
            role = user["role"]

            if role == "teacher":
                def proceed_with_lab(lab_id):
                    db.set_user_lab(user["id"], lab_id)
                    self.current_teacher_lab_id = lab_id
                    self.current_teacher_user_id = user["id"]
                    self._notify_admin_teacher_online(user["id"], lab_id)
                    dashboard = TeacherDashboard(master_app=self)
                    self.active_teacher_dashboard = dashboard
                    dashboard.protocol("WM_DELETE_WINDOW", lambda: self.on_dashboard_close(dashboard))
                    start_teacher_streaming(user["full_name"] or user["username"])

                LabSelectionDialog(self, proceed_with_lab)

            elif role == "admin":
                dashboard = AdminDashboard(master_app=self)
                self.active_teacher_dashboard = dashboard
                dashboard.protocol("WM_DELETE_WINDOW", lambda: self.on_dashboard_close(dashboard))
        else:
            self.error_label.configure(text="Invalid credentials!", text_color="red")

    def on_dashboard_close(self, dashboard):
        if dashboard == self.active_teacher_dashboard:
            self.active_teacher_dashboard = None
            if isinstance(dashboard, TeacherDashboard):
                if getattr(self, "current_teacher_lab_id", None) is not None:
                    self._notify_admin_teacher_offline(self.current_teacher_lab_id)
                self.current_teacher_lab_id = None
                self.current_teacher_user_id = None
                stop_teacher_streaming()
            else:
                self.is_admin_node = False
        dashboard.destroy()
        self.deiconify()

if __name__ == "__main__":
    app = LoginApp()
    app.mainloop()