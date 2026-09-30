import socket
import threading
import io
import time
from datetime import datetime
from PIL import Image, ImageTk

import socket as _socket
import json as _json
from network_config import LOG_PORT, get_admin_ip


def _get_user_info(username, is_admin_context):
    """If we're running inside Admin's own process, the local db is the
    real source of truth — read it directly. Otherwise (Teacher's process),
    the local db is a stale, unused copy, so ask Admin over the network."""
    from database import db as _db

    if is_admin_context:
        return _db.get_user_by_username(username)

    try:
        admin_ip = get_admin_ip()
        if not admin_ip:
            return None
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((admin_ip, LOG_PORT))
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
        try:
            if not lbl.winfo_exists():
                return
            lbl.configure(image=img_tk, text="")
            lbl.image = img_tk
        except Exception as error:
            print(f"[monitor stream] Could not render preview for {ip}: {error}")


def _tint_restricted_frame(dashboard, ip, image):
    card_info = getattr(dashboard, "student_cards", {}).get(ip)
    if card_info and card_info.get("restricted"):
        red_overlay = Image.new("RGB", image.size, (198, 40, 40))
        return Image.blend(image.convert("RGB"), red_overlay, 0.42)
    return image


def update_thumbnail_frame(self, ip, image, source_conn=None):
    if source_conn is not None and self.connected_students.get(ip) is not source_conn:
        return
    dashboard = getattr(self, "active_teacher_dashboard", None)
    raw_image = image.copy()
    if dashboard is not None:
        image = _tint_restricted_frame(dashboard, ip, image)
    img_tk = ImageTk.PhotoImage(image)
    if not hasattr(self, "latest_frames"):
        self.latest_frames = {}
    if not hasattr(self, "latest_raw_frames"):
        self.latest_raw_frames = {}
    if not hasattr(self, "stream_frame_seen"):
        self.stream_frame_seen = set()
    self.latest_frames[ip] = img_tk
    self.latest_raw_frames[ip] = raw_image
    if ip not in self.stream_frame_seen:
        self.stream_frame_seen.add(ip)
        print(f"[monitor stream] First frame received from {ip}")

    if dashboard is not None:
        update_thumbnail_frame_for(dashboard, ip, img_tk)


def start_alert_monitoring(self, dashboard):
    """Poll Admin's alert store so monitoring cards reflect restricted sites."""
    from .student_cards import set_card_restricted
    poll_state = {"last_error": None}

    def poll():
        if not dashboard.winfo_exists():
            return
        try:
            if getattr(dashboard, "is_admin_monitor", False):
                from database import db
                alerts = db.get_alerts_for_admin(unacknowledged_only=False, active_only=True)
            else:
                admin_ip = get_admin_ip()
                if not admin_ip:
                    raise OSError("Admin server was not discovered on this LAN.")
                request = "ACTION: GET_ALERTS | ACTIVE: 1 | UNACKED: 0"
                teacher_id = getattr(self, "current_teacher_user_id", None)
                lab_id = getattr(self, "current_teacher_lab_id", None)
                if teacher_id:
                    request += f" | TEACHERID: {teacher_id}"
                if lab_id is not None:
                    request += f" | LABID: {lab_id}"
                with _socket.create_connection((admin_ip, LOG_PORT), timeout=2) as sock:
                    sock.sendall(request.encode())
                    alerts = _json.loads(sock.recv(65536).decode() or "[]")
            alert_ips = {alert.get("ip_address") for alert in alerts if alert.get("ip_address")}
            for ip in list(getattr(dashboard, "student_cards", {})):
                set_card_restricted(dashboard, ip, ip in alert_ips)
            poll_state["last_error"] = None
        except (OSError, ValueError) as error:
            message = str(error)
            if message != poll_state["last_error"]:
                print(f"[DEBUG alert monitor] {message}")
                poll_state["last_error"] = message
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
    """Returns (username, role, source_ip) from a stream handshake."""
    fields = {}
    for part in raw_user_info.split("|"):
        if ":" in part:
            key, value = part.split(":", 1)
            fields[key.strip().upper()] = value.strip()
    username = fields.get("NAME") or f"User-{fallback_ip}"
    role = fields.get("ROLE", "student").lower()
    source_ip = fields.get("IP", fallback_ip)
    return username, role, source_ip


def _get_teacher_stream_ip(self, username):
    if not getattr(self, "is_admin_node", False):
        return None
    from database import db as _db

    student = _db.get_user_by_username(username)
    if not student or student.get("role") != "student":
        return None
    entry = getattr(self, "online_teachers", {}).get(student.get("lab_id"))
    return entry.get("ip_address") if entry else None


def _read_handshake(conn, limit=128):
    handshake = bytearray()
    while len(handshake) < limit and not handshake.endswith(b"\n"):
        packet = conn.recv(1)
        if not packet:
            break
        handshake.extend(packet)
    return handshake.decode("utf-8", errors="ignore").strip()


def _recv_exact(conn, byte_count):
    data = bytearray()
    while len(data) < byte_count:
        packet = conn.recv(byte_count - len(data))
        if not packet:
            return None
        data.extend(packet)
    return bytes(data)


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
    if not hasattr(self, "stream_frame_seen"):
        self.stream_frame_seen = set()
    if not hasattr(self, "student_expressions"):
        self.student_expressions = {}
    if not hasattr(self, "login_history_data"):
        self.login_history_data = []
    if not hasattr(self, "active_teacher_dashboard"):
        self.active_teacher_dashboard = None
    if not hasattr(self, "entity_roles"):
        self.entity_roles = {}
    if not hasattr(self, "handshake_roles"):
        self.handshake_roles = {}
    if not hasattr(self, "ip_to_username"):
        self.ip_to_username = {}

    def handle_client(conn, addr):
        peer_ip = addr[0]
        student_ip = peer_ip
        username = f"User-{peer_ip}"
        role = "student"
        try:
            conn.settimeout(3.0)
            raw_user_info = _read_handshake(conn)
            conn.settimeout(None)
            username, role, source_ip = _parse_handshake(raw_user_info, peer_ip)
            if source_ip != peer_ip and (
                getattr(self, "is_admin_node", False)
                or peer_ip == getattr(self, "admin_ip", None)
            ):
                student_ip = source_ip
        except Exception:
            conn.settimeout(None)
        self.connected_students[student_ip] = conn
        self.handshake_roles[student_ip] = role
        print(f"[monitor stream] Accepted {role} '{username}' from {student_ip} on TCP 9998")

        relay_ip = _get_teacher_stream_ip(self, username) if role == "student" else None
        relay_conn = None
        relay_retry_at = 0.0
        last_relayed_at = 0.0

        if hasattr(self, 'after'):
            self.after(0, lambda u=username, ip=student_ip, r=role: update_student_card_name(self, u, ip, r))
            display_name = f"{username} - PC {student_ip.split('.')[-1]}" if role == "student" else f"TEACHER - {username}"
            self.after(0, lambda: record_login(self, display_name, student_ip))

        try:
            while True:
                raw_length = _recv_exact(conn, 4)
                if not raw_length:
                    break
                frame_length = int.from_bytes(raw_length, byteorder='big')
                if frame_length <= 0 or frame_length > 20 * 1024 * 1024:
                    raise ValueError(f"Invalid frame size: {frame_length}")
                frame_data = _recv_exact(conn, frame_length)
                if frame_data is None:
                    break
                image = Image.open(io.BytesIO(frame_data)).convert("RGB").resize(
                    (240, 150), Image.Resampling.LANCZOS
                )
                if relay_ip:
                    now = time.monotonic()
                    if relay_conn is None and now >= relay_retry_at:
                        try:
                            relay_conn = socket.create_connection((relay_ip, 9998), timeout=1.0)
                            relay_conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                            relay_conn.sendall(
                                f"NAME: {username}|ROLE:student|IP:{student_ip}\n".encode("utf-8")
                            )
                            relay_conn.settimeout(5.0)
                        except OSError as error:
                            print(f"[monitor relay] Cannot connect to Teacher {relay_ip}: {error}")
                            if relay_conn:
                                relay_conn.close()
                            relay_conn = None
                            relay_retry_at = now + 2.0
                    if relay_conn and now - last_relayed_at >= 0.05:
                        try:
                            relay_buffer = io.BytesIO()
                            image.save(relay_buffer, format="JPEG", quality=65, optimize=True)
                            relay_frame = relay_buffer.getvalue()
                            relay_conn.sendall(len(relay_frame).to_bytes(4, "big") + relay_frame)
                            last_relayed_at = now
                        except OSError as error:
                            print(f"[monitor relay] Stream to Teacher {relay_ip} stopped: {error}")
                            relay_conn.close()
                            relay_conn = None
                            relay_retry_at = time.monotonic() + 2.0
                if hasattr(self, 'after'):
                    self.after(0, lambda ip=student_ip, frame=image, source=conn:
                               update_thumbnail_frame(self, ip, frame, source))
        except Exception as e:
            print(f"Stream error with {student_ip}: {e}")
        finally:
            conn.close()
            if relay_conn:
                relay_conn.close()
            is_current_connection = self.connected_students.get(student_ip) is conn
            if is_current_connection:
                del self.connected_students[student_ip]
                self.handshake_roles.pop(student_ip, None)
                self.latest_frames.pop(student_ip, None)
                getattr(self, "latest_raw_frames", {}).pop(student_ip, None)
                self.stream_frame_seen.discard(student_ip)

            def remove_card_ui():
                if not is_current_connection:
                    return
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
                if is_current_connection:
                    self.after(0, lambda: record_logout(self, student_ip))

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
                raw_length = _recv_exact(conn, 4)
                if not raw_length:
                    break
                frame_length = int.from_bytes(raw_length, byteorder='big')
                if frame_length <= 0 or frame_length > 20 * 1024 * 1024:
                    raise ValueError(f"Invalid frame size: {frame_length}")
                frame_data = _recv_exact(conn, frame_length)
                if frame_data is None:
                    break
                image = Image.open(io.BytesIO(frame_data)).convert("RGB")

                dashboard = getattr(self, "active_teacher_dashboard", None)
                if dashboard and hasattr(dashboard, 'active_viewers') and student_ip in dashboard.active_viewers:
                    viewer = dashboard.active_viewers[student_ip]
                    if viewer.winfo_exists():
                        image = _tint_restricted_frame(dashboard, student_ip, image)
                        viewer.queue_image(image)
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