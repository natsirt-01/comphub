# config.py
import customtkinter as ctk
from tkinter import ttk

COLORS = {
    "navy": "#2b1745",
    "navy_deep": "#1c102d",
    "navy_panel": "#493064",
    "blue": "#55b9e8",
    "blue_hover": "#319dce",
    "sky": "#55b9e8",
    "pink": "#e76aa9",
    "pink_hover": "#ca4e90",
    "surface": "#fbf7fc",
    "surface_alt": "#f0e8f5",
    "ink": "#2e2340",
    "muted": "#786b88",
    "white": "#ffffff",
    "danger": "#df4f92",
    "warning": "#e77ab1",
    "success": "#269fc4",
}

def apply_theme():
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")


def apply_widget_theme(window):
    style = ttk.Style(window)
    style.theme_use("clam")
    style.configure(
        "Treeview",
        background=COLORS["white"],
        fieldbackground=COLORS["white"],
        foreground=COLORS["ink"],
        rowheight=30,
        borderwidth=0,
        font=("Segoe UI", 10),
    )
    style.configure(
        "Treeview.Heading",
        background=COLORS["navy_panel"],
        foreground=COLORS["white"],
        font=("Segoe UI", 10, "bold"),
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", COLORS["sky"])],
        foreground=[("selected", COLORS["navy_deep"])],
    )


def maximize_window(window):
    """Use a maximized window while retaining the normal Windows title bar."""
    window.after(50, lambda: window.state("zoomed"))