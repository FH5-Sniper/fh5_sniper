import pyautogui
import time
import json
import logger
import window_utils
import vision_utils

# disable PyAutoGUI's built-in failsafe (moving mouse to corner raises
# an exception) since we handle focus checks ourselves and the popup
# message wasn't user-friendly in normal operation.
pyautogui.FAILSAFE = False

CONFIDENCE = 0.8
CONFIG_FILE = "config.json"

# -------------------------
# CONFIG HELPERS
# -------------------------

DEFAULT_TIMINGS = {
    # interval used for both pre-press pause and menu navigation during buy attempts
    "buy_attempt_interval": 0.4,
    "post_buy_wait": 5.0,
    "reset_interval": 0.8,
}

def load_config():
    """Load config with safe defaults."""
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    # Ensure timings exist
    if "TIMINGS" not in data:
        data["TIMINGS"] = DEFAULT_TIMINGS.copy()

    return data


def load_region():
    data = load_config()
    return tuple(data["AUCTION_OPTIONS_REGION"])


def load_timings():
    data = load_config()
    return data["TIMINGS"]

# -------------------------
# DETECTION
# -------------------------

def car_available(region):
    """
    Check if the 'Auction Options' button is available using image detection.

    Args:
        region (tuple): Region tuple (left, top, width, height) to search in.
                        It is assumed the caller precomputes this.
    Returns:
        bool: True if button found, False otherwise.
    """
    try:
        if region is None:
            # caller forgot to supply region; try fallback path
            fallback = load_region()
            region = window_utils.get_fh5_region_safe(fallback_region=fallback)
            if region is None:
                print("WARNING: No detection region available")
                return False

        # determine which template to use based on the *full* window size.
        # the caller usually passes a cropped region (bottom-left quarter) so
        # using that directly would misclassify the window as "small".  we
        # still keep `region` unchanged for the actual screenshot search.
        win = window_utils.get_fh5_window()
        if win:
            full_window_region = window_utils.get_window_region(win)
        else:
            full_window_region = None

        # use the window region for template decisions; fall back to provided
        # region only when the window can't be located.
        size_region = full_window_region if full_window_region is not None else region

        # prepare window size tuple for scale hint (used elsewhere)
        current_window_size = (win.width, win.height) if win else None

        # read baseline from config if available
        cfg = load_config()
        baseline_window_size = None
        bw = cfg.get("BASELINE_WINDOW_WIDTH")
        bh = cfg.get("BASELINE_WINDOW_HEIGHT")
        if bw and bh:
            baseline_window_size = (bw, bh)

        base_template = window_utils.resource_path("assets/auction_options_template.png")
        template, size_cat = vision_utils.choose_template(
            base_template,
            region=size_region,
            debug=False,
        )
        # determine numeric thresholds per category
        if size_cat == "small":
            base_min = 0.7
            conf = 0.65
        elif size_cat == "medium":
            base_min = 0.5
            conf = 0.70
        else:
            base_min = 0.35
            conf = 0.72
        # fixed range, nothing fancy
        scale_min, scale_max = base_min, 1.0

        # starting hint = middle of the permitted interval (caching may override)
        scale_hint_val = (scale_min + scale_max) / 2
        location = vision_utils.locate_on_screen_with_variants(
            base_template,
            region=region,
            confidence=conf,
            grayscale=True,
            scale_min=scale_min,
            scale_max=scale_max,
            scale_hint=scale_hint_val,
            hint_margin=0.12,
            debug=False,
        )
       
        return location is not None
    except Exception as e:
        print(f"Error in car_available: {e}")
        return False

# -------------------------
# ACTIONS
# -------------------------

def buy_sequence(t, full_region=None, stop_flag=None):
    """Perform buy sequence and detect success/failure via screenshots.

    Args:
        t: timing configuration dict
        full_region: optional region to limit post-buy image searches (entire window)

    Returns:
      True if buy succeeded, False if failed, None if undetermined.
    """
    # If FH5 is not focused, abort the buy attempt immediately to avoid
    # sending keystrokes to other applications. The loop caller will detect
    # this and stop the sniper.
    try:
        if not window_utils.is_fh5_focused():
            logger.update_log("🔒 Buy sequence aborted: FH5 not focused")
            # not sending keystrokes; caller will treat result as undetermined
            return None
    except Exception:
        # conservative fallback: abort
        return None

    pyautogui.press('y')
    # brief pause and navigation use same buy_attempt_interval
    interval = t.get("buy_attempt_interval", 0.4)
    time.sleep(interval)

    pyautogui.typewrite(['down', '\n', '\n'], interval=interval)
    time.sleep(t["post_buy_wait"])

    # After waiting, check for success/failure images on screen
    result = None
    try:
        if full_region is not None:
            # choose success/failure templates based on full_region size
            base_succ = window_utils.resource_path("assets/buyout_successful_template.png")
            base_fail = window_utils.resource_path("assets/buyout_failed_template.png")
            tpl_succ, cat_succ = vision_utils.choose_template(
                base_succ,
                region=full_region,
                debug=False,
            )
            tpl_fail, cat_fail = vision_utils.choose_template(
                base_fail,
                region=full_region,
                debug=False,
            )
            # pick the strictest category among the two templates
            if "small" in (cat_succ, cat_fail):
                size_cat = "small"
            elif "medium" in (cat_succ, cat_fail):
                size_cat = "medium"
            else:
                size_cat = "full"

            if size_cat == "small":
                base_min = 0.7
                conf = 0.65
            elif size_cat == "medium":
                base_min = 0.5
                conf = 0.70
            else:
                base_min = 0.35
                conf = 0.72

            # fixed range again
            scale_min, scale_max = base_min, 1.0
            print(
                f"Using {size_cat} buyout templates: {tpl_succ}, {tpl_fail} "
                f"(confidence={conf}, scales {scale_min:.3f}-{scale_max:.3f})"
            )
            scale_hint_val = (scale_min + scale_max) / 2

            if vision_utils.locate_on_screen_with_variants(
                base_succ,
                region=full_region,
                confidence=conf,
                grayscale=True,
                scale_min=scale_min,
                scale_max=scale_max,
                scale_hint=scale_hint_val,
                hint_margin=0.12,
                debug=False,
            ) is not None:
                result = True
            elif vision_utils.locate_on_screen_with_variants(
                base_fail,
                region=full_region,
                confidence=conf,
                grayscale=True,
                scale_min=scale_min,
                scale_max=scale_max,
                scale_hint=scale_hint_val,
                hint_margin=0.12,
                debug=False,
            ) is not None:
                result = False
        else:
            # fallback to whole screen if no region provided
            print("⚠️  No full_region provided for buy detection, scanning entire screen")
            base_succ = window_utils.resource_path("assets/buyout_successful_template.png")
            base_fail = window_utils.resource_path("assets/buyout_failed_template.png")
            tpl_succ, cat_succ = vision_utils.choose_template(
                base_succ,
                region=None,
                debug=False,
            )
            tpl_fail, cat_fail = vision_utils.choose_template(
                base_fail,
                region=None,
                debug=False,
            )
            if "small" in (cat_succ, cat_fail):
                size_cat = "small"
            elif "medium" in (cat_succ, cat_fail):
                size_cat = "medium"
            else:
                size_cat = "full"
            if size_cat == "small":
                base_min = 0.7
                conf = 0.65
            elif size_cat == "medium":
                base_min = 0.5
                conf = 0.70
            else:
                base_min = 0.35
                conf = 0.72
            scale_min, scale_max = base_min, 1.0
            scale_hint_val = (scale_min + scale_max) / 2
            if vision_utils.locate_on_screen_with_variants(
                base_succ,
                confidence=conf,
                grayscale=True,
                scale_min=scale_min,
                scale_max=scale_max,
                scale_hint=scale_hint_val,
                hint_margin=0.12,
                debug=False,
            ) is not None:
                result = True
            elif vision_utils.locate_on_screen_with_variants(
                base_fail,
                confidence=conf,
                grayscale=True,
                scale_min=scale_min,
                scale_max=scale_max,
                scale_hint=scale_hint_val,
                hint_margin=0.12,
                debug=False,
            ) is not None:
                result = False
    except Exception as e:
        print(f"Error detecting buy result: {e}")

    pyautogui.typewrite(['\n', 'esc', 'esc', '\n', '\n'], interval=t["reset_interval"])
    print("Attempt complete — returned to start.")
    return result

def reset_search(t, stop_flag=None):
    # Wait for FH5 focus before sending the reset keystrokes; if the user
    # clicks away, this will pause instead of sending Esc to other apps.
    try:
        if not window_utils.wait_for_fh5_focus(stop_flag=stop_flag):
            return
    except Exception:
        pass
    # final safety check
    try:
        if not window_utils.is_fh5_focused():
            logger.update_log("🔒 Reset aborted: FH5 not focused")
            return
    except Exception:
        return
    pyautogui.typewrite(['esc', '\n', '\n'], interval=t["reset_interval"])

# -------------------------
# MAIN LOOP
# -------------------------

def sniper_loop(logger_callback, region, scans, timings, stop_flag, status_callback=None):
    """
    Main sniper loop for detecting and buying cars.

    Args:
        logger_callback: Function to log messages
        region: Initial region from config (used as fallback)
        scans: Number of scan iterations (each one may refresh)
        timings: Timing configuration
        stop_flag: Dict with 'stop' key to signal loop termination
        status_callback: Optional callback for UI updates
    """
    try:
        # Prompt the user to focus FH5 before starting, then countdown
        try:
            logger_callback("⚠️ Please focus Forza Horizon 5 now — click inside the FH5 window to allow inputs.")
        except Exception:
            pass

        # Pre-start countdown
        for i in range(5, 0, -1):
            if stop_flag["stop"]:
                logger_callback("🛑 Sniper stopped before starting")
                return
            logger_callback(f"Starting in {i}...")
            time.sleep(1)

        # compute regions once before loop
        logger_callback("🔍 Computing detection regions")
        config_region = region  # passed in from caller

        # prefer a manually-saved region from config if present
        cfg = load_config()
        manual_region = tuple(cfg["AUCTION_OPTIONS_REGION"]) if "AUCTION_OPTIONS_REGION" in cfg else None

        window = window_utils.get_fh5_window()
        if window:
            full_region = window_utils.get_window_region(window)
        else:
            full_region = None

        if manual_region:
            # If user manually calibrated, use that region for detection
            bottom_left_region = manual_region
            # ensure buy-detection has a sensible full_region fallback
            if full_region is None:
                full_region = manual_region
            logger_callback(f"✅ Using manual calibrated region: {manual_region}")
        elif full_region:
            bottom_left_region = window_utils.bottom_left_quarter(full_region)
            logger_callback(f"✅ Using FH5 window bounds: {full_region}, bottom-left quarter: {bottom_left_region}")
        else:
            full_region = config_region
            bottom_left_region = window_utils.bottom_left_quarter(config_region) if config_region else None
            logger_callback("⚠️  FH5 window not found, using configured region for scans")

        logger_callback("🚀 Sniper starting now!")
        successes = 0
        failures = 0
        buy_attempts = 0
        refreshes = 0

        for i in range(scans):
            # normal loop

            # stop if requested
            if stop_flag["stop"]:
                logger_callback("🛑 Sniper stopped by user")
                break

            try:
                if not window_utils.is_fh5_focused():
                    logger_callback("🛑 FH5 lost focus - stopping sniper")
                    stop_flag["stop"] = True
                    break
            except Exception:
                logger_callback("🛑 Focus check error, stopping sniper")
                stop_flag["stop"] = True
                break

            # execute iteration inside its own try/except in case of unexpected errors
            try:
                # use precomputed bottom_left_region for detection
                if car_available(region=bottom_left_region):
                    buy_attempts += 1
                    logger_callback(f"Scan #{i+1} ✅ Car found — buying! (Attempt #{buy_attempts})")

                    # Notify UI immediately that a buy attempt started (include scans done)
                    if status_callback:
                        try:
                            status_callback(buy_attempts, successes, failures, refreshes, i+1)
                        except Exception:
                            pass

                    result = buy_sequence(timings, full_region=full_region, stop_flag=stop_flag)
                    if result is True:
                        successes += 1
                        logger_callback(f"Attempt #{buy_attempts} ✅ Buy successful")
                    elif result is False:
                        failures += 1
                        logger_callback(f"Attempt #{buy_attempts} ❌ Buy failed")
                    else:
                        logger_callback(f"Attempt #{buy_attempts} ⚠️ Result undetermined")

                    # Report stats to UI if callback provided
                    if status_callback:
                        try:
                            status_callback(buy_attempts, successes, failures, refreshes, i+1)
                        except Exception:
                            pass

                else:
                    refreshes += 1
                    logger_callback(f"Scan #{i+1} ❌ No car - refreshing...")
                    reset_search(timings, stop_flag=stop_flag)

                    # Report refresh count to UI (include scans done)
                    if status_callback:
                        try:
                            status_callback(buy_attempts, successes, failures, refreshes, i+1)
                        except Exception:
                            pass

            except Exception as scan_err:
                logger_callback(f"❌ Error during scan #{i+1}: {scan_err}")
                stop_flag["stop"] = True
                break
    except Exception as overall_err:
        try:
            logger_callback(f"🔴 Unhandled error in sniper loop: {overall_err}")
        except Exception:
            pass
        stop_flag["stop"] = True

    finally:
        stop_flag["stop"] = False
        logger_callback("✅ Sniper stopped")
