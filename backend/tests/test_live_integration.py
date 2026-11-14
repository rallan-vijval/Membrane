"""Opt-in only: real credentials and billable API calls. Never use test doubles here."""
import os
import subprocess
import sys

import pytest

from backend.app.config import ROOT


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RUN_LIVE_INTEGRATION") != "1", reason="Set RUN_LIVE_INTEGRATION=1 after configuring credentials; billable")
def test_real_atlas_provider_and_known_neighbor_preflight():
    result = subprocess.run([sys.executable, "-m", "scripts.backend_setup", "preflight"], cwd=ROOT,
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout
