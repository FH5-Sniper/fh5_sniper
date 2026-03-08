# FH5 Sniper

This is a Python automation tool for Forza Horizon 5 that automatically scans and purchases cars from the auction house.

## Quick Start

1. Install dependencies: `pip install -r requirements.txt`
2. Run the application: `python app.py`
3. In Forza Horizon 5 (windowed mode), go to the Auction House
4. Perform calibration (Manual or Auto) to focus detection
5. Configure timing settings if needed
6. Start the sniper

## Features

- **Automatic Auction Scanning**: Continuously scans for available cars
- **Smart Detection**: Uses image recognition to find auction options
- **Calibration System**: Manual and automatic region calibration for accuracy
- **Timing Presets**: Fast/Mid/Slow presets based on PC and internet performance
- **Focus Safety**: Only sends keystrokes when FH5 is the active window
- **Real-time Logging**: GUI log with color-coded messages
- **Configurable Timings**: Adjustable delays for different system speeds
- **Standalone Executable**: Can be packaged as a single EXE file

## Architecture

- **app.py**: Tkinter GUI with multi-tab interface
- **sniper.py**: Core scanning and buying logic
- **vision_utils.py**: OpenCV-based template matching
- **calibrator.py**: Region calibration utilities
- **window_utils.py**: FH5 window detection and management
- **settings.py**: Configuration management
- **logger.py**: Thread-safe logging system

## Timing Presets

Choose from predefined timing presets based on your system performance:

- **Fast**: For high-end PCs with fast internet (0.4s buy interval, 4s post-buy wait, 0.8s reset)
- **Mid**: For average PCs with stable internet (0.6s buy interval, 5s post-buy wait, 0.9s reset)
- **Slow**: For slower PCs or laggy connections (0.7s buy interval, 6s post-buy wait, 1.1s reset)
- **Custom**: Manually adjust individual timing values

The preset selector automatically detects when your current settings match a preset.

## Packaging as a standalone executable

The project uses several PNG templates which are stored in the
`assets/` directory.  When building with PyInstaller, include that
folder by using the `--add-data` option and supply a custom icon/ name.
For example:

```powershell
pyinstaller --onefile --windowed \
  --name "FH5 Sniper" \
  --icon "assets\sniper.ico" \
  --add-data "assets;assets" \
  app.py
```

This produces `dist\FH5 Sniper.exe` with the red crosshair icon.  You can
also rename the resulting file manually if you prefer a different name.

The code resolves asset paths at runtime via `window_utils.resource_path`,
which handles both normal Python execution and the bundled `--onefile`
executable (`sys._MEIPASS`).

After building the EXE, copy the resulting `sniper.log` file (if needed)
and the `config.json` file alongside the executable, or use the
`--add-data` option again to bundle defaults.

## Dependencies

Install prerequisites with:

```bash
pip install -r requirements.txt
```

### Running the test suite

The `tests/` folder contains pytest tests covering configuration, window
utilities, sniper behaviour, calibration helpers and basic vision logic.
Use this command to execute them:

```bash
pytest -q
```

#### Vision detection tests

The vision tests simulate the screen by monkeypatching
`pyautogui.screenshot` to return one of the reference template images from
`assets/`.  You can add your own screenshots to `tests/` and extend
`tests/test_vision.py` if you want more realistic cases, e.g. an
`auction_options_available.png` and a matching `auction_options_missing.png`.
The same detection code is exercised -- if the template appears in the
screenshot the test will pass.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Buttons not found | Run calibration (Manual or Auto) |
| Slow scans | Use calibration to focus detection on smaller region |
| Keystrokes not working | Ensure FH5 window is focused and in foreground |
| Auto calibration fails | Try resizing FH5 window or use manual calibration |
| GUI not responding | Check console for errors; restart application |
| False positives | Adjust timing intervals in Settings tab |

## Notes

- The GUI buffer keeps the last 10 000 log lines; all messages are also
  written to `sniper.log`.
- Focus detection prevents the tool from sending keystrokes when FH5 is
  not the foreground window.

## Support the Project

If you like the tool and want to support the development and future releases, you can make a donation via PayPal:

[💖 Donate via PayPal](https://www.paypal.com/ncp/payment/W2FY4KHD58UEG)

Every contribution helps fund updates, improvements, and future tools, thank you for your support!