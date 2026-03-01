import json
import os
import window_utils

CONFIG_FILE = window_utils.get_config_file()

# Validation limits
MIN_INTERVAL = 0.1  # minimum delay between keystrokes
MAX_INTERVAL = 20.0  # maximum interval to prevent unbearably slow execution
MIN_SCANS = 1
MAX_SCANS = 100000

# All default values
DEFAULT_CONFIG = {
    "scans": 1000,  # previously 'attempts'
    "TIMINGS": {
        "buy_attempt_interval": 0.4,
        "post_buy_wait": 5.0,
        "reset_interval": 0.8,
    },
    "BASELINE_WINDOW_WIDTH": 1622,
    "BASELINE_WINDOW_HEIGHT": 956,
    # whether to skip the popup warning about missing manual calibration
    "SKIP_CALIBRATION_WARNING": False,
    # AUCTION_OPTIONS_REGION is optional (only set via manual calibration)
}

DEFAULT_TIMINGS = DEFAULT_CONFIG["TIMINGS"].copy()


def validate_settings(timings_dict, scans_value):
    """Validate timing and scans settings.
    
    Returns:
        (is_valid, error_message, corrected_values_dict)
    """
    errors = []
    corrected = {
        "timings": timings_dict.copy(),
        "scans": scans_value
    }
    
    # Validate scans
    if scans_value < MIN_SCANS:
        errors.append(f"Number of Scans must be at least {MIN_SCANS}")
        corrected["scans"] = MIN_SCANS
    elif scans_value > MAX_SCANS:
        errors.append(f"Number of Scans cannot exceed {MAX_SCANS}")
        corrected["scans"] = MAX_SCANS
    
    # Validate intervals
    interval_names = {
        "buy_attempt_interval": "Buy Interval",
        "post_buy_wait": "Post Buy Wait",
        "reset_interval": "Reset Interval"
    }
    
    for key, display_name in interval_names.items():
        val = timings_dict.get(key, 0)
        if val < MIN_INTERVAL:
            errors.append(f"{display_name} must be at least {MIN_INTERVAL}")
            corrected["timings"][key] = MIN_INTERVAL
        elif val > MAX_INTERVAL:
            errors.append(f"{display_name} cannot exceed {MAX_INTERVAL}")
            corrected["timings"][key] = MAX_INTERVAL
    
    return (len(errors) == 0, "; ".join(errors) if errors else "", corrected)


def load_config():
    """Load full config with defaults merged."""
    try:
        with open(CONFIG_FILE, "r") as f:
            user_config = json.load(f)
        # Merge: user config overrides defaults
        config = DEFAULT_CONFIG.copy()
        config.update(user_config)
        # migration from old key name
        if "attempts" in config:
            config["scans"] = config.pop("attempts")
            save_config(config)
        
        # MIGRATION FIRST: handle deprecated keys before validation
        if "TIMINGS" in user_config:
            # merge only known timing keys, ignore deprecated ones
            user_times = {k: v for k, v in user_config.get("TIMINGS", {}).items() if k in DEFAULT_TIMINGS}
            # migrate old menu_interval if present
            if "menu_interval" in user_config.get("TIMINGS", {}):
                val = user_config["TIMINGS"].get("menu_interval")
                user_times.setdefault("buy_attempt_interval", val)
            config["TIMINGS"] = {**DEFAULT_TIMINGS, **user_times}
            # if there were deprecated keys in the original user_config, clean them from file
            deprecated = [k for k in user_config.get("TIMINGS", {}) if k not in DEFAULT_TIMINGS]
            if deprecated:
                # rewrite to remove them
                save_config(config)
        
        # Validate and fix scans value
        if config["scans"] < MIN_SCANS or config["scans"] > MAX_SCANS:
            config["scans"] = max(MIN_SCANS, min(MAX_SCANS, config["scans"]))
            save_config(config)
        
        # Validate and fix timing intervals
        if "TIMINGS" in config:
            needs_save = False
            for key in ["buy_attempt_interval", "post_buy_wait", "reset_interval"]:
                val = config["TIMINGS"].get(key, 0)
                if val < MIN_INTERVAL:
                    config["TIMINGS"][key] = MIN_INTERVAL
                    needs_save = True
                elif val > MAX_INTERVAL:
                    config["TIMINGS"][key] = MAX_INTERVAL
                    needs_save = True
            if needs_save:
                save_config(config)
        
        return config
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(config):
    """Save config to file."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def load_timings():
    """Load timings for runtime use (sniper)."""
    config = load_config()
    return config["TIMINGS"]


def load_timings_ui():
    """Load timings for UI fields."""
    return load_timings()


def save_timings_ui(timings_dict, scans_value):
    """Save timings and total scans from UI with validation.
    
    Returns:
        (success, error_message, corrected_values)
    """
    is_valid, error_msg, corrected = validate_settings(timings_dict, scans_value)
    
    # Save corrected values even if there were errors
    config = load_config()
    config["TIMINGS"] = corrected["timings"]
    config["scans"] = corrected["scans"]
    save_config(config)
    
    return (is_valid, error_msg, corrected)


def get_scans():
    """Get number of scans from config."""
    config = load_config()
    return config.get("scans", 1000)

def get_skip_calibration_warning():
    """Return True if the user opted out of the calibration popup."""
    config = load_config()
    return config.get("SKIP_CALIBRATION_WARNING", False)

def set_skip_calibration_warning(value: bool):
    """Persist the user's choice about the calibration popup."""
    config = load_config()
    config["SKIP_CALIBRATION_WARNING"] = bool(value)
    save_config(config)


def set_scans(value):
    """Set number of scans in config."""
    config = load_config()
    config["scans"] = value
    save_config(config)


def reset_to_defaults():
    """Reset all settings to defaults, preserving manual calibration if it exists."""
    try:
        with open(CONFIG_FILE, "r") as f:
            current_config = json.load(f)
    except:
        current_config = {}
    
    # Preserve manual calibration if it exists
    manual_region = current_config.get("AUCTION_OPTIONS_REGION")
    
    # Restore defaults
    config = DEFAULT_CONFIG.copy()
    if manual_region:
        config["AUCTION_OPTIONS_REGION"] = manual_region
    
    save_config(config)
    return config