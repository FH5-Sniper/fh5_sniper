# FH5 Sniper

This is a Python automation tool for Forza Horizon 5.

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

## Notes

- The GUI buffer keeps the last 10 000 log lines; all messages are also
  written to `sniper.log`.
- Focus detection prevents the tool from sending keystrokes when FH5 is
  not the foreground window.
