"""
Automated attendance taker for Android emulator.

Prereqs:
  1. Android Studio AVD or Genymotion running, with Google Play image.
  2. `adb` on PATH. Verify: `adb devices` shows your emulator.
  3. pip install uiautomator2
  4. First run: `python -m uiautomator2 init` (installs helper APK on device).
  5. Manually install + log into your attendance app once on the emulator.
     Take an AVD snapshot after login so it persists.

Configure the CONFIG block below for your specific app, then run:
  python attendance.py
"""

import subprocess
import sys
import time
import logging
from pathlib import Path

import uiautomator2 as u2

# ---------------------------------------------------------------------------
# CONFIG — fill these in for your specific app and location
# ---------------------------------------------------------------------------
CONFIG = {
    # Your target coordinates (decimal degrees). Menara 1 Sentrum, KL Sentral.
    "latitude":  3.1346,
    "longitude": 101.6864,
    # Optional altitude in meters (some apps check this).
    "altitude":  50.0,

    # Android package name of the attendance app.
    # Find it: `adb shell pm list packages | grep -i <app_name>`
    "package":   "com.example.attendance",

    # Main/launcher activity. Find it with:
    # `adb shell cmd package resolve-activity --brief <package>`
    # Leave as None to use monkey launcher (works for most apps).
    "activity":  None,

    # The UI steps to perform, in order. Each step is a dict.
    # Prefer `text`, `resourceId`, or `description` over raw coordinates —
    # they survive UI shifts, unlike xy taps.
    "steps": [
        {"action": "wait",  "seconds": 4, "note": "let app load"},
        {"action": "click", "text": "Check In",      "timeout": 15},
        {"action": "wait",  "seconds": 2},
        {"action": "click", "text": "Confirm",       "timeout": 10},
        {"action": "wait",  "seconds": 3, "note": "let submission register"},
        # Fallback example using coordinates (only if text/id not findable):
        # {"action": "tap_xy", "x": 540, "y": 1600},
    ],

    # Where to dump UI hierarchy + screenshot on failure, for debugging.
    "debug_dir": "debug",

    # Retry the whole flow this many times if it fails.
    "max_attempts": 2,
}
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("attendance")


def sh(cmd: str, check: bool = True) -> str:
    """Run a shell command, return stdout."""
    log.debug("$ %s", cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\nstderr: {r.stderr}")
    return r.stdout.strip()


def find_emulator_console() -> str | None:
    """Return the emulator console port (e.g. 'emulator-5554') or None."""
    out = sh("adb devices", check=False)
    for line in out.splitlines()[1:]:
        if "emulator-" in line and "device" in line:
            return line.split()[0]
    return None


def set_gps(lat: float, lng: float, alt: float = 0.0) -> None:
    """
    Set GPS via emulator console. Order is (longitude latitude altitude).
    Works for AVD; Genymotion exposes the same command.
    """
    dev = find_emulator_console()
    if not dev:
        raise RuntimeError(
            "No emulator detected. Start AVD/Genymotion and verify `adb devices`."
        )
    port = dev.split("-")[1]
    # `adb emu` talks to the emulator's telnet console.
    sh(f'adb -s {dev} emu geo fix {lng} {lat} {alt}')
    log.info("GPS set: lat=%s lng=%s alt=%s on %s", lat, lng, alt, dev)


def launch_app(pkg: str, activity: str | None) -> None:
    if activity:
        sh(f'adb shell am start -n {pkg}/{activity}')
    else:
        sh(
            f'adb shell monkey -p {pkg} '
            f'-c android.intent.category.LAUNCHER 1'
        )
    log.info("Launched %s", pkg)


def dump_debug(d: u2.Device, tag: str, debug_dir: str) -> None:
    """Save screenshot + UI XML for post-mortem."""
    Path(debug_dir).mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    png = Path(debug_dir) / f"{ts}-{tag}.png"
    xml = Path(debug_dir) / f"{ts}-{tag}.xml"
    try:
        d.screenshot(str(png))
        xml.write_text(d.dump_hierarchy(), encoding="utf-8")
        log.info("Debug artifacts: %s , %s", png, xml)
    except Exception as e:
        log.warning("Could not dump debug: %s", e)


def run_step(d: u2.Device, step: dict, debug_dir: str) -> None:
    action = step["action"]
    note = step.get("note", "")

    if action == "wait":
        time.sleep(step["seconds"])
        return

    if action == "tap_xy":
        d.click(step["x"], step["y"])
        return

    if action == "click":
        timeout = step.get("timeout", 10)
        selector = {k: step[k] for k in ("text", "resourceId", "description")
                    if k in step}
        if not selector:
            raise ValueError(f"click step needs text/resourceId/description: {step}")
        el = d(**selector)
        if not el.wait(timeout=timeout):
            dump_debug(d, f"missing-{list(selector.values())[0]}", debug_dir)
            raise RuntimeError(f"Element not found within {timeout}s: {selector}")
        el.click()
        log.info("Clicked %s %s", selector, f"({note})" if note else "")
        return

    raise ValueError(f"Unknown action: {action}")


def attempt(cfg: dict) -> bool:
    set_gps(cfg["latitude"], cfg["longitude"], cfg["altitude"])
    launch_app(cfg["package"], cfg["activity"])

    d = u2.connect()  # connects to default adb device
    d.wait_activity(".*", timeout=10)

    for i, step in enumerate(cfg["steps"], 1):
        log.info("Step %d/%d: %s", i, len(cfg["steps"]), step)
        try:
            run_step(d, step, cfg["debug_dir"])
        except Exception as e:
            log.error("Step %d failed: %s", i, e)
            dump_debug(d, f"step-{i}-fail", cfg["debug_dir"])
            return False
    return True


def main() -> int:
    for attempt_no in range(1, CONFIG["max_attempts"] + 1):
        log.info("=== Attempt %d/%d ===", attempt_no, CONFIG["max_attempts"])
        try:
            if attempt(CONFIG):
                log.info("Attendance submitted.")
                return 0
        except Exception as e:
            log.error("Attempt failed: %s", e)
        time.sleep(5)
    log.error("All attempts failed. See %s/ for artifacts.", CONFIG["debug_dir"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
