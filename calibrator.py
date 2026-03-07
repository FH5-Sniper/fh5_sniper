import pyautogui
import time
import json
import os
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk
import window_utils

CONFIG_FILE = window_utils.get_config_file()

# Padding in pixels
PADDING_LEFT = 20
PADDING_TOP = 20
PADDING_RIGHT = 20
PADDING_BOTTOM = 20


def draw_arrow_on_image(image_path, target_pos, arrow_color="red"):
    """
    Load image and draw an arrow with label pointing to target corner.
    Arrow is drawn AROUND/OUTSIDE the image with extended black background.
    target_pos: 'top-left' or 'bottom-right'
    Returns: PIL Image with arrow and label
    """
    try:
        img_path = window_utils.resource_path(image_path)
        img = Image.open(img_path).convert("RGB")
        orig_w, orig_h = img.size
        
        # Extend canvas: add 120px padding on top/left, 80px on bottom/right
        canvas_w = orig_w + 200
        canvas_h = orig_h + 120
        
        # Create black background
        canvas = Image.new("RGB", (canvas_w, canvas_h), color="black")
        # Paste original image in offset position
        canvas.paste(img, (80, 40))
        
        # Draw on canvas
        draw = ImageDraw.Draw(canvas)
        
        # Arrow properties
        import math
        arrow_color_rgb = arrow_color
        line_width = 4
        arrow_size = 30
        
        if target_pos == "top-left":
            # Arrow from left pointing to top-left corner of image
            # Image top-left is at (80, 40)
            img_corner_x, img_corner_y = 80, 40
            
            # Arrow starts from left side
            start_x, start_y = 20, img_corner_y
            end_x, end_y = img_corner_x - 10, img_corner_y
            
            # Draw arrow line
            draw.line([(start_x, start_y), (end_x, end_y)], fill=arrow_color_rgb, width=line_width)
            
            # Arrowhead pointing right
            arrow_left_y = end_y - arrow_size // 2
            arrow_right_y = end_y + arrow_size // 2
            draw.polygon(
                [(end_x, end_y), (end_x - arrow_size, arrow_left_y), (end_x - arrow_size, arrow_right_y)],
                fill=arrow_color_rgb
            )
            
            # Label: "→ Auction Options"
            draw.text((25, img_corner_y - 25), "→", fill=arrow_color_rgb, 
                     font=None)  # Using default font
        
        else:  # bottom-right
            # Arrow from right pointing to bottom-right corner of image
            # Image bottom-right is at (80 + orig_w, 40 + orig_h)
            img_corner_x, img_corner_y = 80 + orig_w, 40 + orig_h
            
            # Arrow starts from right side
            start_x, start_y = canvas_w - 20, img_corner_y
            end_x, end_y = img_corner_x + 10, img_corner_y
            
            # Draw arrow line
            draw.line([(start_x, start_y), (end_x, end_y)], fill=arrow_color_rgb, width=line_width)
            
            # Arrowhead pointing left
            arrow_left_y = end_y - arrow_size // 2
            arrow_right_y = end_y + arrow_size // 2
            draw.polygon(
                [(end_x, end_y), (end_x + arrow_size, arrow_left_y), (end_x + arrow_size, arrow_right_y)],
                fill=arrow_color_rgb
            )
            
            # Label: "Auction Options ←"
            label_x = canvas_w - 180
            draw.text((label_x, img_corner_y - 25), "←", fill=arrow_color_rgb, 
                     font=None)  # Using default font
        
        return canvas
    except Exception as e:
        print(f"Error drawing arrow: {e}")
        return None


def show_calibration_visual(target_pos, duration=5000, root=None):
    """
    Show a window with the auction options template image and a red arrow.
    target_pos: 'top-left' or 'bottom-right'
    """
    if root is None:
        root = tk.Tk()
        root.withdraw()
    
    try:
        # Draw arrow on image (use assets folder)
        img_with_arrow = draw_arrow_on_image("assets/auction_options_template.png", target_pos)
        if img_with_arrow is None:
            return
        
        # Resize for display (max 300px)
        max_size = 300
        img_with_arrow.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img_with_arrow)
        
        # Create overlay window
        overlay = tk.Toplevel(root)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.85)
        overlay.overrideredirect(True)
        overlay.geometry(f"{img_with_arrow.width}x{img_with_arrow.height}+100+100")
        
        # Display image
        img_label = tk.Label(overlay, image=photo)
        img_label.image = photo
        img_label.pack()
        
        # Auto close
        overlay.after(duration, overlay.destroy)
        overlay.bind("<Button-1>", lambda e: overlay.destroy())
        
        return overlay
    except Exception as e:
        print(f"Error showing calibration visual: {e}")


def get_calibration_image(target_pos):
    """
    Get the template image with arrow (no window, just return image).
    Returns: PIL Image resized to max 300px, or None on error.
    """
    try:
        img_with_arrow = draw_arrow_on_image("assets/auction_options_template.png", target_pos)
        if img_with_arrow is None:
            return None
        
        # Resize for display
        max_size = 300
        img_with_arrow.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        return img_with_arrow
    except Exception as e:
        print(f"Error getting calibration image: {e}")
        return None



def calibrate(status_label=None, image_callback=None, error_label=None):
    """Manual calibration: user hovers over top-left and bottom-right corners with visual guide."""
    def countdown(msg, target_pos):
        # Update image in UI if callback provided
        if image_callback:
            try:
                calib_img = get_calibration_image(target_pos)
                image_callback(calib_img)
            except Exception as e:
                print(f"Error updating calibration image: {e}")
        
        for i in range(5, 0, -1):
            text = f"{msg} ({i})"
            print(text)
            if status_label:
                status_label.after(
                    0,
                    lambda: status_label.config(
                        text=text,
                        bootstyle="info"
                    )
                )
            time.sleep(1)

    countdown("Move mouse to TOP-LEFT corner of Auction Options button", "top-left")
    top_left_x, top_left_y = pyautogui.position()
    print(f"Top-left captured: {top_left_x}, {top_left_y}")

    countdown("Move mouse to BOTTOM-RIGHT corner of Auction Options button", "bottom-right")
    bottom_right_x, bottom_right_y = pyautogui.position()
    print(f"Bottom-right captured: {bottom_right_x}, {bottom_right_y}")

    width = bottom_right_x - top_left_x
    height = bottom_right_y - top_left_y
    
    # Validate calibration: ensure mouse moved correctly
    if width <= 0 or height <= 0:
        error_msg = ""
        if width <= 0:
            error_msg += "Mouse moved horizontally in wrong direction (should move left to right). "
        if height <= 0:
            error_msg += "Mouse moved vertically in wrong direction (should move top to bottom)."
        
        print(f"❌ Calibration failed: {error_msg}")
        
        # Clear image
        if image_callback:
            image_callback(None)
        
        # Show error in dedicated error_label if provided, otherwise use status_label
        error_display = error_label if error_label else status_label
        if error_display:
            error_display.after(
                0,
                lambda msg=error_msg: error_display.config(
                    text=f"❌ Calibration failed: {msg}Try again!",
                    bootstyle="danger"
                )
            )
        return
    
    region = (
        top_left_x - PADDING_LEFT,
        top_left_y - PADDING_TOP,
        width + PADDING_LEFT + PADDING_RIGHT,
        height + PADDING_TOP + PADDING_BOTTOM
    )

    # record FH5 window size while we're at it, if available
    win = window_utils.get_fh5_window()
    baseline = {}
    if win:
        baseline = {
            "BASELINE_WINDOW_WIDTH": win.width,
            "BASELINE_WINDOW_HEIGHT": win.height,
        }

    # Save to config
    cfg = {"AUCTION_OPTIONS_REGION": region}
    cfg.update(baseline)
    try:
        with open(CONFIG_FILE, "r") as f:
            existing = json.load(f)
        existing.update(cfg)
        cfg = existing
    except FileNotFoundError:
        pass
    
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

    print(f"✅ Saved region: AUCTION_OPTIONS_REGION = {region}")

    # Clear image on completion
    if image_callback:
        image_callback(None)

    if status_label:
        status_label.after(
            0,
            lambda: status_label.config(
                text="Manual calibration: SET",
                bootstyle="success"
            )
        )



def get_default_region():
    """Return a default bottom-left region with padding if no calibration exists."""
    try:
        screen_width, screen_height = pyautogui.size()
    except Exception:
        screen_width, screen_height = 0, 0

    # Check for FH5 window for better default
    fh5_window = window_utils.get_fh5_window()
    if fh5_window:
        # Prioritize FH5 window bounds
        screen_width = fh5_window.width
        screen_height = fh5_window.height

    # Button dimensions
    w, h = 365, 75
    margin_left, margin_bottom = 10, 10

    if screen_width == 0 or screen_height == 0:
        return (0, 0, screen_width, screen_height)

    x1 = margin_left - PADDING_LEFT
    y1 = screen_height - h - margin_bottom - PADDING_TOP
    width = w + PADDING_LEFT + PADDING_RIGHT
    height = h + PADDING_TOP + PADDING_BOTTOM

    return (x1, y1, width, height)


def load_region():
    """Return region from config, or default if not calibrated."""
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        return tuple(data["AUCTION_OPTIONS_REGION"])
    except Exception:
        return get_default_region()


def load_baseline_window():
    """Return stored window size (width,height) or None."""
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        w = data.get("BASELINE_WINDOW_WIDTH")
        h = data.get("BASELINE_WINDOW_HEIGHT")
        if w and h:
            return (w, h)
    except Exception:
        pass
    return None


def has_manual_region():
    """Return True if a manual AUCTION_OPTIONS_REGION exists in config."""
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        return "AUCTION_OPTIONS_REGION" in data
    except Exception:
        return False


def has_auto_region():
    """Return True if an auto AUCTION_OPTIONS_REGION exists in config."""
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        return "AUTO_AUCTION_OPTIONS_REGION" in data
    except Exception:
        return False


import tkinter as tk

import tkinter as tk

def show_region_overlay(region, duration=5000, root=None,
                        message="Button should be behind this"):
    """
    Pro overlay with proper text padding.
    Detection box stays exact.
    Text never touches the box.
    """

    x, y, w, h = region

    if root is None:
        root = tk.Tk()
        root.withdraw()

    # 🔥 Layout tuning
    EXTRA_WIDTH = 320
    TEXT_HEIGHT = 56          # ⬅️ increased for safe wrap
    SIDE_PADDING = 16
    TEXT_TOP_PADDING = 8      # ⬅️ new vertical breathing room
    TEXT_BOTTOM_PADDING = 16  # ⬅️ space above box

    overlay_width = max(w + SIDE_PADDING * 2, EXTRA_WIDTH)
    overlay_height = h + TEXT_HEIGHT

    # Center detection box
    box_offset_x = (overlay_width - w) // 2
    box_top_y = TEXT_HEIGHT  # where the box starts vertically

    overlay = tk.Toplevel(root)
    overlay.attributes("-topmost", True)
    overlay.overrideredirect(True)
    overlay.attributes("-alpha", 0.35)

    overlay.geometry(
        f"{overlay_width}x{overlay_height}+{x - box_offset_x}+{y - TEXT_HEIGHT}"
    )

    canvas = tk.Canvas(
        overlay,
        width=overlay_width,
        height=overlay_height,
        bg="white",
        highlightthickness=0,
    )
    canvas.pack()

    # 🔴 Detection box (exact region)
    canvas.create_rectangle(
        box_offset_x,
        box_top_y,
        box_offset_x + w,
        box_top_y + h,
        outline="red",
        width=3,
    )

    # 🧠 Countdown text (proper padded zone)
    text_id = canvas.create_text(
        overlay_width / 2,
        (TEXT_HEIGHT - TEXT_BOTTOM_PADDING) / 2 + TEXT_TOP_PADDING,
        text="",
        fill="red",
        font=("Segoe UI", 11, "bold"),
        width=overlay_width - SIDE_PADDING * 2,
        justify="center",
    )

    # ⏱️ Countdown updater
    def update_countdown(remaining_ms):
        remaining_s = max(0, remaining_ms // 1000)
        canvas.itemconfig(
            text_id,
            text=f"{message}, closing in {remaining_s}s",
        )
        if remaining_ms > 0:
            overlay.after(1000, lambda: update_countdown(remaining_ms - 1000))

    update_countdown(duration)

    # Auto close
    overlay.after(duration, overlay.destroy)

    # Optional click to close
    overlay.bind("<Button-1>", lambda e: overlay.destroy())

def reset_region(status_label=None):
    """Reset AUCTION_OPTIONS_REGION in config to default (or empty)."""
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    if "AUCTION_OPTIONS_REGION" in data:
        del data["AUCTION_OPTIONS_REGION"]

    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

    if status_label:
        status_label.after(
            0,
            lambda: status_label.config(
                text="Manual calibration: NOT SET",
                bootstyle="danger"
            )
        )


def find_optimal_template_and_location(base_template):
    """Find the optimal template and scale for the current screen configuration.
    
    Returns:
        tuple: (template_path, scale, location) or None if not found
    """
    import vision_utils
    
    # Get window size for template selection
    win = window_utils.get_fh5_window()
    if win:
        size_region = window_utils.get_window_region(win)
    else:
        # Fall back to full screen if window not found
        import pyautogui
        screen_w, screen_h = pyautogui.size()
        size_region = (0, 0, screen_w, screen_h)
    
    # Choose the primary template based on window size
    template_path, category = vision_utils.choose_template(base_template, region=size_region, debug=False)
    
    # Try the primary template first with scale detection
    result = find_template_at_best_scale(template_path)
    if result:
        scale, location = result
        return template_path, scale, location
    
    # If primary template fails, try other variants
    candidates = []
    
    # Add other variants if they exist
    med = base_template.replace(".png", "_med.png")
    if os.path.isfile(window_utils.resource_path(med)):
        candidates.append(med)
    
    candidates.append(base_template)  # full size
    
    small = base_template.replace(".png", "_small.png")
    if os.path.isfile(window_utils.resource_path(small)):
        candidates.append(small)
    
    # Remove the primary template if it's already in candidates
    if template_path in candidates:
        candidates.remove(template_path)
    
    # Try each candidate
    for candidate in candidates:
        candidate_path = window_utils.resource_path(candidate)
        result = find_template_at_best_scale(candidate_path)
        if result:
            scale, location = result
            return candidate_path, scale, location
    
    return None


def find_template_at_best_scale(template_path):
    """Find the best scale for a specific template.
    
    Returns:
        tuple: (scale, location) or None if not found
    """
    import vision_utils
    import cv2
    import numpy as np
    
    try:
        # Load template
        template_color = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template_color is None:
            return None
        
        template_gray = cv2.cvtColor(template_color, cv2.COLOR_BGR2GRAY)
        template_h, template_w = template_gray.shape[:2]
        
        # Take screenshot
        import pyautogui
        screenshot = pyautogui.screenshot()
        screen_img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
        screen_h, screen_w = screen_gray.shape[:2]
        
        # Try different scales
        scales_to_try = np.linspace(1.0, 0.4, 18)  # Start with full size, go down
        
        for scale in scales_to_try:
            t_h = int(template_h * scale)
            t_w = int(template_w * scale)
            
            if t_h <= 0 or t_w <= 0 or t_h > screen_h or t_w > screen_w:
                continue
            
            resized = cv2.resize(template_gray, (t_w, t_h), interpolation=cv2.INTER_AREA)
            
            result = cv2.matchTemplate(screen_gray, resized, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= 0.8:  # Same confidence as used elsewhere
                match_left = max_loc[0]
                match_top = max_loc[1]
                return scale, (match_left, match_top, t_w, t_h)
    
    except Exception as e:
        print(f"Error in find_template_at_best_scale: {e}")
    
    return None


def auto_calibrate(status_label=None):
    """Auto calibrate: use image detection to find the auction options button once."""

    def countdown(msg):
       
        for i in range(5, 0, -1):
            text = f"{msg} ({i})"
            print(text)
            if status_label:
                status_label.after(
                    0,
                    lambda: status_label.config(
                        text=text,
                        bootstyle="info"
                    )
                )
            time.sleep(1)

    
    countdown("Make sure FH5 window is in focus, and AUCTION OPTIONS button is visible. Calibration starts in 5 seconds.")

    try:
        import vision_utils

        status_label.after(
            0,
            lambda: status_label.config(
                text="Calibrating... looking for Auction Options button on screen, this may take a moment.",
                bootstyle="warning"
            )
        )
        
        # Use the same template path as the sniper
        base_template = "assets/auction_options_template.png"
        
        # Try to find the button and get detailed info about which template worked
        result = find_optimal_template_and_location(base_template)
        
        if result is None:
            print("❌ Auto calibration failed: Could not find Auction Options button")
            return False
        
        template_path, scale, location = result
        left, top, width, height = location
        
        # Add some padding around the detected button (similar to manual calibration)
        region = (
            left - PADDING_LEFT,
            top - PADDING_TOP,
            width + PADDING_LEFT + PADDING_RIGHT,
            height + PADDING_TOP + PADDING_BOTTOM
        )
        
        # Record FH5 window size while we're at it
        win = window_utils.get_fh5_window()
        baseline = {}
        if win:
            baseline = {
                "BASELINE_WINDOW_WIDTH": win.width,
                "BASELINE_WINDOW_HEIGHT": win.height,
            }
        
        # Save to config with auto prefix - include template and scale info
        cfg = {
            "AUTO_AUCTION_OPTIONS_REGION": region,
            "AUTO_AUCTION_OPTIONS_TEMPLATE": template_path,
            "AUTO_AUCTION_OPTIONS_SCALE": scale
        }
        cfg.update(baseline)
        try:
            with open(CONFIG_FILE, "r") as f:
                existing = json.load(f)
            existing.update(cfg)
            cfg = existing
        except FileNotFoundError:
            pass
        
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        
        print(f"✅ Auto calibration saved region: {region}, template: {template_path}, scale: {scale}")
        return True
            
    except Exception as e:
        print(f"❌ Auto calibration error: {e}")
        if status_label:
            status_label.after(
                0,
                lambda: status_label.config(
                    text=f"Auto calibration: ERROR - {e}",
                    bootstyle="danger"
                )
            )


def load_auto_region():
    """Return auto-calibrated region from config, or None if not set."""
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        return tuple(data["AUTO_AUCTION_OPTIONS_REGION"])
    except Exception:
        return None


def load_auto_template_info():
    """Return auto-calibrated template path and scale, or None if not set."""
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        # Try new keys first, then fall back to old keys for backward compatibility
        template_path = data.get("AUTO_AUCTION_OPTIONS_TEMPLATE") or data.get("AUTO_TEMPLATE_PATH")
        scale = data.get("AUTO_AUCTION_OPTIONS_SCALE") or data.get("AUTO_SCALE")
        if template_path and scale is not None:
            return template_path, scale
    except Exception:
        pass
    return None


def reset_auto_region(status_label=None):
    """Reset AUTO_AUCTION_OPTIONS_REGION in config."""
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    # Clear all auto calibration data
    keys_to_remove = [
        "AUTO_AUCTION_OPTIONS_REGION",
        "AUTO_AUCTION_OPTIONS_TEMPLATE",
        "AUTO_AUCTION_OPTIONS_SCALE"
    ]
    
    for key in keys_to_remove:
        if key in data:
            del data[key]

    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

    if status_label:
        status_label.after(
            0,
            lambda: status_label.config(
                text="Auto calibration: NOT SET",
                bootstyle="danger"
            )
        )