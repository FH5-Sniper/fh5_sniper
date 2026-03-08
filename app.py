import ttkbootstrap as tb
from ttkbootstrap.constants import *
from tkinter import scrolledtext
import tkinter as tk

import threading
import calibrator
import sniper
import settings
import logger
import vision_utils
from PIL import Image, ImageTk
import window_utils
import ctypes
import webbrowser

# optional requests availability (used for update checks)
try:
    import requests  # type: ignore
    HAVE_REQUESTS = True
except Exception:
    requests = None
    HAVE_REQUESTS = False

# application version
__version__ = "1.0.5"

# path to the static icon file (created once and checked into repo)
_icon_file = window_utils.resource_path("assets/sniper.ico")

# --- DPI AWARENESS (IMPORTANT FOR PYAUTOGUI) ---
try:
    ctypes.windll.user32.SetProcessDPIAware()
    print("✅ DPI awareness enabled")
except Exception:
    print("⚠️  Could not set DPI awareness (may be normal on some systems)")

sniper_running = False
stop_flag = {"stop": False}
timer_running = False
timer_elapsed = 0
buy_attempts = 0
buy_successes = 0
buy_failures = 0
buy_refreshes = 0
current_total_scans = 0
calibration_done_this_session = False

# --- DEFAULT REGION ---

DEFAULT_REGION = calibrator.load_region()

# --- CONFIG SAVE ---
CONFIG_FILE = window_utils.get_config_file()


# optional auto-update checker (stub)
def check_for_updates():
    """Query GitHub releases and return (latest_tag_or_None, error_or_None).

    Error values: 'missing_requests', 'network', 'http', or None on success/no-error.
    """
    def _norm(v):
        if not v:
            return None
        return str(v).lstrip("vV").strip()

    def _is_newer(latest, current):
        # safe semver-ish comparison: compare numeric components
        try:
            la = tuple(int(x) for x in _norm(latest).split("."))
            cu = tuple(int(x) for x in _norm(current).split("."))
            return la > cu
        except Exception:
            return _norm(latest) != _norm(current)

    if not HAVE_REQUESTS:
        logger.update_log("⚠️ Update check skipped: 'requests' not available")
        return None, "missing_requests"

    url = "https://api.github.com/repos/FH5-Sniper/fh5_sniper/releases/latest"
    try:
        resp = requests.get(url, timeout=3)
    except Exception:
        logger.update_log("⚠️ Update check failed (network error)")
        return None, "network"

    if not resp.ok:
        logger.update_log(f"⚠️ Update check HTTP error: {resp.status_code}")
        return None, "http"

    try:
        latest = resp.json().get("tag_name")
        if latest and _is_newer(latest, __version__):
            logger.update_log(f"🔄 New version available: {latest} (current {__version__})")
            return str(latest), None
        # no newer release
        logger.update_log("✅ No updates found")
        return None, None
    except Exception:
        logger.update_log("⚠️ Update check failed (parsing error)")
        return None, "network"


def show_update_popup(latest_tag):
    try:
        popup = tk.Toplevel(root)
        popup.title("Update Available")
        popup.transient(root)
        popup.grab_set()
        
        # Set icon for popup
        try:
            popup.iconbitmap(_icon_file)
        except Exception:
            pass

        tb.Label(popup, text=f"New version available: {latest_tag}", font=("Arial", 12, "bold")).pack(padx=20, pady=(12,6))
        tb.Label(popup, text=f"Current version: {__version__}", font=("Arial", 10)).pack(padx=20, pady=(0,10))

        def open_release():
            import webbrowser
            webbrowser.open("https://github.com/FH5-Sniper/fh5_sniper/releases/latest")
            popup.destroy()

        btn_frame = tb.Frame(popup)
        btn_frame.pack(pady=(6,12))
        tb.Button(btn_frame, text="Open Releases", command=open_release, bootstyle=INFO).pack(side="left", padx=6)
        tb.Button(btn_frame, text="Dismiss", command=popup.destroy, bootstyle=SECONDARY).pack(side="left", padx=6)

        popup.protocol("WM_DELETE_WINDOW", popup.destroy)
        root.wait_window(popup)
    except Exception:
        # UI failed; ignore
        pass

# --- BUILD UI ---

# ---------- Main Window ----------

root = tb.Window(themename="cyborg")
root.title("FH5 Sniper")

try:
    root.iconbitmap(_icon_file)
except Exception:
    pass
root.geometry("930x740")
root.maxsize(1400, 740)  # Max height of 740px, max width of 1400px

# style tweaks for more modern appearance and better readability
style = tb.Style()
style.configure('TButton', font=('Arial', 11), padding=6)
style.configure('TLabel', font=('Arial', 11))

# global exception hook for uncaught errors
import sys

def handle_exception(exc_type, exc_value, exc_traceback):
    # allow keyboard interrupts through
    if exc_type == KeyboardInterrupt:
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    try:
        logger.update_log(f"🔴 Unhandled exception: {exc_value}")
    except Exception:
        pass

sys.excepthook = handle_exception

# Track if this is the first sniper start in this app session
first_sniper_session_start = True

# Top row: notebook on the left, quick actions (updates) on the right
top_row = tb.Frame(root)
top_row.pack(fill="x", padx=10, pady=10)

notebook = tb.Notebook(top_row)
notebook.pack(side="left", fill="both", expand=True)

# ---------- Sniper Tab ----------
sniper_tab = tb.Frame(notebook)
notebook.add(sniper_tab, text="Sniper")

def update_timer():
    global timer_running, timer_elapsed
    if timer_running:
        timer_elapsed += 1
        hours = timer_elapsed // 3600
        minutes = (timer_elapsed % 3600) // 60
        seconds = timer_elapsed % 60
        if hours > 0:
            timer_label.config(text=f"⏱️  {hours}:{minutes:02d}:{seconds:02d}")
        else:
            timer_label.config(text=f"⏱️  {minutes:02d}:{seconds:02d}")
        root.after(1000, update_timer)

def show_recalibration_reminder():
    """Display modal popup reminding user to recalibrate after restarting FH5.
    
    This popup appears only on the first sniper start of the app session.
    """
    popup = tk.Toplevel(root)
    popup.title("Recalibration Recommended")
    popup.transient(root)
    popup.grab_set()
    popup.resizable(False, False)
    
    # Set icon for popup
    try:
        popup.iconbitmap(_icon_file)
    except Exception:
        pass

    title = tb.Label(popup, text="Recalibration Recommended", font=("Arial", 13, "bold"))
    title.pack(padx=20, pady=(20, 10))

    message = (
        "If you have closed and reopened Forza Horizon 5 or started a new gaming session,\n"
        "the window position or size may have changed.\n\n"
        "For optimal detection performance, we recommend running calibration again.\n"
        "This ensures the sniper can accurately locate the Auction Options button."
    )
    
    tb.Label(popup, text=message, font=("Arial", 10), justify="center").pack(padx=20, pady=(0, 20))

    dont_show_var = tk.BooleanVar()
    tb.Checkbutton(popup, text="Don't show this reminder again", variable=dont_show_var).pack(pady=(0, 15))

    button_frame = tb.Frame(popup)
    button_frame.pack(pady=(0, 20))

    def on_continue():
        if dont_show_var.get():
            settings.set_skip_recalibration_reminder(True)
        popup.destroy()

    def on_calibrate():
        global sniper_running
        sniper_running = False
        if dont_show_var.get():
            settings.set_skip_recalibration_reminder(True)
        popup.destroy()
        notebook.select(1)  # Switch to Calibration tab (index 1)

    continue_button = tb.Button(button_frame, text="Continue Without Calibration", width=25, command=on_continue)
    continue_button.pack(side="left", padx=5)

    calibrate_button = tb.Button(button_frame, text="Calibrate Now", width=15, command=on_calibrate, bootstyle=PRIMARY)
    calibrate_button.pack(side="left", padx=5)

    popup.protocol("WM_DELETE_WINDOW", on_continue)
    root.wait_window(popup)


def show_calibration_warning():
    """Display modal popup reminding user to perform manual calibration.

    Returns when the user dismisses the dialog. If the "don't show again"
    checkbox is ticked, the preference is saved via settings.set_skip_calibration_warning.
    """
    popup = tk.Toplevel(root)
    popup.title("Calibration Required")
    popup.transient(root)
    popup.grab_set()
    popup.resizable(False, False)
    
    # Set icon for popup
    try:
        popup.iconbitmap(_icon_file)
    except Exception:
        pass

    title = tb.Label(popup, text="No Calibration Detected", font=("Arial", 13, "bold"))
    title.pack(padx=20, pady=(20, 10))

    tb.Label(popup, text="Calibration has not been performed.", font=("Arial", 11)).pack(padx=20, pady=(0, 8))
    tb.Label(
        popup,
        text="For faster and more accurate scans, we recommend running either\nauto or manual calibration before starting the sniper.",
        font=("Arial", 10),
        justify="center"
    ).pack(padx=20, pady=(0, 15))

    dont_show_var = tk.BooleanVar()
    tb.Checkbutton(popup, text="Don't show this warning again", variable=dont_show_var).pack(pady=(0, 15))

    def on_continue():
        settings.set_skip_calibration_warning(True)  # Always skip after continuing
        popup.destroy()

    def on_calibrate_cancel():
        # Stop sniper and switch to calibration tab
        global sniper_running
        sniper_running = False
        if dont_show_var.get():
            settings.set_skip_calibration_warning(True)
        popup.destroy()
        notebook.select(1)  # Switch to Calibration tab (index 1)

    button_frame = tb.Frame(popup)
    button_frame.pack(pady=(0, 20))

    continue_button = tb.Button(button_frame, text="Continue Without Calibration", width=25, command=on_continue)
    continue_button.pack(side="left", padx=5)

    calibrate_button = tb.Button(button_frame, text="Cancel & Calibrate", width=15, command=on_calibrate_cancel, bootstyle=DANGER)
    calibrate_button.pack(side="left", padx=5)

    popup.protocol("WM_DELETE_WINDOW", on_continue)
    root.wait_window(popup)


def start_sniper_ui():
    global sniper_running, stop_flag, timer_running, timer_elapsed, buy_attempts, buy_successes, buy_failures, first_sniper_session_start, calibration_done_this_session
    if sniper_running:
        logger.update_log("⚠️ Sniper already running!")
        return
    
    # Show recalibration reminder on first sniper start of this session, but skip if calibration was done this session
    if first_sniper_session_start and not settings.get_skip_recalibration_reminder() and not calibration_done_this_session:
        first_sniper_session_start = False
        show_recalibration_reminder()
        # Check if user clicked "Calibrate Now" which sets sniper_running to False
        if not sniper_running:
            return
    
    # warn the user if calibration hasn't been done and they haven't opted out
    if not calibrator.has_manual_region() and not calibrator.has_auto_region() and not settings.get_skip_calibration_warning():
        show_calibration_warning()
        # If user clicked Cancel & Calibrate, sniper_running is False, so return
        if not sniper_running:
            return

    sniper_running = True
    timer_running = False
    timer_elapsed = 0
    stop_flag["stop"] = False

    # Reset attempt stats and update UI
    buy_attempts = 0
    buy_successes = 0
    buy_failures = 0
    buy_scans = 0


    # load settings and region values before we use them
    region = calibrator.load_region()
    scans = settings.get_scans()
    timings = settings.load_timings()

    # store total scan count so we can show "scans left"
    global current_total_scans
    current_total_scans = scans
    buy_stats_label.config(text=f"Buy attempts: {buy_attempts} | Success: {buy_successes} | Fail: {buy_failures} | Scans: {buy_scans}")
    scans_left_label.config(text=f"Scans left: {max(current_total_scans - buy_attempts, 0)}")

    # Start sniper thread; status updates will be sent back via update_stats
    threading.Thread(
        target=sniper_thread_ui,
        args=(region, scans, timings, update_stats),
        daemon=True
    ).start()

    # Start timer after the same 5s countdown the sniper shows
    def begin_timer_after_countdown():
        global timer_running, timer_elapsed
        if sniper_running and not stop_flag.get("stop", False):
            timer_elapsed = 0
            timer_running = True
            update_timer()

    root.after(5000, begin_timer_after_countdown)


def update_stats(attempts_count, successes, failures, refresh_count=0, scans_done=0):
    # Called from sniper thread; marshal UI updates to main thread
    def _update():
        global buy_attempts, buy_successes, buy_failures
        buy_attempts = attempts_count
        buy_successes = successes
        buy_failures = failures
        globals()['buy_refreshes'] = refresh_count
        buy_stats_label.config(text=f"Buy attempts: {buy_attempts} | Success: {buy_successes} | Fail: {buy_failures} | Refreshes: {refresh_count}")
        # update scans left using scans_done
        try:
            remaining = max(current_total_scans - scans_done, 0)
        except Exception:
            remaining = 0
        scans_left_label.config(text=f"Scans left: {remaining}")
    root.after(0, _update)

def sniper_thread_ui(region, scans, timings, status_callback):
    global sniper_running, timer_running
    try:
        start_button.config(state=DISABLED)
        stop_button.config(state=NORMAL)
  
        sniper.sniper_loop(logger.update_log, region, scans, timings, stop_flag, status_callback)

    except Exception as e:
        logger.update_log(f"❌ Error: {e}")

    finally:
        sniper_running = False
        timer_running = False
        stop_flag["stop"] = False
        stop_flag["requested"] = False
        start_button.config(state=NORMAL)
        stop_button.config(state=DISABLED)
        logger.update_log("✅ Sniper stopped")

def stop_sniper_ui():
    global timer_running
    if sniper_running and not stop_flag.get("requested", False):
        timer_running = False
        stop_flag["stop"] = True
        stop_flag["requested"] = True
        logger.update_log("🛑 Stop requested...")
        stop_button.config(state=DISABLED)
    elif not sniper_running:
        logger.update_log("⚠️ Sniper is not running")

# Control frame with buttons (stacked), centered title, and timer to the right
control_frame = tb.Frame(sniper_tab)
control_frame.pack(fill="x", padx=10, pady=10)

# Left: buttons stacked vertically
buttons_frame = tb.Frame(control_frame)
buttons_frame.pack(side="left", fill="y", padx=(0,10))

start_button = tb.Button(
    buttons_frame,
    text="Start Sniper",
    command=start_sniper_ui,
    bootstyle=SUCCESS,
    width=12
)
start_button.pack(side="top", pady=3)


stop_button = tb.Button(
    buttons_frame,
    text="Stop Sniper",
    command=stop_sniper_ui,
    bootstyle=DANGER,
    width=12,
    state=DISABLED  # initially disabled until sniper is running
)
stop_button.pack(side="top", pady=3)

# keyboard accessibility: Alt+S to start, Alt+T to stop
root.bind('<Alt-s>', lambda e: start_sniper_ui())
root.bind('<Alt-S>', lambda e: start_sniper_ui())
root.bind('<Alt-t>', lambda e: stop_sniper_ui())
root.bind('<Alt-T>', lambda e: stop_sniper_ui())

# Center: title label (keeps centered by giving this frame expanding space)
center_frame = tb.Frame(control_frame)
center_frame.pack(side="left", expand=True)
sniper_title_label = tb.Label(center_frame, text="Sniper Controls", font=("Arial", 14, "bold"))
sniper_title_label.pack()

# Right: Timer
timer_label = tb.Label(control_frame, text="⏱️  00:00", font=("Arial", 14, "bold"))
timer_label.pack(side="right", padx=10)

# Stats row below the controls (left: buy stats, right: scans left)
stats_frame = tb.Frame(sniper_tab)
stats_frame.pack(fill="x", padx=10)

buy_stats_label = tb.Label(stats_frame, text="Buy attempts: 0 | Success: 0 | Fail: 0 | Refreshes: 0", font=("Arial", 12))
buy_stats_label.pack(side="left", anchor="w")

scans_left_label = tb.Label(stats_frame, text=f"Scans left: {settings.get_scans()}", font=("Arial", 12))
scans_left_label.pack(side="right", anchor="e")

# set initial total scans (for label init)
current_total_scans = settings.get_scans()

# Log frame
log_frame = tb.Labelframe(sniper_tab, text="Status Log", bootstyle=SUCCESS)
log_frame.pack(fill="both", expand=True, padx=10, pady=10)

# ScrolledText widget for logs
log_text = scrolledtext.ScrolledText(log_frame, wrap="word", height=12)
log_text.pack(fill="both", expand=True, padx=5, pady=5)

# Insert initial message
log_text.insert("end", "Ready...\n")
log_text.configure(state='disabled')  # make it read-only

# Initialize logger with the ScrolledText widget
logger.init_logger(log_text)

# ---------- Calibration Tab ----------
calib_tab = tb.Frame(notebook)
notebook.add(calib_tab, text="Calibration")

tb.Label(calib_tab, text="Calibration Wizard", font=("Arial", 14, "bold")).pack(pady=10)

# Section: Instructions for FH5
calibration_instructions = (
    "Make sure Forza Horizon 5 is running in windowed mode (Alt + Enter).\n"
    "You can resize the window so it’s smaller and easier to work with.\n"
    "Go to the Auction House and make sure the 'Auction Options' button is visible.\n\n"
    "During calibration:\n"
    "1. Move your mouse over the top-left corner of the 'Auction Options' button.\n"
    "2. Then, move your mouse over the bottom-right corner of the button.\n\n"
)

# brief explanation about calibration vs automatic detection
calib_explain = (
    "Calibration allows the sniper to focus on a smaller region, making each scan much faster.\n"
    "Auto calibration is the fastest option.\n"
    "If no calibration exists, the app falls back to the built-in detection logic, which scans wider areas and takes slightly longer per attempt.\n"
)

calib_explain_label = tb.Label(
    calib_tab,
    text=calib_explain,
    font=("Arial", 11, "italic"),
    wraplength=900,
    justify="center"
)
calib_explain_label.pack(pady=(10, 5))

# We'll place the status and test labels inside a bordered box below the
# Run/Remove calibration controls so they're visually grouped.


# utility for info popups
def show_info(title, message, image_path=None):
    info = tk.Toplevel(root)
    info.title(title)
    info.resizable(False, False)
    info.attributes("-topmost", True)
    
    # Set icon for popup
    try:
        info.iconbitmap(_icon_file)
    except Exception:
        pass

    # message text
    lbl = tb.Label(info, text=message, wraplength=380, justify=LEFT)
    lbl.pack(padx=10, pady=10, fill="x")

    # image + caption (your original label logic)
    if image_path:
        img_path = window_utils.resource_path(image_path)
        img = Image.open(img_path)
        photo = ImageTk.PhotoImage(img)

        img_label = tb.Label(
            info,  # 🔥 IMPORTANT: parent is the popup now
            image=photo,
            compound="top",
            bootstyle=INFO,
        )
        img_label.image = photo  # 🔥 keep reference
        img_label.pack(pady=10)

    btn = tb.Button(info, text="OK", command=info.destroy, bootstyle=SUCCESS)
    btn.pack(pady=5)

# Run calibration button
def run_calibration():
    global calibration_done_this_session
    region_test_label.config(text="")
    calibrator.calibrate(status_label=status_label, image_callback=update_calibration_image, error_label=region_test_label)

    # Check if calibration was successful
    if calibrator.has_manual_region():
        calibration_done_this_session = True
        # Automatically test region after calibration
        root.after(0, lambda: test_region_with_retry())

    # update UI in main thread
    root.after(0, update_status_label)
    root.after(0, update_button_states)
    root.after(0, lambda: logger.update_log("✅ Manual calibration complete"))

def run_auto_calibration():
    global calibration_done_this_session
    region_test_label.config(text="")
    success = calibrator.auto_calibrate(status_label=status_label)

    # update UI in main thread
    if success:
        calibration_done_this_session = True
        root.after(0, update_status_label)
        root.after(0, lambda: logger.update_log("✅ Auto calibration complete"))
    else:
        # Show error message and keep it visible
        status_label.after(0, lambda: status_label.config(
            text="Manual calibration: NOT SET\nAuto calibration: FAILED\nCalibration failed, try resizing the Forza Horizon 5 window to be either bigger or smaller to make sure the Auction Options button is detected.",
            bootstyle="danger"
        ))
        root.after(0, lambda: logger.update_log("❌ Auto calibration failed"))
    
    root.after(0, update_button_states)

# horizontal button frame
btn_frame = tb.Frame(calib_tab)
btn_frame.pack(pady=5, fill="x")

# Left group: Run Auto + Remove Auto (stacked vertically) with info buttons
left_group = tb.Frame(btn_frame)
# align with status box which uses padx=20
left_group.pack(side="left", anchor="n", padx=20)

auto_run_row = tb.Frame(left_group)
auto_run_row.pack(side="top", anchor="w")
auto_run_btn = tb.Button(auto_run_row, text="Run Auto Calibration", bootstyle=PRIMARY, width=22,
          command=lambda: threading.Thread(target=run_auto_calibration, daemon=True).start())
auto_run_btn.pack(side="left", padx=(5))
auto_info_run = tb.Button(auto_run_row, text="?", width=2, bootstyle="info-outline",
                     command=lambda: show_info(
                         "Auto Calibration",
                         "Auto calibration uses image recognition to automatically find the Auction Options button.\n\n"
                         "Make sure Forza Horizon 5 is running in windowed mode and the Auction Options button is visible.\n"
                         "The detection may take a few seconds. If it fails, try resizing the Forza Horizon 5 window.",
                         image_path="assets/auction_options_template.png"
                     ))
auto_info_run.pack(side="left")

def test_region_with_retry():
    """Test region with multiple template sizes. Called after calibration."""
    config_region = calibrator.load_region()
    manual_region = calibrator.load_region() if calibrator.has_manual_region() else None
    auto_region = calibrator.load_auto_region() if calibrator.has_auto_region() else None
    
    window = window_utils.get_fh5_window()
    if window:
        full = window_utils.get_window_region(window)
        default_reg = window_utils.bottom_left_quarter(full)
    else:
        default_reg = window_utils.bottom_left_quarter(config_region)
    
    # Use the same priority as sniper_loop
    if manual_region:
        test_reg = manual_region
        region_type = "manual calibrated"
    elif auto_region:
        test_reg = auto_region
        region_type = "auto calibrated"
    else:
        test_reg = default_reg
        region_type = "default (bottom-left quarter)"

    try:
        region_test_label.config(text="Testing calibration region (this may take a moment)...", bootstyle="info")
        root.update_idletasks()  # Force UI update to show the testing message
        logger.update_log("🔍 Testing calibration with all templates...")
        
        # Use the base template with multiple scales and confidences like auto calibration
        template_path = window_utils.resource_path("assets/auction_options_template.png")
        scales = [0.8, 0.9, 1.0, 1.1, 1.2]
        confidences = [0.65, 0.68, 0.7, 0.72]
        
        found_params = None
        
        for scale in scales:
            for confidence in confidences:
                print(f"[TEST] Trying scale={scale}, confidence={confidence}")
                
                try:
                    location = vision_utils.locate_on_screen_with_variants(
                        template_path, region=test_reg, confidence=confidence, scale_min=scale, scale_max=scale, scale_steps=1
                    )
                    
                    if location is not None:
                        found_params = (scale, confidence)
                        region_test_label.config(
                            text=f"✅ Calibration successful! Button detected (scale={scale}, conf={confidence})",
                            bootstyle="success"
                        )
                        logger.update_log(f"✅ Button found with scale={scale}, confidence={confidence}")
                        
                        # Save the successful parameters to config for manual calibration
                        config = settings.load_config()
                        config["MANUAL_TEMPLATE_INFO"] = {
                            "template_path": template_path,
                            "scale": scale,
                            "confidence": confidence
                        }
                        settings.save_config(config)
                        
                        return
                except Exception as e:
                    print(f"[ERROR] Exception testing scale={scale}, conf={confidence}: {e}")
                    continue
        
        # If we get here, no template worked - show simple error message
        region_test_label.config(
            text="❌ Button not detected. Please run calibration again.",
            bootstyle="danger"
        )
        logger.update_log("⚠️ Calibration test failed - trying all templates")
        
        # Show prompt to retry calibration
        retry_popup = tk.Toplevel(root)
        retry_popup.title("Retry Calibration")
        retry_popup.transient(root)
        retry_popup.grab_set()
        retry_popup.resizable(False, False)
        
        try:
            retry_popup.iconbitmap(window_utils.resource_path("assets/sniper.ico"))
        except Exception:
            pass

        tb.Label(retry_popup, text="Calibration Not Detected", font=("Arial", 11, "bold")).pack(padx=20, pady=(15, 10))
        tb.Label(retry_popup, text="The button could not be detected in the calibrated region.\nPlease try calibrating again.", 
                 font=("Arial", 10), justify="center").pack(padx=20, pady=(0, 15))

        btn_frame = tb.Frame(retry_popup)
        btn_frame.pack(pady=(0, 15))
        
        def retry_calibration():
            retry_popup.destroy()
            threading.Thread(target=run_calibration, daemon=True).start()
        
        tb.Button(btn_frame, text="Retry Calibration", command=retry_calibration, bootstyle=PRIMARY).pack(side="left", padx=5)
        tb.Button(btn_frame, text="Skip", command=retry_popup.destroy, bootstyle=SECONDARY).pack(side="left", padx=5)
        
        retry_popup.protocol("WM_DELETE_WINDOW", retry_popup.destroy)
        
    except Exception as e:
        print(f"[ERROR] test_region_with_retry exception: {e}")
        region_test_label.config(text=f"❌ Error: {e}", bootstyle="danger")

def test_region():
    # mimic sniper_loop's region priority: manual > auto > default
    config_region = calibrator.load_region()
    manual_region = calibrator.load_region() if calibrator.has_manual_region() else None
    auto_region = calibrator.load_auto_region() if calibrator.has_auto_region() else None
    
    window = window_utils.get_fh5_window()
    if window:
        full = window_utils.get_window_region(window)
        default_reg = window_utils.bottom_left_quarter(full)
    else:
        default_reg = window_utils.bottom_left_quarter(config_region)
    
    # Use the same priority as sniper_loop
    if manual_region:
        test_reg = manual_region
        region_type = "manual calibrated"
    elif auto_region:
        test_reg = auto_region
        region_type = "auto calibrated"
    else:
        test_reg = default_reg
        region_type = "default (bottom-left quarter)"

    try:
        found = sniper.car_available(test_reg)
        if found:
            region_test_label.config(text=f"Test Region Result: ✅ Button detected in {region_type} region", bootstyle="success")
        else:
            region_test_label.config(text=f"Test Region Result: ❌ Button NOT detected in {region_type} region", bootstyle="danger")

    except Exception as e:
        region_test_label.config(text=f"❌ Error testing region: {e}", bootstyle="danger")

def reset_auto_region_ui():
    region_test_label.config(text="")
    calibrator.reset_auto_region(status_label=status_label)
    update_status_label()
    update_button_states()
    logger.update_log("🔄 Auto region removed.")

auto_remove_row = tb.Frame(left_group)
auto_remove_row.pack(side="top", pady=4, anchor="w")
auto_reset_btn = tb.Button(auto_remove_row, text="Remove Auto Region",
    bootstyle=DANGER,
    command=reset_auto_region_ui,
    width=22)
auto_reset_btn.pack(side="left", padx=(5))
auto_info_remove = tb.Button(auto_remove_row, text="?", width=2, bootstyle="info-outline",
                         command=lambda: show_info("Remove Auto Region", 
"Clears any auto-calibrated region. "
"The sniper will revert to automatic detection which searches the entire window area."))
auto_info_remove.pack(side="left")

# Right group: Manual calibration + Test + Show overlay (stacked vertically)
right_group = tb.Frame(btn_frame)
right_group.pack(side="left", anchor="n", padx=20)

run_row = tb.Frame(right_group)
run_row.pack(side="top", anchor="w")
run_btn = tb.Button(run_row, text="Run Manual Calibration", bootstyle=SUCCESS, width=22,
          command=lambda: threading.Thread(target=run_calibration, daemon=True).start())
run_btn.pack(side="left", padx=(5))
info_run = tb.Button(run_row, text="?", width=2, bootstyle="info-outline",

                     command=lambda: show_info(
                         "Manual Calibration",
                         calibration_instructions,
                         image_path="assets/auction_options_template.png"
                     ))
info_run.pack(side="left")

def reset_region_ui():
    region_test_label.config(text="")
    calibrator.reset_region(status_label=status_label)
    update_status_label()
    update_button_states()
    logger.update_log("🔄 Region removed. Run calibration again if needed.")

remove_row = tb.Frame(right_group)
remove_row.pack(side="top", pady=4, anchor="w")
reset_btn = tb.Button(remove_row, text="Remove Manual Region",
    bootstyle=DANGER,
    command=reset_region_ui,
    width=22)
reset_btn.pack(side="left", padx=(5))
info_remove = tb.Button(remove_row, text="?", width=2, bootstyle="info-outline",

                         command=lambda: show_info("Remove Manual Region", 
"Clears any user-specified calibration. "
"When removed the sniper will revert to automatic detection which is slower per scan but doesn’t require setup."))
info_remove.pack(side="left")

# Status box under the left group (flow layout)
status_box = tb.Labelframe(calib_tab, text="Calibration Status", padding=8)
status_box.pack(fill="x", padx=20, pady=(10,12))

status_label = tb.Label(
    status_box,
    text="Manual calibration: not set\nAuto calibration: not set",
    font=("Arial", 12),
    wraplength=850
)
status_label.pack(anchor="w")

# Image label for displaying calibration visual with arrow
calib_image_label = tb.Label(status_box, text="")
calib_image_label.pack(anchor="w", pady=(8,8))

region_test_label = tb.Label(status_box, text="", font=("Arial", 12, "italic"), wraplength=850)
region_test_label.pack(anchor="w", pady=(4,0))

# Test and Show overlay buttons under the status box
test_overlay_frame = tb.Frame(calib_tab)
test_overlay_frame.pack(pady=(5, 10), fill="x")

# Left side: Test Region
test_left = tb.Frame(test_overlay_frame)
test_left.pack(side="left", padx=20)

test_row = tb.Frame(test_left)
test_row.pack(side="top", anchor="w")
test_btn = tb.Button(test_row, text="Test Region", command=test_region,
                     bootstyle=INFO, width=20)
test_btn.pack(side="left", padx=(5,0))
info_test = tb.Button(test_row, text="?", width=2, bootstyle="info-outline",
                      command=lambda: show_info("Test Region Info", 
"Test Region checks the current detection region for the Auction Options button. "
"Make sure that you are in the auction house with Auction Options button visible when you run this test."))
info_test.pack(side="left", padx=(0,15))

# Right side: Show Region Overlay
test_right = tb.Frame(test_overlay_frame)
test_right.pack(side="left", padx=20)

show_row = tb.Frame(test_right)
show_row.pack(side="top", anchor="w")
show_btn = tb.Button(show_row, text="Show Region Overlay",
          command=lambda: calibrator.show_region_overlay(
              region=(calibrator.load_region() if calibrator.has_manual_region() else 
                     calibrator.load_auto_region() if calibrator.has_auto_region() else 
                     calibrator.load_region()),
              duration=5000,
              root=root
          ),
          bootstyle=INFO,
          width=20)
show_btn.pack(side="left", padx=(5,0))
info_show = tb.Button(show_row, text="?", width=2, bootstyle="info-outline",
                      command=lambda: show_info("Show Region Overlay Info", 
"Show Region Overlay draws the calibrated region on screen so you can verify it covers the Auction Options button."))
info_show.pack(side="left", padx=(0,15))

# Callback to update calibration image display
def update_calibration_image(pil_image):
    """Update the calibration image label with arrow display."""
    try:
        if pil_image is None:
            calib_image_label.config(image="", text="")
            calib_image_label.image = None
        else:
            photo = ImageTk.PhotoImage(pil_image)
            calib_image_label.config(image=photo, text="")
            calib_image_label.image = photo
    except Exception as e:
        print(f"Error updating calibration image: {e}")


def update_status_label():
    try:
        manual_status = "SET" if calibrator.has_manual_region() else "NOT SET"
        has_any_calibration = calibrator.has_manual_region() or calibrator.has_auto_region()
        
        if calibrator.has_auto_region():
            auto_status = "SET"
        elif has_any_calibration:
            auto_status = "NOT SET"
        else:
            auto_status = "NOT SET\nTry resizing the Forza Horizon 5 window to be bigger or smaller to ensure the Auction Options button is detected."
        
        status_label.config(
            text=f"Manual calibration: {manual_status}\nAuto calibration: {auto_status}",
            bootstyle="success" if has_any_calibration else "danger"
        )
    except Exception:
        status_label.config(
            text="Manual calibration: unknown\nAuto calibration: unknown",
            bootstyle="warning"
        )

# control state helper
def update_button_states():
    has_manual = calibrator.has_manual_region()
    has_auto = calibrator.has_auto_region()
    has_any = has_manual or has_auto
    
    # Manual calibration buttons
    if has_manual:
        reset_btn.config(state=NORMAL)
    else:
        reset_btn.config(state=DISABLED)
    
    # Test and Show buttons work with any calibration
    if has_any:
        show_btn.config(state=NORMAL)
        test_btn.config(state=NORMAL)
    else:
        show_btn.config(state=DISABLED)
        test_btn.config(state=DISABLED)
    
    # Auto calibration buttons
    if has_auto:
        auto_reset_btn.config(state=NORMAL)
    else:
        auto_reset_btn.config(state=DISABLED)

# ---------- Settings Tab ----------
settings_tab = tb.Frame(notebook)
notebook.add(settings_tab, text="Settings")

title_row = tb.Frame(settings_tab)
title_row.pack(fill="x", pady=8, padx=10)

# Centered Settings title
settings_title_label = tb.Label(title_row, text="Settings", font=("Arial", 14, "bold"), anchor="center", justify="center")
settings_title_label.pack(side="left", expand=True, fill="x")

# Explanatory text about settings
settings_explain = (
    "Choose a timing preset based on your PC performance and internet speed, or customize the values manually.\n\n"
    "If keystrokes are being executed too fast or the app is not keeping pace with the game, "
    "increase the timing intervals or choose a slower preset."
)

settings_explain_label = tb.Label(
    settings_tab,
    text=settings_explain,
    font=("Arial", 11, "italic"),
    wraplength=900,
    justify="center"
)
settings_explain_label.pack(pady=(10, 5))

# Preset selector
preset_frame = tb.Frame(settings_tab)
preset_frame.pack(pady=(10, 5), fill="x")

# Inner frame to hold the label and combobox centered
row_frame = tb.Frame(preset_frame)
row_frame.pack(anchor="center")  # Centers the inner frame horizontally

preset_var = tb.StringVar(value="Custom")  # Default to Custom since we load current values

# Label and combobox side by side
tb.Label(row_frame, text="Timing Preset", font=("Arial", 12, "bold")).pack(side="left", padx=(0, 10))
preset_combo = tb.Combobox(
    row_frame,
    textvariable=preset_var,
    values=["Custom", "Fast", "Mid", "Slow"],
    state="readonly",
    width=15
)
preset_combo.pack(side="left")

info_btn = tb.Button(row_frame, text="?", width=2, bootstyle="info-outline",
                     command=lambda: show_info("Timing Presets", "Fast: For high-end PCs with fast internet\nMid: For average PCs with stable internet\nSlow: For slower PCs or laggy connections\n\n"))
info_btn.pack(side="left", padx=(5,0))

# Preset definitions
PRESETS = {
    "Fast": {"buy_attempt_interval": 0.4, "post_buy_wait": 4.0, "reset_interval": 0.8},
    "Mid": {"buy_attempt_interval": 0.6, "post_buy_wait": 5.0, "reset_interval": 0.9},
    "Slow": {"buy_attempt_interval": 0.7, "post_buy_wait": 6.0, "reset_interval": 1.1},
}

def detect_current_preset():
    """Check if current timing values match a preset."""
    try:
        current = {
            "buy_attempt_interval": float(buy_interval_var.get()),
            "post_buy_wait": float(post_buy_wait_var.get()),
            "reset_interval": float(reset_interval_var.get()),
        }
        for preset_name, preset_values in PRESETS.items():
            if all(abs(current[key] - preset_values[key]) < 0.01 for key in preset_values):
                return preset_name
    except ValueError:
        pass
    return "Custom"

def update_preset_display():
    """Update the preset combobox to reflect current values."""
    current_preset = detect_current_preset()
    preset_var.set(current_preset)

timings = settings.load_timings_ui()

buy_interval_var = tb.StringVar(value=str(timings.get("buy_attempt_interval", 0.6)))
post_buy_wait_var = tb.StringVar(value=str(timings.get("post_buy_wait", 5.0)))
reset_interval_var = tb.StringVar(value=str(timings.get("reset_interval", 0.9)))
attempts_var = tb.StringVar(value=str(settings.get_scans()))  # stores scans count

# Set initial preset display
update_preset_display()

# helper to create row with info button

def make_setting_row(parent, label_text, var, help_text):
    row = tb.Frame(parent)
    # allow row to expand horizontally so we can centre entry_frame with grid
    row.pack(pady=(10,0), anchor="center", fill="x")
    # grid columns: [filler][label][entry+button][filler]
    row.grid_columnconfigure(0, weight=1)
    row.grid_columnconfigure(1, weight=0)
    row.grid_columnconfigure(2, weight=0)
    row.grid_columnconfigure(3, weight=1)
    # place label in column 1 (fixed), entry_frame in column 2 (fixed); filler columns keep entry centered
    tb.Label(row, text=label_text).grid(row=0, column=1, padx=(0,10), sticky="e")
    entry_frame = tb.Frame(row)
    entry_frame.grid(row=0, column=2)
    tb.Entry(entry_frame, textvariable=var, width=10).pack(side="left")
    tb.Button(
        entry_frame,
        text="?",
        width=2,
        bootstyle="info-outline",
        command=lambda: show_info(label_text, help_text)
    ).pack(side="left", padx=(5,0))
    return row

# number of scans row
make_setting_row(
    settings_tab,
    "Number of Scans",
    attempts_var,
    "How many auctions the sniper will scan before stopping. "
    "A higher number increases coverage but takes longer."
)

make_setting_row(
    settings_tab,
    "Buy Interval",
    buy_interval_var,
    "Delay between key presses during the buy attempt navigation."
)

make_setting_row(
    settings_tab,
    "Post Buy Wait",
    post_buy_wait_var,
    "Delay after a buy attempt to match the in‑game time it takes for the auction to report success or failure."
)

make_setting_row(
    settings_tab,
    "Reset Interval",
    reset_interval_var,
    "The interval between resets of the auction view, used when exiting out and entering the auction list again."
)

# Function to save settings
def save_settings(message=None):
    try:
        timings_dict = {
            "buy_attempt_interval": float(buy_interval_var.get()),
            "post_buy_wait": float(post_buy_wait_var.get()),
            "reset_interval": float(reset_interval_var.get()),
        }
        scans_value = int(attempts_var.get())
    except ValueError:
        validation_error_label.config(text="❌ Invalid values (must be numbers)", bootstyle="danger")
        return
    
    # Validate and save
    is_valid, error_msg, corrected = settings.save_timings_ui(timings_dict, scans_value)
    
    # Update UI with corrected values
    attempts_var.set(str(corrected["scans"]))
    buy_interval_var.set(str(corrected["timings"]["buy_attempt_interval"]))
    post_buy_wait_var.set(str(corrected["timings"]["post_buy_wait"]))
    reset_interval_var.set(str(corrected["timings"]["reset_interval"]))
    
    # Update preset display
    update_preset_display()
    
    # update scans left label immediately
    global current_total_scans
    current_total_scans = corrected["scans"]
    scans_left_label.config(text=f"Scans left: {current_total_scans}")
    
    if message:
        validation_error_label.config(text=message, bootstyle="success")
    elif is_valid:
        validation_error_label.config(text="✅ Settings saved", bootstyle="success")
    else:
        validation_error_label.config(text=f"⚠️ {error_msg} (auto-corrected and saved)", bootstyle="warning")

button_frame = tb.Frame(settings_tab)
button_frame.pack(pady=10)

tb.Button(button_frame, text="Save Settings", command=save_settings, bootstyle="success").pack(side="left", padx=5)

validation_error_label = tb.Label(settings_tab, text="", font=("Arial", 11))
validation_error_label.pack(pady=5)

def apply_preset():
    """Apply the selected preset values to the UI and auto-save if not Custom."""
    preset_name = preset_var.get()
    if preset_name in PRESETS:
        preset_values = PRESETS[preset_name]
        buy_interval_var.set(str(preset_values["buy_attempt_interval"]))
        post_buy_wait_var.set(str(preset_values["post_buy_wait"]))
        reset_interval_var.set(str(preset_values["reset_interval"]))
        if preset_name != "Custom":
            save_settings(message=f"✅ {preset_name} applied, settings saved!")
        else:
            validation_error_label.config(text=f"✅ Applied {preset_name} preset", bootstyle="success")

def on_preset_change(*args):
    """Called when preset selection changes."""
    apply_preset()

preset_var.trace_add("write", on_preset_change)

def _run_update_check(interactive=False, test_latest=None):
    """Run check_for_updates in background; if interactive=True show popup when newer."""
    try:
        if test_latest is not None:
            latest = test_latest
            check_error = None
        else:
            latest, check_error = check_for_updates()

        if latest:
            # if interactive show popup, otherwise only log
            if interactive:
                root.after(0, lambda: show_update_popup(latest))
            else:
                logger.update_log(f"🔄 Update available: {latest}")
        else:
            # give user feedback when they asked for an interactive check
            if interactive:
                if check_error == "missing_requests":
                    root.after(0, lambda: show_info("Update Check", "Update check unavailable: 'requests' package not installed. Install with `pip install requests`."))
                elif check_error is None:
                    root.after(0, lambda: show_info("Update Check", "You're already up to date!"))
                else:
                    root.after(0, lambda: show_info("Update Check", "Update check failed. Please try again later."))
    except Exception:
        pass

# update status and button states on startup
update_status_label()
update_button_states()

# ---------- Info Tab ----------
info_tab = tb.Frame(notebook)
notebook.add(info_tab, text="Info")

tb.Label(info_tab, text="Project information and support links", font=("Arial", 12)).pack(pady=20)

# GitHub link
github_frame = tb.Frame(info_tab)
github_frame.pack(pady=10)
tb.Label(github_frame, text="View the project on GitHub", font=("Arial", 10)).pack(side="left")
tb.Button(github_frame, text="Open", command=lambda: webbrowser.open("https://github.com/FH5-Sniper/fh5_sniper"), bootstyle=PRIMARY, width=8).pack(side="left", padx=(10,0))

# PayPal link
paypal_frame = tb.Frame(info_tab)
paypal_frame.pack(pady=10)
tb.Label(paypal_frame, text="Support the project via PayPal", font=("Arial", 10)).pack(side="left")
tb.Button(paypal_frame, text="Donate", command=lambda: webbrowser.open("https://www.paypal.com/ncp/payment/W2FY4KHD58UEG"), bootstyle=SUCCESS, width=8).pack(side="left", padx=(10,0))

# Update check
update_frame = tb.Frame(info_tab)
update_frame.pack(pady=10)
tb.Button(update_frame, text="Check for updates", command=lambda: threading.Thread(target=lambda: _run_update_check(interactive=True), daemon=True).start(), bootstyle=INFO, width=18).pack()

root.mainloop()