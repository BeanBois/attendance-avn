# Attendance Taker — Setup & Usage Guide

An automated Android attendance script. It sets your emulator's GPS to a fixed location, launches your attendance app, and taps through the check-in flow.

This guide walks you from zero to a working run.

---

## 1. What you're building

```
 ┌─────────────────────────────┐
 │  Your PC                    │
 │                             │
 │  ┌──────────────────────┐   │
 │  │  Android Emulator    │   │
 │  │   - Fake GPS         │◄──┼── attendance.py (Python + ADB)
 │  │   - Attendance app   │   │
 │  └──────────────────────┘   │
 └─────────────────────────────┘
```

The script talks to the emulator via `adb` (Android Debug Bridge) and `uiautomator2` (a Python library that clicks real UI elements, not just xy coordinates).

---

## 2. One-time setup

### 2.1 Install Android Studio

1. Download from <https://developer.android.com/studio>.
2. Install with default options.
3. On first launch, let it download the SDK.

### 2.2 Add `adb` to your PATH

`adb` lives at:

```
C:\Users\<YOU>\AppData\Local\Android\Sdk\platform-tools
```

Add that folder to Windows **PATH**:

1. Start menu → "Edit the system environment variables".
2. Environment Variables → select `Path` → Edit → New → paste the path above.
3. Open a **new** terminal. Verify:

```bash
adb version
```

You should see a version string.

### 2.3 Create an emulator (AVD)

1. In Android Studio: **More Actions → Virtual Device Manager → Create Device**.
2. Pick **Pixel 6** (or any phone).
3. Pick a system image: **API 33 (Tiramisu)** with the **Google Play** icon next to it. The Play-image is critical — plain AOSP images don't have Play Services, and most attendance apps need them.
4. Name it something like `attendance-avd`. Finish.
5. Click the ▶ play button to boot it.

### 2.4 Install Python dependencies

```bash
pip install uiautomator2
python -m uiautomator2 init
```

The `init` command installs a helper APK onto the running emulator. Run this **after** the emulator is booted.

### 2.5 Install and log into the attendance app

1. Open Play Store inside the emulator → sign in with a Google account → install your attendance app. (Or drag an `.apk` file onto the emulator window to sideload.)
2. **Log in manually once.** This saves your session.
3. Take a snapshot so the login survives reboots: emulator sidebar **⋮ (More) → Snapshots → Take snapshot**. Name it `logged-in`.

---

## 3. Configure `attendance.py`

Open `attendance.py` and find the `CONFIG` block near the top.

### 3.1 Set your GPS target

```python
"latitude":  40.7580,
"longitude": -73.9855,
"altitude":  10.0,
```

Get coordinates from Google Maps: right-click the spot → first line is `lat, lng`.

### 3.2 Find the app's package name

With the app open on the emulator, run:

```bash
adb shell pm list packages | grep -i <part_of_app_name>
```

Example output: `package:com.acme.attendance`. Strip the `package:` prefix and paste:

```python
"package": "com.acme.attendance",
```

### 3.3 Find button text / IDs for each step

This is the part that's specific to your app. Open the app to the screen where you'd tap "Check In", then run:

```bash
adb shell uiautomator dump /sdcard/ui.xml
adb pull /sdcard/ui.xml
```

Open `ui.xml` in any text editor and search for the button label. You'll see something like:

```xml
<node text="Check In" resource-id="com.acme.attendance:id/btn_checkin" ... />
```

Use whichever is most stable:

- `text="Check In"` → fine if the label never changes.
- `resource-id="com.acme.attendance:id/btn_checkin"` → more robust; preferred.

Translate into a step:

```python
{"action": "click", "text": "Check In", "timeout": 15},
# or:
{"action": "click", "resourceId": "com.acme.attendance:id/btn_checkin", "timeout": 15},
```

Repeat for every tap in the flow. Add `wait` steps between taps if the app needs time to transition:

```python
"steps": [
    {"action": "wait",  "seconds": 4, "note": "app cold-start"},
    {"action": "click", "resourceId": "com.acme.attendance:id/btn_checkin"},
    {"action": "wait",  "seconds": 2},
    {"action": "click", "text": "Confirm"},
    {"action": "wait",  "seconds": 3, "note": "submission round-trip"},
],
```

### 3.4 (Fallback) Raw coordinates

If `uiautomator` can't see an element (happens with custom-rendered canvases, WebViews, etc.):

1. On the emulator, enable **Developer options → Pointer location**. A bar at the top shows X/Y as you tap.
2. Read off coordinates, then:

```python
{"action": "tap_xy", "x": 540, "y": 1600},
```

Coordinate taps break when the UI shifts, so use them only as a last resort.

---

## 4. Running it

With emulator booted and logged in:

```bash
python attendance.py
```

You should see logs like:

```
2026-04-28 09:00:01 INFO GPS set: lat=40.758 lng=-73.9855 alt=10.0 on emulator-5554
2026-04-28 09:00:02 INFO Launched com.acme.attendance
2026-04-28 09:00:06 INFO Step 1/5: {'action': 'wait', ...}
2026-04-28 09:00:10 INFO Clicked {'text': 'Check In'}
...
2026-04-28 09:00:18 INFO Attendance submitted.
```

---

## 5. Scheduling it daily

Use **Windows Task Scheduler**:

1. Start menu → "Task Scheduler" → Create Basic Task.
2. Trigger: Daily at your desired time.
3. Action: Start a program.
   - Program: `python`
   - Arguments: `C:\Users\User\Desktop\Work\work0\attendance_taker\attendance.py`
4. Before the task runs, the emulator must already be booted. Either:
   - Leave the emulator running 24/7 (easiest), or
   - Add a second scheduled task 2 minutes earlier that runs:
     ```
     "C:\Users\<YOU>\AppData\Local\Android\Sdk\emulator\emulator.exe" -avd attendance-avd -no-snapshot-save
     ```

---

## 6. Debugging a failed run

When a step fails, the script drops artifacts in `debug/`:

- `YYYYMMDD-HHMMSS-step-N-fail.png` — screenshot at the moment of failure.
- `YYYYMMDD-HHMMSS-step-N-fail.xml` — full UI hierarchy.

Workflow:

1. Open the screenshot. What does the screen actually look like? Popup? Login expired? New UI?
2. Open the XML. Search for the button you expected. Did its `text` or `resource-id` change?
3. Update that step in `CONFIG["steps"]` and re-run.

### Common failures

| Symptom                                         | Likely cause                              | Fix                                                                 |
| ----------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------------- |
| `No emulator detected`                          | AVD not running                           | Boot the emulator first; verify `adb devices`                       |
| `Element not found within 15s`                  | Button label/id changed, or screen differs | Redump `ui.xml`, update the step selector                           |
| App shows "Device not supported" on launch      | Play Integrity flags the emulator         | Try Genymotion, or accept that this app blocks emulators            |
| Logged out on run                               | Session expired / snapshot not taken      | Log in again, take a fresh AVD snapshot                             |
| GPS set but app still shows real location       | App uses Wi-Fi/cell geolocation too       | Turn off Wi-Fi in emulator settings, force GPS-only location mode   |
| Random popup (rating prompt, update nag)        | Covers your target button                 | Add a conditional dismiss step before the main click                |

---

## 7. File layout

```
attendance_taker/
├── attendance.py       # the script
├── README.md           # this file
└── debug/              # auto-created; screenshots + XML on failure
    ├── 20260428-...png
    └── 20260428-...xml
```

---

## 8. Honest limits

- **Play Integrity / SafetyNet**: apps that enforce these will refuse to run on any emulator. No amount of scripting fixes that from userspace.
- **CAPTCHAs, biometrics, SMS codes**: these are deliberate anti-automation gates. The script can't solve them.
- **UI drift**: every app update can rename buttons or reshuffle the layout. Expect to re-run step 3.3 occasionally.
- **Network geolocation**: `adb emu geo fix` only sets GPS. If the app also checks Wi-Fi SSID or IP geolocation, you need to disable those signals on the emulator.

Treat the script as a scaffold you'll tweak, not a sealed appliance.

---

## 9. Quick reference

```bash
# List connected devices
adb devices

# Set GPS (longitude first, then latitude)
adb emu geo fix -73.9855 40.7580

# Launch an app by package
adb shell monkey -p com.acme.attendance -c android.intent.category.LAUNCHER 1

# Dump current UI
adb shell uiautomator dump /sdcard/ui.xml && adb pull /sdcard/ui.xml

# Raw tap
adb shell input tap 540 1200

# Screenshot
adb exec-out screencap -p > screen.png

# Run the script
python attendance.py
```
#   a t t e n d a n c e - a v n  
 