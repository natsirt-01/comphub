# config.py
import customtkinter as ctk

COLORS = {
    "navy": "#0b1f3a",
    "navy_deep": "#071529",
    "navy_panel": "#102b4c",
    "blue": "#2878c8",
    "blue_hover": "#1d5fa5",
    "surface": "#f4f7fb",
    "surface_alt": "#e7eef7",
    "ink": "#102238",
    "muted": "#64748b",
    "white": "#ffffff",
    "danger": "#c83c4a",
    "warning": "#c58a16",
    "success": "#238b68",
}

def apply_theme():
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")


def maximize_window(window):
    """Use a maximized window while retaining the normal Windows title bar."""
    window.after(50, lambda: window.state("zoomed"))