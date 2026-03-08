"""Vision utilities with multi-scale template matching.

This module provides a drop-in replacement for PyAutoGUI's
`locateOnScreen` that can handle scaled templates. Templates are assumed to be
captured at full screen resolution; when the game runs at a lower resolution or
in a window, the template is scaled down during matching.

The core function `locate_on_screen_scaled` mimics the PyAutoGUI API but uses
OpenCV internals for performance and scale awareness.
"""

import os
from typing import Optional, Tuple

import cv2
import numpy as np
import pyautogui

import window_utils  # for window size queries

# simple in-memory cache for loaded templates to avoid disk I/O
_template_cache = {}

# remember the last successful scale for each template path; helps narrow
# future searches when the window size is stable.
_last_scale_hint = {}


# thresholds for distinguishing window sizes relative to the screen.
# if either dimension is below SMALL -> use small template
# if between SMALL and MED -> medium template (if available)
# otherwise use full template.  these numbers were chosen based on the
# behaviour users reported when resizing the FH5 window.
SMALL_PERCENT_WIDTH = 0.50   # 50% of screen width
SMALL_PERCENT_HEIGHT = 0.50  # 50% of screen height
MED_PERCENT_WIDTH = 0.80     # up to 80% of screen width is considered medium
MED_PERCENT_HEIGHT = 0.80    # up to 80% of screen height is considered medium


def choose_template(base_path: str, region: Optional[Tuple[int, int, int, int]] = None, debug: bool = False):
    """Return appropriate template path depending on region size relative to screen.

    Args:
        base_path: path to the fullscreen template (e.g. "auction_options_template.png").
        region: optional region tuple whose dimensions are used instead of the
                actual window. If None, tries to query the FH5 window.
        debug: whether to emit informational prints.

    Returns:
        (path, is_small) tuple where "path" is either the base_path or the
        corresponding small-template variant, and is_small is a bool flag.
    """
    # get screen dimensions for relative comparison
    screen_w, screen_h = pyautogui.size()
    if debug:
        print(f"screen size: {screen_w}x{screen_h}")
    
    # determine window/region dimensions
    w = h = 0
    if region:
        _, _, w, h = region
    else:
        win = window_utils.get_fh5_window()
        if win:
            w, h = win.width, win.height
    
    # compare to screen as percentages
    category = "full"
    if w and h:
        w_percent = w / screen_w
        h_percent = h / screen_h
        if debug:
            print(f"window size: {w}x{h} ({w_percent*100:.1f}% x {h_percent*100:.1f}%)")
        # small if either dim < small threshold
        if w_percent < SMALL_PERCENT_WIDTH or h_percent < SMALL_PERCENT_HEIGHT:
            category = "small"
        # medium if not small and either dim < med threshold
        elif w_percent < MED_PERCENT_WIDTH or h_percent < MED_PERCENT_HEIGHT:
            category = "medium"

        # choose appropriate filename
        if category == "small":
            candidate = base_path.replace(".png", "_small.png")
        elif category == "medium":
            candidate = base_path.replace(".png", "_med.png")
        else:
            candidate = base_path

        if category != "full" and os.path.isfile(candidate):
            chosen = candidate
        else:
            chosen = base_path
    else:
        chosen = base_path
    
    if debug:
        print(f"template selection: chose {category} -> {chosen}")
    # return category string for downstream logic
    return chosen, category


def compute_scale_bounds(
    template_path: str,
    region: Optional[Tuple[int, int, int, int]] = None,
    fallback_min: float = 0.35,
    fallback_max: float = 1.0,
    margin: float = 0.10,
) -> Tuple[float, float]:
    """Return simple bounds for template scaling.

    At the moment this helper does nothing more than echo back the provided
    fallbacks.  It exists to keep the API stable in case we revisit more
    sophisticated heuristics later, but callers should not rely on hints from
    region or window size – those have proved unreliable in practice.
    """
    return fallback_min, fallback_max


def _load_template(image_path: str, debug: bool = False):
    """Load template as a numpy array (BGR) and cache the result.

    Args:
        image_path: path to template
        debug: whether to print loading message
    """
    if image_path in _template_cache:
        if debug:
            print(f"Template '{image_path}' retrieved from cache")
        return _template_cache[image_path]

    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Template not found: {image_path}")

    # read in color by default; convert to gray later
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Failed to load image: {image_path}")

    _template_cache[image_path] = img
    if debug:
        print(f"Loaded template '{image_path}' (cached)")
    return img



def locate_on_screen_with_variants(
    base_path: str,
    region=None,
    confidence: float = 0.8,
    grayscale: bool = True,
    scale_min: float = 0.4,
    scale_max: float = 1.0,
    scale_steps: int = 18,
    debug: bool = False,
    scale_hint: Optional[float] = None,
    hint_margin: float = 0.10,
) -> Optional[Tuple[int, int, int, int]]:
    """Attempt to locate a template and its size variants.

    The method first calls :func:`choose_template` to pick a primary file path
    (small/medium/full).  If no match is found using that template, additional
    candidates are tried in this order:
    1. medium variant (``*_med.png``) if it exists
    2. full-size base template
    3. small variant (``*_small.png``) if it exists

    This makes the detection resilient when the window-size heuristic
    misclassifies the current scaling.
    """
    # determine primary candidate and category (debug flag matters)
    template, category = choose_template(base_path, region=region, debug=debug)
    candidates = [template]

    # helper to add file if exists and not already present
    def maybe_add(path):
        if path not in candidates and os.path.isfile(path):
            candidates.append(path)

    # medium variant
    med = base_path.replace(".png", "_med.png")
    maybe_add(med)
    # full base template
    maybe_add(base_path)
    # small variant
    small = base_path.replace(".png", "_small.png")
    maybe_add(small)

    if debug:
        print(f"searching variants: {candidates}")

    for tpl in candidates:
        if tpl == template:
            # inherit the provided scale_hint for the primary candidate
            hint = scale_hint
        else:
            hint = None
        loc = locate_on_screen_scaled(
            tpl,
            region=region,
            confidence=confidence,
            grayscale=grayscale,
            scale_min=scale_min,
            scale_max=scale_max,
            scale_steps=scale_steps,
            debug=debug,
            scale_hint=hint,
            hint_margin=hint_margin,
        )
        if loc is not None:
            return loc
    return None


def locate_on_screen_scaled(
    image_path: str,
    region=None,
    confidence: float = 0.8,
    grayscale: bool = True,
    scale_min: float = 0.4,
    scale_max: float = 1.0,
    scale_steps: int = 18,
    debug: bool = False,
    scale_hint: Optional[float] = None,
    hint_margin: float = 0.10,
) -> Optional[Tuple[int, int, int, int]]:
    """Search the screen or region for a template at multiple scales.

    Args:
        image_path: Path to the single template image (assumed fullscreen).
        region: Optional (left, top, width, height) to limit search.
        confidence: Matching threshold (0-1); same semantics as PyAutoGUI.
        grayscale: Whether to convert images to grayscale for matching.
        scale_min: Minimum scale factor (relative to original template).
        scale_max: Maximum scale factor. Should normally be 1.0.
        scale_steps: Number of intermediate scales to try.
        debug: Print detailed information about each scale.

    Returns:
        A 4-tuple (left, top, width, height) in screen coordinates if found,
        otherwise `None`.
    """
    # take screenshot of region or full screen
    try:
        if region:
            left, top, w, h = region
            screenshot = pyautogui.screenshot(region=region)
        else:
            left, top = 0, 0
            screenshot = pyautogui.screenshot()
    except Exception as e:
        print(f"⚠️  Error taking screenshot: {e}")
        return None

    # convert screenshot to numpy BGR array
    screen_img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    if grayscale:
        screen_proc = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
    else:
        screen_proc = screen_img

    template_color = _load_template(image_path, debug=debug)
  
    if grayscale:
        template_proc = cv2.cvtColor(template_color, cv2.COLOR_BGR2GRAY)
    else:
        template_proc = template_color

    screen_h, screen_w = screen_proc.shape[:2]

    # decide which scales to try first
    scales_to_try = None
    # accept an explicit hint or fall back to cached hint
    if scale_hint is None:
        scale_hint = _last_scale_hint.get(image_path)
    if scale_hint is not None:
        # compute a tight window around the hint
        low = max(scale_min, scale_hint * (1.0 - hint_margin))
        high = min(scale_max, scale_hint * (1.0 + hint_margin))
        scales_to_try = np.linspace(high, low, scale_steps)
    else:
        scales_to_try = np.linspace(scale_max, scale_min, scale_steps)

    # iterate over candidate scales
    for scale in scales_to_try:

        # compute resized template size
        t_h = int(template_proc.shape[0] * scale)
        t_w = int(template_proc.shape[1] * scale)

        # skip impossible scales
        if t_h <= 0 or t_w <= 0 or t_h > screen_h or t_w > screen_w:
            continue

        resized = cv2.resize(template_proc, (t_w, t_h), interpolation=cv2.INTER_AREA)

        # do the matching
        try:
            result = cv2.matchTemplate(screen_proc, resized, cv2.TM_CCOEFF_NORMED)
        except Exception as e:
            print(f"⚠️  Error during matchTemplate at scale {scale}: {e}")
            continue

        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if debug:
            print(f"scale={scale:.3f} max_val={max_val:.3f}")

        if max_val >= confidence:
            # remember this scale for next time
            _last_scale_hint[image_path] = scale
            # match found - compute screen coords
            match_left = left + max_loc[0]
            match_top = top + max_loc[1]
            # width/height should be size of resized template
            
            return (match_left, match_top, t_w, t_h)

    # if we tried a hinted window and failed, fall back to full range once
    if scale_hint is not None and scales_to_try is not None:
        # check if the hint-limited search covered entire interval; if not,
        # run once over the full range.
        full_range = np.linspace(scale_max, scale_min, scale_steps)
        if not np.array_equal(full_range, scales_to_try):
            for scale in full_range:
                t_h = int(template_proc.shape[0] * scale)
                t_w = int(template_proc.shape[1] * scale)
                if t_h <= 0 or t_w <= 0 or t_h > screen_h or t_w > screen_w:
                    continue
                resized = cv2.resize(template_proc, (t_w, t_h), interpolation=cv2.INTER_AREA)
                try:
                    result = cv2.matchTemplate(screen_proc, resized, cv2.TM_CCOEFF_NORMED)
                except Exception:
                    continue
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                if debug:
                    print(f"scale={scale:.3f} max_val={max_val:.3f}")
                if max_val >= confidence:
                    _last_scale_hint[image_path] = scale
                    match_left = left + max_loc[0]
                    match_top = top + max_loc[1]
                    return (match_left, match_top, t_w, t_h)
    # no match found
    if debug:
        print(f"no match for '{image_path}' (confidence {confidence})")
    return None
