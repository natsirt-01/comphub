import socket
import threading
import io
from datetime import datetime
from PIL import Image, ImageTk

import socket as _socket
import json as _json
from network_config import TEACHER_IP, ADMIN_IP, LOG_PORT, get_registered_ip_role


def _get_user_info(username, is_admin_context):
    """If we're running inside Admin's own process, the local db is the
    real source of truth — read it directly. Otherwise (Teacher's process),
    the local db is a stale, unused copy, so ask Admin over the network."""
    from database import db as _db

    if is_admin_context:
        return _db.get_user_by_username(username)

    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((ADMIN_IP, LOG_PORT))
        s.sendall(f"ACTION: GET_USER_INFO | USER: {username}".encode())
        response = s.recv(4096).decode()
        s.close()
        data = _json.loads(response)
        return data if data else None
    except Exception as e:
        print(f"[ERROR _get_user_info network query]: {e}")
        return None

def handle_student_expression(self, expression_text, sender_ip):
    """self is always the LoginApp instance."""
    from .student_cards import build_card_label
    try:
        parts = expression_text.split("|")
        expression = parts[1].strip() if len(parts) >= 2 else expression_text.strip()

        if not hasattr(self, "student_expressions"):
            self.student_expressions = {}
        self.student_expressions[sender_ip] = expression

        dashboard = getattr(self, "active_teacher_dashboard", None)
        if dashboard and sender_ip in dashboard.student_cards:
            card_info = dashboard.student_cards[sender_ip]
            card_info["expression"] = expression
            new_label = build_card_label(card_info["pc_number"], card_info["full_name"], expression, card_info.get("role", "student"))
            if "info_label" in card_info and card_info["info_label"].winfo_exists():
                card_info["info_label"].configure(text=new_label)
    except Exception as e:
        print(f"[ERROR parsing expression]: {e}")


def update_student_card_name(self, username, ip, role="student"):
    """self is always the LoginApp instance. Updates persistent records and,
    if a dashboard is open, creates/updates the visible card. Lab filtering
    only applies to Teacher dashboards viewing students — Admin's monitor
    dashboard (is_admin_monitor=True) always shows everyone, students and
    teachers alike."""
    from .student_cards import create_student_card, build_card_label

    role = get_registered_ip_role(ip) or role

    dashboard_check = getattr(self, "active_teacher_dashboard", None)
    is_admin_context = getattr(dashboard_check, "is_admin_monitor", False)

    pc_number = ip.split('.')[-1]

    if role == "teacher":
        full_name = username
    else:
        user = _get_user_info(username, is_admin_context)
        full_name = (user["full_name"] if user and user.get("full_name") else username)

    if not hasattr(self, "student_display_names"):
        self.student_display_names = {}
    self.student_display_names[ip] = full_name

    if not hasattr(self, "ip_to_username"):
        self.ip_to_username = {}
    self.ip_to_username[ip] = username

    if not hasattr(self, "entity_roles"):
        self.entity_roles = {}
    if not hasattr(self, "handshake_roles"):
        self.handshake_roles = {}
    self.entity_roles[ip] = role

    dashboard = getattr(self, "active_teacher_dashboard", None)
    if dashboard is None:
        return

    is_admin_monitor = getattr(dashboard, "is_admin_monitor", False)

    if not is_admin_monitor:
        # This is a Teacher dashboard: never show other teachers, and only
        # show students who match this teacher's currently selected lab.
        if role == "teacher":
            if ip in dashboard.student_cards:
                card_info = dashboard.student_cards.pop(ip)
                try:
                    card_info["frame"].destroy()
                except Exception:
                    pass
            return
        teacher_lab_id = getattr(self, "current_teacher_lab_id", None)
        user = _get_user_info(username, is_admin_context)
        student_lab_id = user["lab_id"] if user else None
        if teacher_lab_id is not None and student_lab_id != teacher_lab_id:
            if ip in dashboard.student_cards:
                try:
                    card_info = dashboard.student_cards[ip]
                    if "frame" in card_info and card_info["frame"].winfo_exists():
                        card_info["frame"].destroy()
                except Exception:
                    pass
                del dashboard.student_cards[ip]
            return

    if ip not in dashboard.student_cards or "frame" not in dashboard.student_cards[ip] \
            or not dashboard.student_cards[ip]["frame"].winfo_exists():
        expression = getattr(self, "student_expressions", {}).get(ip, "Waiting...")
        create_student_card(dashboard, ip, len(dashboard.student_cards), pc_number, full_name, expression, role)
    else:
        card_info = dashboard.student_cards[ip]
        card_info["pc_number"] = pc_number
        card_info["full_name"] = full_name
        card_info["role"] = role
        new_label = build_card_label(pc_number, full_name, card_info["expression"], role)
        if "info_label" in card_info and card_info["info_label"].winfo_exists():
            card_info["info_label"].configure(text=new_label)


def hydrate_dashboard(self, dashboard):
    """Called once when a dashboard opens, to rebuild cards for whoever is
    already connected. Teacher dashboards: students only, filtered to the
    teacher's current lab. Admin's monitor dashboard (is_admin_monitor=True):
    everyone, students and teachers, no lab filtering."""
    from .student_cards import create_student_card

    frames = getattr(self, "latest_frames", {})
    expressions = getattr(self, "student_expressions", {})
    ip_to_username = getattr(self, "ip_to_username", {})
    roles = getattr(self, "entity_roles", {})
    teacher_lab_id = getattr(self, "current_teacher_lab_id", None)
    is_admin_monitor = getattr(dashboard, "is_admin_monitor", False)

    for ip in getattr(self, "connected_students", {}).keys():
        username = ip_to_username.get(ip)
        role = roles.get(ip, "student")

        if not is_admin_monitor:
            if role == "teacher":
                continue
            user = _get_user_info(username, is_admin_monitor) if username else None
            if user and teacher_lab_id is not None and user["lab_id"] != teacher_lab_id:
                continue
            full_name = (user["full_name"] if user and user.get("full_name") else (username or "Unknown"))
        else:
            if role == "teacher":
                full_name = username or "Unknown Teacher"
            else:
                user = _get_user_info(username, is_admin_monitor) if username else None
                full_name = (user["full_name"] if user and user.get("full_name") else (username or "Unknown"))

        pc_number = ip.split('.')[-1]
        expression = expressions.get(ip, "Waiting...")

        create_student_card(dashboard, ip, len(dashboard.student_cards), pc_number, full_name, expression, role)

        if ip in frames:
            update_thumbnail_frame_for(dashboard, ip, frames[ip])


def update_thumbnail_frame_for(dashboard, ip, img_tk):
    if ip in dashboard.student_cards:
        lbl = dashboard.student_cards[ip]["preview"]
        lbl.configure(image=img_tk, text="")
        lbl.image = img_tk


def update_thumbnail_frame(self, ip, img_tk):
    if not hasattr(self, "latest_frames"):
        self.latest_frames = {}
    self.latest_frames[ip] = img_tk

    dashboard = getattr(self, "active_teacher_dashboard", None)
    if dashboard is not None:
        update_thumbnail_frame_for(dashboard, ip, img_tk)


def start_alert_monitoring(self, dashboard):
    """Poll Admin's alert store so monitoring cards reflect restricted sites."""
    from .student_cards import set_card_restricted

    def poll():
        if not dashboard.winfo_exists():
            return
        try:
            request = "ACTION: GET_ALERTS | ACTIVE: 1"
            teacher_id = getattr(self, "current_teacher_user_id", None)
            if teacher_id and not getattr(dashboard, "is_admin_monitor", False):
                request += f" | TEACHERID: {teacher_id}"
            with _socket.create_connection((ADMIN_IP, LOG_PORT), timeout=2) as sock:
                sock.sendall(request.encode())
                alerts = _json.loads(sock.recv(65536).decode() or "[]")
            alert_ips = {alert.get("ip_address") for alert in alerts if alert.get("ip_address")}
            for ip in list(getattr(dashboard, "student_cards", {})):
                set_card_restricted(dashboard, ip, ip in alert_ips)
        except (OSError, ValueError) as error:
            print(f"[DEBUG alert monitor] {error}")
        dashboard.after(1500, poll)

    dashboard.after(500, poll)


def record_login(self, name, ip):
    login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in self.login_history_data:
        if item["ip"] == ip and item["logout"] == "Active / Online":
            return
    self.login_history_data.append({
        "name": name, "ip": ip, "login": login_time, "logout": "Active / Online", "duration": "-"
    })


def record_logout(self, ip):
    logout_time = datetime.now()
    logout_str = logout_time.strftime("%Y-%m-%d %H:%M:%S")
    for item in self.login_history_data:
        if item["ip"] == ip and item["logout"] == "Active / Online":
            item["logout"] = logout_str
            login_dt = datetime.strptime(item["login"], "%Y-%m-%d %H:%M:%S")
            duration_sec = int((logout_time - login_dt).total_seconds())
            hours, remainder = divmod(duration_sec, 3600)
            minutes, seconds = divmod(remainder, 60)
            item["duration"] = f"{hours}h {minutes}m {seconds}s"
            break


def _parse_handshake(raw_user_info, fallback_ip):
    """Returns (username, role) parsed from 'NAME: x|ROLE:y' or 'NAME: x'."""
    username = f"User-{fallback_ip}"
    role = "student"
    if "NAME:" in raw_user_info:
        after_name = raw_user_info.split("NAME:", 1)[1]
        if "|ROLE:" in after_name:
            name_part, role_part = after_name.split("|ROLE:", 1)
            username = name_part.strip() or username
            role = role_part.strip().lower() or "student"
        else:
            username = after_name.split("\n")[0].strip() or username
    return username, role


def start_persistent_stream_listeners(self):
    """Call exactly ONCE, from LoginApp.__init__. self is the LoginApp
    instance and lives for the whole program, so these listeners never get
    torn down/re-bound when a dashboard window opens/closes."""

    if not hasattr(self, "connected_students"):
        self.connected_students = {}
    if not hasattr(self, "student_display_names"):
        self.student_display_names = {}
    if not hasattr(self, "latest_frames"):
        self.latest_frames = {}
    if not hasattr(self, "student_expressions"):
        self.student_expressions = {}
    if not hasattr(self, "login_history_data"):
        self.login_history_data = []
    if not hasattr(self, "active_teacher_dashboard"):
        self.active_teacher_dashboard = None
    if not hasattr(self, "entity_roles"):
        self.entity_roles = {}
    if not hasattr(self, "ip_to_username"):
        self.ip_to_username = {}

    def handle_client(conn, addr):
        student_ip = addr[0]
        self.connected_students[student_ip] = conn

        username = f"User-{student_ip}"
        role = "student"
        try:
            conn.settimeout(3.0)
            raw_user_info = conn.recv(128).decode('utf-8', errors='ignore').strip()
            conn.settimeout(None)
            username, role = _parse_handshake(raw_user_info, student_ip)
        except Exception:
            conn.settimeout(None)
        self.handshake_roles[student_ip] = role

        if hasattr(self, 'after'):
            self.after(0, lambda u=username, ip=student_ip, r=role: update_student_card_name(self, u, ip, r))
            display_name = f"{username} - PC {student_ip.split('.')[-1]}" if role == "student" else f"TEACHER - {username}"
            self.after(0, lambda: record_login(self, display_name, student_ip))

        try:
            while True:
                raw_length = conn.recv(4)
                if not raw_length:
                    break
                frame_length = int.from_bytes(raw_length, byteorder='big')

                frame_data = b""
                while len(frame_data) < frame_length:
                    packet = conn.recv(frame_length - len(frame_data))
                    if not packet:
                        break
                    frame_data += packet

                if len(frame_data) == frame_length:
                    image = Image.open(io.BytesIO(frame_data)).resize((240, 150), Image.Resampling.LANCZOS)
                    img_tk = ImageTk.PhotoImage(image)
                    if hasattr(self, 'after'):
                        self.after(0, lambda ip=student_ip, img=img_tk: update_thumbnail_frame(self, ip, img))
        except Exception as e:
            print(f"Stream error with {student_ip}: {e}")
        finally:
            conn.close()
            if student_ip in self.connected_students:
                del self.connected_students[student_ip]
            self.handshake_roles.pop(student_ip, None)

            def remove_card_ui():
                dashboard = getattr(self, "active_teacher_dashboard", None)
                if dashboard and student_ip in dashboard.student_cards:
                    try:
                        card_info = dashboard.student_cards[student_ip]
                        if isinstance(card_info, dict) and "frame" in card_info and card_info["frame"].winfo_exists():
                            card_info["frame"].destroy()
                    except Exception:
                        pass
                    del dashboard.student_cards[student_ip]

            if hasattr(self, 'after'):
                self.after(0, remove_card_ui)
                self.after(0, lambda: record_logout(self, student_ip))

            def force_close_db_session():
                from database import db
                username = self.ip_to_username.get(student_ip) if hasattr(self, "ip_to_username") else None
                if username:
                    user = db.get_user_by_username(username)
                    if user:
                        session_id = db.get_active_session_id(user["id"])
                        if session_id:
                            db.end_session(session_id)

            if hasattr(self, 'after'):
                self.after(0, force_close_db_session)

    def stream_listener():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("0.0.0.0", 9998))
            server.listen(10)
        except Exception as e:
            print(f"[ERROR] Stream listener could not bind 0.0.0.0:9998: {e}")
            return
        while True:
            try:
                conn, addr = server.accept()
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                print(f"[ERROR] Stream listener accept failed: {e}")

    threading.Thread(target=stream_listener, daemon=True).start()

    def handle_remote_client(conn, addr):
        student_ip = addr[0]
        try:
            while True:
                raw_length = conn.recv(4)
                if not raw_length:
                    break
                frame_length = int.from_bytes(raw_length, byteorder='big')

                frame_data = b""
                while len(frame_data) < frame_length:
                    packet = conn.recv(frame_length - len(frame_data))
                    if not packet:
                        break
                    frame_data += packet

                if len(frame_data) == frame_length:
                    image = Image.open(io.BytesIO(frame_data))

                    dashboard = getattr(self, "active_teacher_dashboard", None)
                    if dashboard and hasattr(dashboard, 'active_viewers') and student_ip in dashboard.active_viewers:
                        viewer = dashboard.active_viewers[student_ip]
                        if viewer.winfo_exists():
                            viewer.after(0, lambda img=image, v=viewer: v.update_image(img))
        except Exception as e:
            print(f"Remote view error for {student_ip}: {e}")
        finally:
            conn.close()

    def remote_listener():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("0.0.0.0", 9997))
            server.listen(10)
        except Exception as e:
            print(f"[ERROR] Remote view listener could not bind 0.0.0.0:9997: {e}")
            return
        while True:
            try:
                conn, addr = server.accept()
                threading.Thread(target=handle_remote_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                print(f"[ERROR] Remote listener accept failed: {e}")

    threading.Thread(target=remote_listener, daemon=True).start()