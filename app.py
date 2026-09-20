import os
import sys
import time
import io
import json
import threading
import base64
import requests
import win32clipboard
from datetime import datetime
from PIL import Image, ImageGrab, ImageDraw, ImageTk
from plyer import notification
import tkinter as tk
import pystray
from pystray import MenuItem as item

# ------------------------------------------------------------------
# Dynamic Configuration Loader (PyInstaller Safe)
# ------------------------------------------------------------------
def get_base_path():
    """Returns the actual folder path whether running as .py or compiled .exe"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(get_base_path(), "config.json")

def load_config():
    """Loads API endpoint and key from local config.json file."""
    default_config = {
        "AWS_API_ENDPOINT": "https://YOUR_API_GATEWAY_URL.execute-api.ap-south-1.amazonaws.com/default/RadarRedactionEngine",
        "X_API_KEY": "YOUR_API_KEY_HERE"
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            
    return default_config

config = load_config()
AWS_API_ENDPOINT = config.get("AWS_API_ENDPOINT")
X_API_KEY = config.get("X_API_KEY")

# ------------------------------------------------------------------
# Global State & Configuration
# ------------------------------------------------------------------
IS_RUNNING = True
IS_PAUSED = False
LAST_IMAGE_HASH = None

# Local History Storage (Hidden in AppData)
HISTORY_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'ShareSafe_History')
os.makedirs(HISTORY_DIR, exist_ok=True)

# ------------------------------------------------------------------
# OS & File Helper Functions
# ------------------------------------------------------------------
def cleanup_old_history():
    """Deletes images older than 24 hours to maintain the Zero-Retention promise."""
    now = time.time()
    for filename in os.listdir(HISTORY_DIR):
        file_path = os.path.join(HISTORY_DIR, filename)
        if os.path.isfile(file_path):
            if os.stat(file_path).st_mtime < now - (24 * 3600):
                try:
                    os.remove(file_path)
                except Exception:
                    pass

def set_clipboard_image(image: Image.Image):
    output = io.BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()
    
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()

def trigger_toast(title: str, message: str):
    try:
        notification.notify(title=title, message=message, app_name="ShareSafe Radar", timeout=3)
    except:
        pass

# ------------------------------------------------------------------
# Background Clipboard Monitor Loop
# ------------------------------------------------------------------
def clipboard_monitor_thread(gui_app):
    global LAST_IMAGE_HASH, IS_RUNNING, IS_PAUSED
    
    cleanup_old_history()
    
    while IS_RUNNING:
        if not IS_PAUSED:
            try:
                img = ImageGrab.grabclipboard()
                
                if isinstance(img, Image.Image):
                    img_bytes = img.tobytes()
                    current_hash = hash(img_bytes)
                    
                    if current_hash != LAST_IMAGE_HASH:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        orig_path = os.path.join(HISTORY_DIR, f"orig_{timestamp}.png")
                        
                        img.convert("RGB").save(orig_path, "PNG")
                        
                        output = io.BytesIO()
                        img.convert("RGB").save(output, "PNG")
                        b64_img = base64.b64encode(output.getvalue()).decode('utf-8')
                        
                        payload = {"image_base64": b64_img}
                        headers = {
                            "x-api-key": X_API_KEY,
                            "Content-Type": "application/json"
                        }
                        
                        try:
                            response = requests.post(AWS_API_ENDPOINT, json=payload, headers=headers, timeout=10)
                            
                            if response.status_code == 200:
                                result = response.json()
                                if result.get("leak_detected"):
                                    safe_b64 = result.get("redacted_image")
                                    safe_bytes = base64.b64decode(safe_b64)
                                    safe_img = Image.open(io.BytesIO(safe_bytes))
                                    
                                    set_clipboard_image(safe_img)
                                    LAST_IMAGE_HASH = hash(safe_img.tobytes())
                                    
                                    gui_app.add_history_entry(timestamp, orig_path, "Redacted")
                                    trigger_toast("ShareSafe Radar", "Sensitive data redacted from clipboard!")
                                else:
                                    gui_app.add_history_entry(timestamp, orig_path, "Clean")
                                    LAST_IMAGE_HASH = current_hash
                            else:
                                LAST_IMAGE_HASH = current_hash
                        except requests.exceptions.RequestException:
                            # Network or timeout error
                            LAST_IMAGE_HASH = current_hash
            except Exception:
                pass
                
        time.sleep(0.8)

# ------------------------------------------------------------------
# Modern UI & System Tray Integration
# ------------------------------------------------------------------
class RadarGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ShareSafe Radar")
        self.root.geometry("600x350")
        self.root.resizable(False, False)
        self.root.configure(bg="#1E1E1E")
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        
        # --- Left Panel ---
        left_frame = tk.Frame(root, bg="#1E1E1E", width=220)
        left_frame.pack(side="left", fill="y", padx=15, pady=15)
        
        self.title_label = tk.Label(left_frame, text="Radar Engine", font=("Segoe UI", 14, "bold"), bg="#1E1E1E", fg="white")
        self.title_label.pack(pady=(5, 10))
        
        self.toggle_btn = tk.Button(
            left_frame, text="🟢 ACTIVE", font=("Segoe UI", 10, "bold"),
            bg="#2EA043", fg="white", activebackground="#238636", activeforeground="white",
            relief="flat", width=18, command=self.toggle_service, cursor="hand2"
        )
        self.toggle_btn.pack(pady=5)
        
        history_label = tk.Label(left_frame, text="Recent Scans (24h)", font=("Segoe UI", 9), bg="#1E1E1E", fg="#AAAAAA")
        history_label.pack(anchor="w", pady=(15, 2))
        
        self.history_list = tk.Listbox(left_frame, bg="#2D2D2D", fg="white", selectbackground="#388BFD", relief="flat", borderwidth=0, font=("Segoe UI", 9), height=10)
        self.history_list.pack(fill="both", expand=True)
        self.history_list.bind('<<ListboxSelect>>', self.on_select_history)
        self.history_paths = {} 
        
        # --- Right Panel ---
        right_frame = tk.Frame(root, bg="#2D2D2D")
        right_frame.pack(side="right", fill="both", expand=True, padx=(0, 15), pady=15)
        
        preview_title = tk.Label(right_frame, text="Original Image Preview", font=("Segoe UI", 10, "bold"), bg="#2D2D2D", fg="white")
        preview_title.pack(pady=(10, 5))
        
        self.img_preview_label = tk.Label(right_frame, bg="#1E1E1E", text="Select a scan to preview", fg="#777777", font=("Segoe UI", 9))
        self.img_preview_label.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.view_btn = tk.Button(
            right_frame, text="Open Full Original", font=("Segoe UI", 9),
            bg="#388BFD", fg="white", relief="flat", command=self.open_original, cursor="hand2", state="disabled"
        )
        self.view_btn.pack(pady=(5, 10))
        
        self.tray_icon = self.create_tray_icon()

    def add_history_entry(self, timestamp, file_path, status):
        time_formatted = datetime.strptime(timestamp, "%Y%m%d_%H%M%S").strftime("%I:%M:%S %p")
        display_text = f"[{status}] {time_formatted}"
        
        self.history_list.insert(0, display_text)
        
        new_paths = {0: file_path}
        for idx, path in self.history_paths.items():
            new_paths[idx + 1] = path
        self.history_paths = new_paths

    def on_select_history(self, event):
        selection = self.history_list.curselection()
        if selection:
            self.view_btn.config(state="normal")
            index = selection[0]
            path = self.history_paths.get(index)
            
            if path and os.path.exists(path):
                try:
                    with Image.open(path) as img:
                        img_copy = img.copy()
                    
                    img_copy.thumbnail((320, 220), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img_copy)
                    self.img_preview_label.config(image=photo, text="")
                    self.img_preview_label.image = photo 
                except Exception:
                    self.img_preview_label.config(image='', text="Preview not available")

    def open_original(self):
        selection = self.history_list.curselection()
        if selection:
            path = self.history_paths.get(selection[0])
            if path and os.path.exists(path):
                try:
                    clean_path = os.path.normpath(path)
                    os.startfile(clean_path)
                except Exception:
                    import subprocess
                    subprocess.run(['explorer', clean_path])

    def toggle_service(self):
        global IS_PAUSED
        IS_PAUSED = not IS_PAUSED
        if IS_PAUSED:
            self.toggle_btn.config(text="🔴 PAUSED", bg="#DA3633", activebackground="#B62324")
        else:
            self.toggle_btn.config(text="🟢 ACTIVE", bg="#2EA043", activebackground="#238636")

    def create_tray_icon(self):
        image = Image.new('RGB', (64, 64), color=(0, 51, 102))
        draw = ImageDraw.Draw(image)
        draw.rectangle([16, 16, 48, 48], fill=(0, 204, 102))
        
        menu = pystray.Menu(
            item('Open Dashboard', self.show_window),
            item('Exit ShareSafe', self.quit_app)
        )
        return pystray.Icon("sharesafe", image, "ShareSafe Radar", menu)

    def hide_window(self):
        self.root.withdraw()
        trigger_toast("ShareSafe Radar", "Running in background. Click tray icon to open.")

    def show_window(self, icon=None, item=None):
        self.root.deiconify()

    def quit_app(self, icon=None, item=None):
        global IS_RUNNING
        IS_RUNNING = False
        self.tray_icon.stop()
        self.root.quit()

# ------------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = RadarGUI(root)
    
    monitor = threading.Thread(target=clipboard_monitor_thread, args=(app,), daemon=True)
    monitor.start()
    
    threading.Thread(target=app.tray_icon.run, daemon=True).start()
    
    root.mainloop()