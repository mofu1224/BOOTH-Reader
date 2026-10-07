"""Full UI automation driver is test-only and never part of the Mac payload."""

import sys
from pathlib import Path

from core.browser import launch_browser as launch_runtime_browser


def launch_browser(playwright, *, headless=False):
    if sys.platform == "darwin":
        executable = (
            Path(__file__).resolve().parent.parent
            / ".cache/ui-test-driver/Google Chrome.app/Contents/MacOS/Google Chrome"
        )
        return playwright.chromium.launch(headless=headless, executable_path=str(executable))
    return launch_runtime_browser(playwright, headless=headless)
