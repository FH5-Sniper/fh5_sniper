import ttkbootstrap as tb
from ttkbootstrap.constants import *
from tkinter import scrolledtext
import tkinter as tk
import threading
import calibrator
import sniper
import settings
import logger
from PIL import Image, ImageTk
import window_utils
import ctypes
import os

# application version (bump when releasing)
__version__ = "1.0.0"

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

# --- DEFAULT REGION ---

DEFAULT_REGION = calibrator.load_region()

# --- CONFIG SAVE ---
CONFIG_FILE = "config.json"


# optional auto-update checker (stub)
def check_for_updates():
    """Query GitHub releases and log if a newer version exists.

    This is a lightweight non-critical operation; failures are ignored.
    """
    try:
        import requests
        url = "https://api.github.com/repos/yourusername/fh5_sniper/releases/latest"
        resp = requests.get(url, timeout=3)
        if resp.ok:
            latest = resp.json().get("tag_name")
            if latest and latest != __version__:
                logger.update_log(f"🔄 New version available: {latest} (current {__version__})")
    except Exception:
        pass

# --- BUILD UI ---

# ---------- Main Window ----------
# use a dark theme by default; still modern but easier on eyes
root = tb.Window(themename="cyborg")
root.title("FH5 Sniper")
# apply custom icon if available
try:
    root.iconbitmap(_icon_file)
except Exception:
    pass
root.geometry("930x700")

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

notebook = tb.Notebook(root)
notebook.pack(fill="both", expand=True, padx=10, pady=10)

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

def show_calibration_warning():
    """Display modal popup reminding user to perform manual calibration.

    Returns when the user dismisses the dialog. If the "don't show again"
    checkbox is ticked, the preference is saved via settings.set_skip_calibration_warning.
    """
    popup = tk.Toplevel(root)
    popup.title("Calibration Recommended")
    popup.transient(root)
    popup.grab_set()

    tb.Label(popup, text="Manual calibration has not been performed.", font=("Arial", 12)).pack(padx=20, pady=(20, 5))
    tb.Label(
    popup,
    text="For faster scans, we recommend running Manual Calibration",
    font=("Arial", 10)
    ).pack(padx=20)

    tb.Label(
        popup,
        text="in the Calibration tab before starting the sniper.",
        font=("Arial", 10)
    ).pack(padx=20, pady=(0, 15))

    dont_show_var = tk.BooleanVar()
    tb.Checkbutton(popup, text="Don't show again", variable=dont_show_var).pack(pady=(0, 15))

    def on_close():
        if dont_show_var.get():
            settings.set_skip_calibration_warning(True)
        popup.destroy()

    ok_button = tb.Button(popup, text="Continue", width=10, command=on_close)
    ok_button.pack(pady=(0, 20))

    popup.protocol("WM_DELETE_WINDOW", on_close)
    root.wait_window(popup)


def start_sniper_ui():
    global sniper_running, stop_flag, timer_running, timer_elapsed, buy_attempts, buy_successes, buy_failures
    if sniper_running:
        logger.update_log("⚠️ Sniper already running!")
        return
    # warn the user if calibration hasn't been done and they haven't opted out
    if not calibrator.has_manual_region() and not settings.get_skip_calibration_warning():
        show_calibration_warning()

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
    "The tool will automatically capture these points and calculate the region."
)

# brief explanation about calibration vs automatic detection
calib_explain = (
    "Manual calibration allows the sniper to focus on a tight region, making each scan much faster.\n\n"
    "If no manual calibration exists, the app will fall back to the built-in detection logic which scans wider areas and takes slightly longer per attempt.\n"
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
    region_test_label.config(text="")
    calibrator.calibrate(status_label=status_label, image_callback=update_calibration_image, error_label=region_test_label)

    # update UI in main thread
    root.after(0, update_status_label)
    root.after(0, update_button_states)
    root.after(0, lambda: logger.update_log("✅ Manual calibration complete"))

# horizontal button frame
btn_frame = tb.Frame(calib_tab)
btn_frame.pack(pady=5, fill="x")

# Left group: Run + Remove (stacked vertically) with info buttons
left_group = tb.Frame(btn_frame)
left_group.pack(side="left", anchor="n")

run_row = tb.Frame(left_group)
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

def test_region():
    # mimic sniper_loop's one-time region calculation
    config_region = calibrator.load_region()
    window = window_utils.get_fh5_window()
    if window:
        full = window_utils.get_window_region(window)
        test_reg = window_utils.bottom_left_quarter(full)
    else:
        test_reg = window_utils.bottom_left_quarter(config_region)

    try:
        found = sniper.car_available(test_reg)
        if found:
            region_test_label.config(text="Test Region Result: ✅ Button detected in region", bootstyle="success")
        else:
            region_test_label.config(text="Test Region Result: ❌ Button NOT detected in region", bootstyle="danger")

    except Exception as e:
        region_test_label.config(text=f"❌ Error testing region: {e}", bootstyle="danger")

# Right group: Test + Show overlay (stacked vertically)
right_group = tb.Frame(btn_frame)
right_group.pack(side="left", anchor="n", padx=20)

# row for Test Region
test_row = tb.Frame(right_group)
test_row.pack(side="top", anchor="w", pady=2)
test_btn = tb.Button(test_row, text="Test Region", command=test_region,
                     bootstyle=INFO, width=20)
test_btn.pack(side="left", padx=(5,0))
info_test = tb.Button(test_row, text="?", width=2, bootstyle="info-outline",
                      command=lambda: show_info("Test/Overlay Info", 
"Test Region checks the current detection region for the Auction Options button. "
"Make sure that you are in the auction house with cars available to buy when you run this test. "
"This requires a manual calibration region to be set."))
info_test.pack(side="left", padx=(0,15))

# row for Show Overlay
show_row = tb.Frame(right_group)
show_row.pack(side="top", anchor="w", pady=2)
show_btn = tb.Button(show_row, text="Show Region Overlay",
          command=lambda: calibrator.show_region_overlay(
              region=calibrator.load_region(),
              duration=5000,
              root=root
          ),
          bootstyle=INFO,
          width=20)
show_btn.pack(side="left", padx=(5,0))
info_show = tb.Button(show_row, text="?", width=2, bootstyle="info-outline",
                      command=lambda: show_info("Show Region Overlay Info", 
"Show Region Overlay draws the calibrated region on screen so you can verify it covers the Auction Options button. "
"This requires a manual calibration region to be set."))
info_show.pack(side="left", padx=(0,15))
info_show.pack(side="left", padx=(0,15))


def reset_region_ui():
    region_test_label.config(text="")
    calibrator.reset_region(status_label=status_label)
    update_status_label()
    update_button_states()
    logger.update_log("🔄 Region removed. Run calibration again if needed.")

remove_row = tb.Frame(left_group)
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
    text="Manual calibration: not set",
    font=("Arial", 12)
)
status_label.pack(anchor="w")

# Image label for displaying calibration visual with arrow
calib_image_label = tb.Label(status_box, text="")
calib_image_label.pack(anchor="w", pady=(8,8))

region_test_label = tb.Label(status_box, text="", font=("Arial", 12, "italic"), wraplength=850)
region_test_label.pack(anchor="w", pady=(4,0))

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
        if calibrator.has_manual_region():
            status_label.config(
                text="Manual calibration: SET",
                bootstyle="success"
            )
        else:
            status_label.config(
                text="Manual calibration: NOT SET",
                bootstyle="danger"
            )
    except Exception:
        status_label.config(
            text="Manual calibration: unknown",
            bootstyle="warning"
        )

# control state helper
def update_button_states():
    has = calibrator.has_manual_region()
    if has:
        reset_btn.config(state=NORMAL)
        show_btn.config(state=NORMAL)
        test_btn.config(state=NORMAL)
    else:
        reset_btn.config(state=DISABLED)
        show_btn.config(state=DISABLED)
        test_btn.config(state=DISABLED)

# Initialize status label
update_status_label()
update_button_states()

# ---------- Settings Tab ----------
settings_tab = tb.Frame(notebook)
notebook.add(settings_tab, text="Settings")

tb.Label(settings_tab, text="Settings", font=("Arial", 14, "bold")).pack(pady=10)

# Explanatory text about settings
settings_explain = (
    "These settings are optimal if your internet connection is stable and your game runs without lag.\n\n"
    "If keystrokes are being executed too fast or the app is not keeping pace with the game, "
    "increase the timing intervals (Buy Interval, Post Buy Wait, Reset Interval) to give the game more time to respond.\n"
)

settings_explain_label = tb.Label(
    settings_tab,
    text=settings_explain,
    font=("Arial", 11, "italic"),
    wraplength=900,
    justify="center"
)
settings_explain_label.pack(pady=(10, 5))

timings = settings.load_timings_ui()

buy_interval_var = tb.StringVar(value=str(timings.get("buy_attempt_interval", 0.4)))
post_buy_wait_var = tb.StringVar(value=str(timings.get("post_buy_wait", 5.0)))
reset_interval_var = tb.StringVar(value=str(timings.get("reset_interval", 0.8)))
attempts_var = tb.StringVar(value=str(settings.get_scans()))  # stores scans count

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
def save_settings():
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
    
    # update scans left label immediately
    global current_total_scans
    current_total_scans = corrected["scans"]
    scans_left_label.config(text=f"Scans left: {current_total_scans}")
    
    if is_valid:
        validation_error_label.config(text="✅ Settings saved", bootstyle="success")
    else:
        validation_error_label.config(text=f"⚠️ {error_msg} (auto-corrected and saved)", bootstyle="warning")

# Function to reset to defaults
def reset_to_defaults():
    config = settings.reset_to_defaults()
    # Update UI with defaults
    buy_interval_var.set(str(config["TIMINGS"].get("buy_attempt_interval", 0.4)))
    post_buy_wait_var.set(str(config["TIMINGS"]["post_buy_wait"]))
    reset_interval_var.set(str(config["TIMINGS"]["reset_interval"]))
    attempts_var.set(str(config.get("scans", config.get("attempts", 1000))))
    # reflect new count in scans left label
    global current_total_scans
    current_total_scans = config.get("scans", config.get("attempts", 1000))
    scans_left_label.config(text=f"Scans left: {current_total_scans}")
    validation_error_label.config(text="✅ Reset to defaults", bootstyle="success")

button_frame = tb.Frame(settings_tab)
button_frame.pack(pady=10)

tb.Button(button_frame, text="Save Settings", command=save_settings, bootstyle="success").pack(side="left", padx=5)
tb.Button(button_frame, text="Reset to Defaults", command=reset_to_defaults, bootstyle="warning").pack(side="left", padx=5)

validation_error_label = tb.Label(settings_tab, text="", font=("Arial", 11))
validation_error_label.pack(pady=5)


root.mainloop()