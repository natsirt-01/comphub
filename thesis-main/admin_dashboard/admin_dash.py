import customtkinter as ctk
import tkinter.ttk as ttk
from database import db
from teacher_dashboard.network_utils import send_command
import tkinter as tk
from tkinter import messagebox
from teacher_dashboard.network_listeners import hydrate_dashboard, start_alert_monitoring
from teacher_dashboard.student_cards import create_occupancy_card
from teacher_dashboard.date_filters import matches_date_range, parse_date_range
from teacher_dashboard.screen_receiver import ScreenViewer
from config import COLORS, maximize_window

class AdminDashboard(ctk.CTkToplevel):
    def __init__(self, master_app):
        super().__init__()
        self.master_app = master_app
        from ui_utils import center_window
        self.title("Super Admin Dashboard")
        center_window(self, 1280, 820)
        maximize_window(self)
        self.configure(fg_color=COLORS["surface"])

        # --- Top toolbar: all-PC power controls & Logout ---
        top_bar = ctk.CTkFrame(self, height=74, corner_radius=0, fg_color=COLORS["navy"])
        top_bar.pack(side="top", fill="x")

        # Left side power controls
        ctk.CTkLabel(top_bar, text="Student PCs:", font=ctk.CTkFont(size=13, weight="bold"), text_color="white").pack(side="left", padx=(15, 5))
        ctk.CTkButton(top_bar, text="Sleep All", fg_color=COLORS["warning"], hover_color="#9d6d0d", width=100,
                    command=self.sleep_all).pack(side="left", padx=5, pady=12)
        ctk.CTkButton(top_bar, text="Restart All", fg_color=COLORS["blue"], hover_color=COLORS["blue_hover"], width=100,
                    command=self.restart_all).pack(side="left", padx=5, pady=12)
        ctk.CTkButton(top_bar, text="Shutdown All", fg_color=COLORS["danger"], hover_color=COLORS["pink_hover"], width=110,
                    command=self.shutdown_all).pack(side="left", padx=5, pady=12)

        # Right side Logout button
        ctk.CTkButton(top_bar, text="Logout", fg_color=COLORS["danger"], hover_color=COLORS["pink_hover"], width=100,
                    command=self.logout_admin).pack(side="right", padx=15, pady=12)

        tabview = ctk.CTkTabview(self, fg_color=COLORS["surface"], segmented_button_fg_color=COLORS["navy_panel"], segmented_button_selected_color=COLORS["blue"], segmented_button_selected_hover_color=COLORS["blue_hover"])
        tabview.pack(expand=True, fill="both", padx=20, pady=20)
        
        tabview.add("Monitoring")
        tabview.add("Logs & History")
        tabview.add("User Management")
        tabview.add("Manage Teachers")
        tabview.add("Lab Monitoring")
        tabview.add("Inventory")
        tabview.add("Blocking Rules")

        # --- Monitoring Tab ---
        self.student_cards = {}
        self.active_viewers = {}
        self.is_admin_monitor = True

        monitor_tab = tabview.tab("Monitoring")
        self.grid_frame = ctk.CTkScrollableFrame(monitor_tab, label_text="LIVE LAB MONITORING",
                             height=400, fg_color=COLORS["surface_alt"])
        self.grid_frame.pack(fill="both", expand=True, padx=20, pady=10)
        self.grid_frame.grid_columnconfigure((0, 1, 2), weight=1)

        hydrate_dashboard(self.master_app, self)
        start_alert_monitoring(self.master_app, self)
        
        # --- Logs & History Tab ---
        logs_top_row = ctk.CTkFrame(tabview.tab("Logs & History"), fg_color="transparent")
        logs_top_row.pack(pady=10, fill="x")

        self.search_entry = ctk.CTkEntry(logs_top_row, placeholder_text="Search student name...", width=300)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self.filter_logs)

        ctk.CTkButton(logs_top_row, text="Refresh", width=90, fg_color=COLORS["blue"], hover_color=COLORS["blue_hover"],
                    command=lambda: self.refresh_table()).pack(side="left")

        logs_date_row = ctk.CTkFrame(tabview.tab("Logs & History"), fg_color="transparent")
        logs_date_row.pack(fill="x", padx=10, pady=(0, 6))
        self.history_start_date = ctk.CTkEntry(logs_date_row, placeholder_text="From (YYYY-MM-DD)", width=150)
        self.history_start_date.pack(side="left", padx=(0, 6))
        self.history_end_date = ctk.CTkEntry(logs_date_row, placeholder_text="To (YYYY-MM-DD)", width=150)
        self.history_end_date.pack(side="left", padx=6)
        ctk.CTkButton(logs_date_row, text="Apply dates", width=100,
                  command=self.refresh_table).pack(side="left", padx=6)
        ctk.CTkButton(logs_date_row, text="Clear dates", width=95,
                  command=self.clear_history_dates).pack(side="left", padx=6)
        self.history_filter_status = ctk.CTkLabel(logs_date_row, text="", anchor="w")
        self.history_filter_status.pack(side="left", padx=8)

        self.tree = ttk.Treeview(tabview.tab("Logs & History"), columns=("User", "Login", "Logout", "Duration"), show='headings')
        for col in ["User", "Login", "Logout", "Duration"]:
            self.tree.heading(col, text=col)
        self.tree.pack(fill="both", expand=True, pady=5)
        
        # --- User Management Tab ---
        user_tab = tabview.tab("User Management")
        ctk.CTkLabel(user_tab, text="Reset Student Password", font=("Arial", 16, "bold")).pack(pady=(20, 10))
        
        self.target_user_entry = ctk.CTkEntry(user_tab, placeholder_text="Enter Student Username", width=250)
        self.target_user_entry.pack(pady=10)
        
        ctk.CTkButton(user_tab, text=f"Reset to Default Password", fg_color=COLORS["danger"], hover_color=COLORS["pink_hover"], width=200,
                    command=self.reset_student_password).pack(pady=10)

        ctk.CTkLabel(user_tab, text="Update Account Display Name", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(20, 5))
        self.rename_user_entry = ctk.CTkEntry(user_tab, placeholder_text="Account username", width=250)
        self.rename_user_entry.pack(pady=5)
        self.rename_full_name_entry = ctk.CTkEntry(user_tab, placeholder_text="New display name", width=250)
        self.rename_full_name_entry.pack(pady=5)
        ctk.CTkButton(user_tab, text="Update Name", fg_color=COLORS["blue"],
                  hover_color=COLORS["blue_hover"], width=200,
                  command=self.rename_user).pack(pady=8)
        
        self.status_label = ctk.CTkLabel(user_tab, text="")
        self.status_label.pack(pady=5)
        
        self.refresh_table()

        # --- Manage Teachers Tab ---
        teacher_tab = tabview.tab("Manage Teachers")

        ctk.CTkLabel(teacher_tab, text="Create Teacher Account", font=("Arial", 16, "bold")).pack(pady=(15, 10))

        self.new_teacher_user = ctk.CTkEntry(teacher_tab, placeholder_text="Username", width=250)
        self.new_teacher_user.pack(pady=5)
        self.new_teacher_pass = ctk.CTkEntry(teacher_tab, placeholder_text="Password", show="*", width=250)
        self.new_teacher_pass.pack(pady=5)
        self.new_teacher_name = ctk.CTkEntry(teacher_tab, placeholder_text="Full Name", width=250)
        self.new_teacher_name.pack(pady=5)

        ctk.CTkButton(teacher_tab, text="Create Teacher", fg_color=COLORS["blue"], hover_color=COLORS["blue_hover"], width=200,
                    command=self.create_teacher).pack(pady=10)

        self.teacher_create_status = ctk.CTkLabel(teacher_tab, text="")
        self.teacher_create_status.pack(pady=5)

        ctk.CTkLabel(teacher_tab, text="Existing Teachers", font=("Arial", 14, "bold")).pack(pady=(20, 5))
        self.teacher_list_frame = ctk.CTkScrollableFrame(teacher_tab, width=500, height=180)
        self.teacher_list_frame.pack(pady=5, fill="both", expand=True, padx=20)
        self.refresh_teacher_list()

        # --- Lab Monitoring Tab ---
        lab_tab = tabview.tab("Lab Monitoring")

        lab_btn_row = ctk.CTkFrame(lab_tab, fg_color="transparent")
        lab_btn_row.pack(pady=15)

        self.lab_buttons = {}
        labs = db.get_all_labs()
        for lab in labs:
            btn = ctk.CTkButton(lab_btn_row, text=lab["name"], width=160, fg_color=COLORS["navy_panel"], hover_color=COLORS["pink_hover"],
                                command=lambda lid=lab["id"], lname=lab["name"]: self.show_lab_occupancy(lid, lname))
            btn.pack(side="left", padx=10)
            self.lab_buttons[lab["id"]] = btn

        self.lab_occupancy_label = ctk.CTkLabel(lab_tab, text="Select a lab above to view occupancy.",
                                                font=("Arial", 14, "bold"))
        self.lab_occupancy_label.pack(pady=10)

        self.lab_occupancy_frame = ctk.CTkScrollableFrame(lab_tab, width=600, height=280)
        self.lab_occupancy_frame.pack(pady=5, fill="both", expand=True, padx=20)
        self.lab_occupancy_frame.grid_columnconfigure((0, 1, 2), weight=1)
        self.selected_lab = None
        self.lab_refresh_after = None

        # --- Inventory Tab ---
        inv_tab = tabview.tab("Inventory")

        add_item_frame = ctk.CTkFrame(inv_tab, fg_color="transparent")
        add_item_frame.pack(pady=10, fill="x", padx=10)

        ctk.CTkLabel(add_item_frame, text="Add New Item", font=("Arial", 14, "bold")).pack(anchor="w")

        add_row = ctk.CTkFrame(add_item_frame, fg_color="transparent")
        add_row.pack(fill="x", pady=5)
        self.inv_item_name = ctk.CTkEntry(add_row, placeholder_text="Item name (e.g. Wireless Mouse)", width=250)
        self.inv_item_name.pack(side="left", padx=5)
        self.inv_item_qty = ctk.CTkEntry(add_row, placeholder_text="Qty", width=80)
        self.inv_item_qty.pack(side="left", padx=5)
        ctk.CTkButton(add_row, text="Add Item", fg_color=COLORS["blue"], hover_color=COLORS["blue_hover"], command=self.add_inventory_item_ui).pack(side="left", padx=5)

        self.inv_status_label = ctk.CTkLabel(inv_tab, text="")
        self.inv_status_label.pack()

        borrow_frame = ctk.CTkFrame(inv_tab, fg_color="transparent")
        borrow_frame.pack(pady=10, fill="x", padx=10)
        ctk.CTkLabel(borrow_frame, text="Log a Borrow", font=("Arial", 14, "bold")).pack(anchor="w")

        borrow_row = ctk.CTkFrame(borrow_frame, fg_color="transparent")
        borrow_row.pack(fill="x", pady=5)

        self.inv_item_map = {}
        self.inv_item_dropdown = ctk.CTkOptionMenu(borrow_row, values=["No items yet"], width=200, fg_color=COLORS["blue"], button_color=COLORS["blue_hover"])
        self.inv_item_dropdown.pack(side="left", padx=5)
        self.inv_borrower_name = ctk.CTkEntry(borrow_row, placeholder_text="Borrower name", width=180)
        self.inv_borrower_name.pack(side="left", padx=5)
        self.inv_borrow_qty = ctk.CTkEntry(borrow_row, placeholder_text="Qty", width=60)
        self.inv_borrow_qty.pack(side="left", padx=5)
        ctk.CTkButton(borrow_row, text="Borrow", fg_color=COLORS["blue"], hover_color=COLORS["blue_hover"], command=self.borrow_item_ui).pack(side="left", padx=5)

        ctk.CTkLabel(inv_tab, text="All Items", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=(15, 0))
        self.inv_items_frame = ctk.CTkScrollableFrame(inv_tab, height=100)
        self.inv_items_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(inv_tab, text="Currently Borrowed", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=(15, 0))
        self.inv_active_frame = ctk.CTkScrollableFrame(inv_tab, height=150)
        self.inv_active_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.refresh_inventory_ui()

        # --- Blocking Rules Tab ---
        blocking_tab = tabview.tab("Blocking Rules")
        ctk.CTkLabel(blocking_tab, text="Restricted-site keywords",
                 font=ctk.CTkFont(size=17, weight="bold")).pack(anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(blocking_tab, text="Matching keywords are checked against active window titles and reported to teachers.",
                 text_color=COLORS["muted"]).pack(anchor="w", padx=16, pady=(0, 10))

        rule_form = ctk.CTkFrame(blocking_tab, fg_color="transparent")
        rule_form.pack(fill="x", padx=12, pady=4)
        self.block_keyword_entry = ctk.CTkEntry(rule_form, placeholder_text="Keyword or site", width=250)
        self.block_keyword_entry.pack(side="left", padx=4)
        self.block_category_entry = ctk.CTkEntry(rule_form, placeholder_text="Category", width=180)
        self.block_category_entry.pack(side="left", padx=4)
        ctk.CTkButton(rule_form, text="Add rule", fg_color=COLORS["blue"],
                  hover_color=COLORS["blue_hover"], command=self.add_blocking_rule).pack(side="left", padx=4)
        self.blocking_status = ctk.CTkLabel(blocking_tab, text="", anchor="w")
        self.blocking_status.pack(fill="x", padx=16, pady=(2, 6))
        self.blocking_rules_frame = ctk.CTkScrollableFrame(blocking_tab)
        self.blocking_rules_frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.refresh_blocking_rules()

    def logout_admin(self):
        if hasattr(self.master_app, "on_dashboard_close"):
            self.master_app.on_dashboard_close(self)
        else:
            self.destroy()

    def reset_student_password(self):
        username = self.target_user_entry.get().strip()
        user = db.get_user_by_username(username)

        if not user or user["role"] != "student":
            self.status_label.configure(text="User not found!", text_color=COLORS["danger"])
            return

        db.reset_to_default_password(user["id"])
        self.status_label.configure(
            text=f"Reset success! New password: {db.DEFAULT_RESET_PASSWORD}",
            text_color=COLORS["sky"]
        )

    def rename_user(self):
        username = self.rename_user_entry.get().strip()
        full_name = self.rename_full_name_entry.get().strip()
        user = db.get_user_by_username(username)
        if not user or not full_name:
            self.status_label.configure(text="Enter an existing username and a display name.", text_color="orange")
            return
        db.update_user_full_name(user["id"], full_name)
        self.status_label.configure(text=f"Updated display name for {username}.", text_color=COLORS["sky"])
        self.rename_full_name_entry.delete(0, "end")

    def refresh_table(self, data=None):
        target = data if data is not None else db.get_all_sessions_history()
        try:
            start, end = parse_date_range(self.history_start_date.get(), self.history_end_date.get())
        except ValueError as error:
            self.history_filter_status.configure(text=str(error), text_color=COLORS["danger"])
            return
        query = self.search_entry.get().strip().casefold()
        target = [entry for entry in target
                  if query in (entry["full_name"] or "").casefold()
                  or query in entry["username"].casefold()]
        target = [entry for entry in target
                  if matches_date_range(entry.get("login_time"), start, end)]
        for item in self.tree.get_children():
            self.tree.delete(item)
        for entry in target:
            display_name = entry["full_name"] or entry["username"]
            duration = entry["duration_secs"] or 0
            mins, secs = divmod(duration, 60)
            hrs, mins = divmod(mins, 60)
            duration_str = f"{hrs}h {mins}m {secs}s" if entry["logout_time"] else "Active"
            self.tree.insert("", "end", values=(
                f"{display_name} ({entry['role']})",
                entry["login_time"],
                entry["logout_time"] or "Still active",
                duration_str,
            ))
        self.history_filter_status.configure(text=f"{len(target)} session(s)", text_color=COLORS["muted"])

    def filter_logs(self, event):
        self.refresh_table()

    def clear_history_dates(self):
        self.history_start_date.delete(0, "end")
        self.history_end_date.delete(0, "end")
        self.refresh_table()

    def create_teacher(self):
        username = self.new_teacher_user.get().strip()
        password = self.new_teacher_pass.get().strip()
        full_name = self.new_teacher_name.get().strip()

        if not username or not password or not full_name:
            self.teacher_create_status.configure(text="Punan ang lahat ng kahon.", text_color="orange")
            return

        if db.get_user_by_username(username):
            self.teacher_create_status.configure(text="Username already taken.", text_color=COLORS["danger"])
            return

        db.create_staff_user(username, password, "teacher", full_name=full_name)
        self.teacher_create_status.configure(text=f"Teacher '{full_name}' created!", text_color=COLORS["sky"])
        self.new_teacher_user.delete(0, "end")
        self.new_teacher_pass.delete(0, "end")
        self.new_teacher_name.delete(0, "end")
        self.refresh_teacher_list()

    def refresh_teacher_list(self):
        for widget in self.teacher_list_frame.winfo_children():
            widget.destroy()

        teachers = db.get_all_teachers()
        if not teachers:
            ctk.CTkLabel(self.teacher_list_frame, text="No teachers yet.", text_color="gray").pack(pady=10)
            return

        for t in teachers:
            student_count = len(db.get_students_for_teacher(t["id"]))
            text = f"{t['full_name']} ({t['username']}) — {student_count} student(s)"
            ctk.CTkLabel(self.teacher_list_frame, text=text, anchor="w").pack(fill="x", padx=10, pady=3)

    def show_lab_occupancy(self, lab_id, lab_name):
        self.selected_lab = (lab_id, lab_name)
        self.refresh_lab_occupancy()

    def refresh_lab_occupancy(self):
        if not self.winfo_exists() or self.selected_lab is None:
            return

        lab_id, lab_name = self.selected_lab
        self.lab_occupancy_label.configure(text=f"{lab_name} — Currently Occupied")

        for widget in self.lab_occupancy_frame.winfo_children():
            widget.destroy()

        occupants = db.get_lab_occupancy(lab_id)
        if not occupants:
            ctk.CTkLabel(self.lab_occupancy_frame, text="No one is currently in this lab.",
                        text_color="gray").pack(pady=20)
        else:
            for index, person in enumerate(occupants):
                ip_address = person.get("ip_address")
                preview_image = getattr(self.master_app, "latest_frames", {}).get(ip_address)
                create_occupancy_card(self.lab_occupancy_frame, person, index // 3, index % 3, preview_image)

        if self.lab_refresh_after:
            self.after_cancel(self.lab_refresh_after)
        self.lab_refresh_after = self.after(5000, self.refresh_lab_occupancy)

    def refresh_blocking_rules(self):
        for widget in self.blocking_rules_frame.winfo_children():
            widget.destroy()

        for rule in db.get_blocklist():
            row = ctk.CTkFrame(self.blocking_rules_frame)
            row.pack(fill="x", padx=5, pady=3)
            ctk.CTkLabel(row, text=rule["keyword"], anchor="w").pack(side="left", padx=10, pady=7, fill="x", expand=True)
            ctk.CTkLabel(row, text=rule["category"], width=140, anchor="w",
                         text_color=COLORS["muted"]).pack(side="left", padx=8)
            ctk.CTkButton(row, text="Remove", width=80, fg_color=COLORS["danger"],
                          hover_color="#a92e3b",
                          command=lambda rid=rule["id"]: self.remove_blocking_rule(rid)).pack(side="right", padx=8, pady=5)

    def add_blocking_rule(self):
        keyword = self.block_keyword_entry.get().strip()
        category = self.block_category_entry.get().strip()
        if not keyword or not category:
            self.blocking_status.configure(text="Enter both a keyword and category.", text_color="orange")
            return
        if any(rule["keyword"].casefold() == keyword.casefold() for rule in db.get_blocklist()):
            self.blocking_status.configure(text="That keyword already has a rule.", text_color=COLORS["danger"])
            return

        db.add_blocklist_entry(keyword, category)
        self.block_keyword_entry.delete(0, "end")
        self.block_category_entry.delete(0, "end")
        self.blocking_status.configure(text="Blocking rule added.", text_color=COLORS["sky"])
        self.refresh_blocking_rules()

    def remove_blocking_rule(self, entry_id):
        db.remove_blocklist_entry(entry_id)
        self.blocking_status.configure(text="Blocking rule removed.", text_color=COLORS["sky"])
        self.refresh_blocking_rules()

    def _get_all_connected_ips(self):
        connected = getattr(self.master_app, "connected_students", {})
        roles = getattr(self.master_app, "entity_roles", {})
        ips = [ip for ip in connected.keys() if roles.get(ip, "student") != "teacher"]
        return ips

    def sleep_all(self):
        ips = self._get_all_connected_ips()
        if not messagebox.askyesno("Confirm Sleep", f"Put {len(ips)} student PC(s) to sleep?"):
            return
        succeeded = sum(send_command(ip, "SLEEP") for ip in ips)
        self.status_label.configure(text=f"Sleep sent to {succeeded}/{len(ips)} PC(s).", text_color=COLORS["sky"])

    def restart_all(self):
        ips = self._get_all_connected_ips()
        if not messagebox.askyesno("Confirm Restart", f"Restart {len(ips)} student PC(s)? Their login will remain active."):
            return
        succeeded = sum(send_command(ip, "REBOOT") for ip in ips)
        self.status_label.configure(text=f"Restart sent to {succeeded}/{len(ips)} PC(s).", text_color=COLORS["sky"])

    def shutdown_all(self):
        ips = self._get_all_connected_ips()
        if not messagebox.askyesno("Confirm Shutdown", f"Shutdown {len(ips)} student PC(s) and force logout?"):
            return
        succeeded = sum(send_command(ip, "SHUTDOWN") for ip in ips)
        self.status_label.configure(text=f"Shutdown sent to {succeeded}/{len(ips)} PC(s).", text_color=COLORS["sky"])

    def add_inventory_item_ui(self):
        name = self.inv_item_name.get().strip()
        qty_str = self.inv_item_qty.get().strip()

        if not name or not qty_str.isdigit():
            self.inv_status_label.configure(text="Enter a name and a valid quantity.", text_color="orange")
            return

        existing = [i for i in db.get_all_inventory_items() if i["name"].lower() == name.lower()]
        if existing:
            self.inv_status_label.configure(text="Item already exists.", text_color=COLORS["danger"])
            return

        db.add_inventory_item(name, int(qty_str))
        self.inv_status_label.configure(text=f"Added '{name}' (x{qty_str}).", text_color=COLORS["sky"])
        self.inv_item_name.delete(0, "end")
        self.inv_item_qty.delete(0, "end")
        self.refresh_inventory_ui()

    def borrow_item_ui(self):
        selected = self.inv_item_dropdown.get()
        item_id = self.inv_item_map.get(selected)
        borrower = self.inv_borrower_name.get().strip()
        qty_str = self.inv_borrow_qty.get().strip()

        if not item_id or not borrower or not qty_str.isdigit():
            self.inv_status_label.configure(text="Fill in item, borrower, and quantity.", text_color="orange")
            return

        ok, err = db.borrow_item(item_id, borrower, int(qty_str))
        if ok:
            self.inv_status_label.configure(text=f"'{borrower}' borrowed {qty_str}x {selected}.", text_color=COLORS["sky"])
            self.inv_borrower_name.delete(0, "end")
            self.inv_borrow_qty.delete(0, "end")
        else:
            self.inv_status_label.configure(text=err, text_color=COLORS["danger"])
        self.refresh_inventory_ui()

    def return_item_ui(self, borrow_id):
        db.return_item(borrow_id)
        self.refresh_inventory_ui()

    def refresh_inventory_ui(self):
        for widget in self.inv_items_frame.winfo_children():
            widget.destroy()
        for widget in self.inv_active_frame.winfo_children():
            widget.destroy()

        items = db.get_all_inventory_items()
        self.inv_item_map = {i["name"]: i["id"] for i in items}
        if items:
            self.inv_item_dropdown.configure(values=list(self.inv_item_map.keys()))
            self.inv_item_dropdown.set(list(self.inv_item_map.keys())[0])
        else:
            self.inv_item_dropdown.configure(values=["No items yet"])
            self.inv_item_dropdown.set("No items yet")

        if not items:
            ctk.CTkLabel(self.inv_items_frame, text="No items added yet.", text_color="gray").pack(pady=10)
        for item in items:
            text = f"{item['name']} — {item['quantity_available']} / {item['quantity_total']} available"
            ctk.CTkLabel(self.inv_items_frame, text=text, anchor="w").pack(fill="x", padx=10, pady=3)

        active = db.get_active_borrows()
        if not active:
            ctk.CTkLabel(self.inv_active_frame, text="Nothing currently borrowed.", text_color="gray").pack(pady=10)
        for record in active:
            frm = ctk.CTkFrame(self.inv_active_frame)
            frm.pack(fill="x", padx=5, pady=4)
            text = f"{record['item_name']} x{record['quantity']} — {record['borrower_name']} (since {record['borrowed_at']})"
            ctk.CTkLabel(frm, text=text, anchor="w").pack(side="left", padx=10, pady=6, fill="x", expand=True)
            ctk.CTkButton(frm, text="Mark Returned", fg_color=COLORS["blue"], hover_color=COLORS["blue_hover"], width=110,
                        command=lambda bid=record["id"]: self.return_item_ui(bid)).pack(side="right", padx=10)

    def show_context_menu(self, event, ip, name, role="student"):
        context_menu = tk.Menu(self, tearoff=0, bg="#f0f0f0", fg="black", font=("Arial", 10))
        context_menu.add_command(label="Remote View", command=lambda: self.open_full_view(ip, is_control=False))

        if role != "teacher":
            context_menu.add_separator()
            context_menu.add_command(label="Lock", command=lambda: send_command(ip, "LOCK"))
            context_menu.add_command(label="Unlock", command=lambda: send_command(ip, "UNLOCK"))

        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def open_full_view(self, student_ip, is_control=False):
        try:
            if student_ip in self.active_viewers:
                try:
                    self.active_viewers[student_ip].destroy()
                except Exception:
                    pass
            viewer = ScreenViewer(student_ip, control_mode=is_control)
            self.active_viewers[student_ip] = viewer

            def on_viewer_close():
                if student_ip in self.active_viewers:
                    del self.active_viewers[student_ip]
                viewer.destroy()

            viewer.protocol("WM_DELETE_WINDOW", on_viewer_close)
        except Exception as e:
            print(f"Error sa pagbubukas ng ScreenViewer: {e}")