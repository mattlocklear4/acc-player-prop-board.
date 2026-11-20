#!/usr/bin/env python3
"""Offline smoke test for minute-adjusted Friday publishing. No network or DB."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("acc_publish_friday_board.py").resolve()
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    (root / "research").mkdir()
    slate = {"date_eastern": "2026-11-20", "games": [{
        "game_id": "g1", "teams": [{"team": "Example", "players": [
            {"Player": "Starter", "AthleteId": "1", "Minutes": 30,
             "BaselinePoints": 15, "KenPomPoints": 16, "BaselineAssists": 6},
            {"Player": "Unavailable", "AthleteId": "2", "Minutes": 20,
             "BaselinePoints": 10}]}]}]}
    reviews = {"rows": [
        {"game_id": "g1", "team": "Example", "athlete_id": "1",
         "rotation_minutes_scenario": 36, "rotation_minutes_delta": 6,
         "usage_pct_last5": 21.5, "availability_status": None},
        {"game_id": "g1", "team": "Example", "athlete_id": "2",
         "rotation_minutes_scenario": 0, "rotation_minutes_delta": -20,
         "usage_pct_last5": 15, "availability_status": "out"}]}
    (root / "research/acc_friday_slate.json").write_text(json.dumps(slate))
    (root / "research/acc_friday_minutes_review.json").write_text(json.dumps(reviews))
    subprocess.run([sys.executable, str(SCRIPT)], cwd=root, check=True, capture_output=True)
    output = json.loads((root / "data/friday_board.json").read_text())
    starter, unavailable = output["games"][0]["teams"][0]["players"]
    assert starter["BaselinePoints"] == 15
    assert starter["RotationBaselinePoints"] == 18
    assert starter["RotationKenPomPoints"] == 19.2
    assert starter["RotationBaselineAssists"] == 7.2
    assert starter["RecentUsagePct"] == 21.5
    assert starter["RotationScenarioVerified"] is False
    assert unavailable["RotationBaselinePoints"] == 0
    assert unavailable["AvailabilityStatus"] == "out"
print("Friday rotation projection publishing: 8 assertions passed; no network calls")
