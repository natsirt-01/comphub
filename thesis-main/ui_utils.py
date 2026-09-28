def center_window(win, width, height):
    """Centers any Tk/CTk window (main window or Toplevel) on the screen,
    and sets its size. Call this instead of win.geometry('WxH')."""
    win.update_idletasks()
    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    win.geometry(f"{width}x{height}+{x}+{y}")