import customtkinter as ctk

COLORS = {
    "navy": "#0b1f3a",
    "navy_panel": "#102b4c",
    "blue": "#2878c8",
    "blue_hover": "#1d5fa5",
    "surface": "#f4f7fb",
    "ink": "#102238",
    "muted": "#64748b",
    "white": "#ffffff",
    "danger": "#c83c4a",
}


def apply_theme():
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")


def maximize_window(window):
    window.after(50, lambda: window.state("zoomed"))


def center_window(win, width, height):
    """Centers any Tk/CTk window (main window or Toplevel) on the screen,
    and sets its size. Call this instead of win.geometry('WxH')."""
    win.update_idletasks()
    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    win.geometry(f"{width}x{height}+{x}+{y}")