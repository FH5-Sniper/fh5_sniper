import json
import os

import calibrator
import settings


def test_has_manual_region(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    # no file -> False
    monkeypatch.setattr(calibrator, "CONFIG_FILE", str(cfg))
    assert not calibrator.has_manual_region()
    # create with region
    data = {"AUCTION_OPTIONS_REGION": [1,2,3,4]}
    cfg.write_text(json.dumps(data))
    assert calibrator.has_manual_region()
