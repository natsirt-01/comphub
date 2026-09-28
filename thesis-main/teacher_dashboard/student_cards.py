import customtkinter as ctk
from config import COLORS


def setup_grid_layout(self):
    self.grid_frame = ctk.CTkScrollableFrame(self, label_text="LIVE LAB MONITORING", height=400,
                                             fg_color=COLORS["surface_alt"])
    self.grid_frame.pack(fill="both", expand=True, padx=20, pady=10)
    self.grid_frame.grid_columnconfigure((0, 1, 2), weight=1)


def build_card_label(pc_number, full_name, expression, role="student"):
    if role == "teacher":
        return f"TEACHER - {full_name}"
    return f"PC {pc_number} - {full_name} - {expression}"


def create_student_card(self, ip, index, pc_number, full_name, expression="Waiting...", role="student"):
    if ip in self.student_cards:
        return

    row = index // 3
    col = index % 3

    label = build_card_label(pc_number, full_name, expression, role)

    pc_card = ctk.CTkFrame(self.grid_frame, corner_radius=8, border_width=1,
                           fg_color=COLORS["white"], border_color="#cbd5e1")
    pc_card.grid(row=row, column=col, padx=12, pady=12, sticky="nsew")

    screen_preview = ctk.CTkFrame(pc_card, height=160, corner_radius=6,
                                  fg_color=COLORS["surface_alt"])
    screen_preview.pack(fill="x", padx=10, pady=10)
    screen_preview.pack_propagate(False)

    lbl_preview = ctk.CTkLabel(screen_preview, text=f"{label}\n(Waiting for Live Stream...)",
                               text_color=COLORS["muted"], font=ctk.CTkFont(size=11))
    lbl_preview.pack(fill="both", expand=True)

    lbl_preview.bind("<Button-3>", lambda e: self.show_context_menu(e, ip, label, role))
    screen_preview.bind("<Button-3>", lambda e: self.show_context_menu(e, ip, label, role))

    lbl_info_text = ctk.CTkLabel(pc_card, text=label, font=ctk.CTkFont(size=12, weight="bold"),
                                 text_color=COLORS["ink"])
    lbl_info_text.pack(pady=(0, 10))
    lbl_info_text.bind("<Button-3>", lambda e: self.show_context_menu(e, ip, label, role))

    self.student_cards[ip] = {
        "card": pc_card,
        "frame": pc_card,
        "preview": lbl_preview,
        "info_label": lbl_info_text,
        "pc_number": pc_number,
        "full_name": full_name,
        "expression": expression,
        "role": role,
        "restricted": False,
    }


def create_occupancy_card(parent, person, row, col, preview_image=None):
    role = person.get("role", "student").capitalize()
    name = person.get("full_name") or person.get("username") or "Unknown"
    pc_name = person.get("pc_name") or "Unidentified PC"
    ip_address = person.get("ip_address") or ""

    card = ctk.CTkFrame(parent, corner_radius=8, border_width=1,
                        fg_color=COLORS["white"], border_color="#cbd5e1")
    card.grid(row=row, column=col, padx=12, pady=12, sticky="nsew")

    preview = ctk.CTkFrame(card, height=120, corner_radius=6,
                           fg_color=COLORS["surface_alt"])
    preview.pack(fill="x", padx=10, pady=10)
    preview.pack_propagate(False)
    preview_label = ctk.CTkLabel(preview, text=f"{role} PC\n{pc_name}",
                                 text_color=COLORS["muted"],
                                 font=ctk.CTkFont(size=13, weight="bold"))
    preview_label.pack(fill="both", expand=True)
    if preview_image is not None:
        preview_label.configure(image=preview_image, text="")
        preview_label.image = preview_image

    ctk.CTkLabel(card, text=name, font=ctk.CTkFont(size=13, weight="bold"),
                 text_color=COLORS["ink"]).pack(pady=(0, 2))
    ctk.CTkLabel(card, text=f"{role} | {ip_address or pc_name}",
                 font=ctk.CTkFont(size=11), text_color=COLORS["muted"]).pack(pady=(0, 8))


def set_card_restricted(self, ip, restricted):
    card_info = self.student_cards.get(ip)
    if not card_info or card_info.get("restricted") == restricted:
        return
    card_info["restricted"] = restricted
    card_info["frame"].configure(
        border_color=COLORS["danger"] if restricted else "#cbd5e1",
        border_width=3 if restricted else 1,
    )
    card_info["info_label"].configure(
        text_color=COLORS["danger"] if restricted else COLORS["ink"]
    )