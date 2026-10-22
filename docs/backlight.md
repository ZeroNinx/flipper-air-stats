# Backlight behavior

Air Stats controls how long the display stays lit. Brightness is set in the
Flipper's system settings; the app does not write a brightness value to the HAL
or override the notification service's brightness setting.

| Mode | Behavior |
|------|----------|
| Auto | Use the firmware's backlight timeout and brightness |
| 5s | Turn off after five seconds without app input |
| 1m / 5m / 10m / 20m / 60m | Turn off after the selected inactivity interval |
| Inf | Keep lit at system brightness until the mode changes or the app exits |

Button activity on all app screens, including menus and sensor editors, restarts
the selected inactivity interval. Mode indices in `settings.cfg` are preserved:
5s = 0, Auto = 1, timed minute modes = 2–6, Inf = 7. Previously, index 0 behaved
like an off override; it now implements the five-second timeout shown in the UI.

## Cause of the old behavior

The old tick handler called `furi_hal_light_set(LightBacklight, 0xFF)` every five
seconds in Inf and active timed modes. This bypassed system brightness, so a
dimmed display could jump to maximum brightness repeatedly. The same code wrote
the light value without acquiring the notification service's always-on lock.
The system timeout could therefore turn it off until the next five-second write.

Calling `sequence_display_backlight_enforce_auto` unconditionally on mode changes
or exit was also unbalanced: this message releases a reference-counted lock and
must only be sent when the app actually owns one.

## Current implementation

`helpers/backlight.c` acquires the firmware's always-on lock once for Inf and for
each active timed interval. The notification service scales the light value by
the system brightness. Clearing its transient notification layer after acquiring
the lock also removes a stale light value or timer from the previous session;
the locked internal layer stays lit.

Input events are routed to the app's dispatcher thread before changing lock or
timeout state. The sensor editor handles only its own custom event, allowing the
backlight event to reach the dispatcher without rebuilding the editor.

At a timed expiry the controller releases its own lock and requests backlight
off once. Later ticks do not resend display commands. Auto and app exit release
only a lock owned by this controller. Elapsed-time subtraction handles the
32-bit tick counter wrapping.

## Validation

Run `python3 tools/test_backlight.py` with a host C compiler. It compiles the
production controller against a simulated notification service and checks:

- 20% system brightness is preserved, including replacing a stale raw value of 255.
- Inf survives a simulated system timeout without periodic writes.
- Reapplying Inf and repeated activity do not acquire extra locks.
- Auto returns to the firmware timeout, with no unmatched unlock on cleanup.
- Every timed mode expires once at its boundary, and activity resets the interval.
- A timed mode can wake again after expiry; invalid modes fall back to Auto.
- Timeouts remain correct across tick-counter rollover.

For a physical check, set system brightness below maximum and the system timeout
to an interval shorter than the observation window. Run Air Stats in Inf, leave
it idle beyond that interval, and confirm it remains lit without a brightness
jump. Then exercise Auto and 5s, reset a timer from a menu, and exit to confirm
that the firmware regains normal backlight control. A USB framebuffer screenshot
shows display content, not physical backlight intensity; it cannot by itself
verify brightness or whether the light is on.

Build and host checks on October 22, 2026 passed for Momentum API 79.2 and 87.1,
and official firmware API 88.2. The API 87.1 build was uploaded to the connected
Flipper and its checksum verified. Device checks exercised the 5s setting and
confirmed that Auto and Inf could each be selected and saved; the original Inf
setting was restored afterward.
During a subsequent 40-second Inf error-log observation, no notification-service
lock errors were reported. Physical brightness still requires visual inspection.

The firmware behavior used here is documented in the
[Momentum CN v1.1.6 notification service](https://github.com/kalicyh/Momentum-Firmware-CN/blob/v1.1.6/applications/services/notification/notification_app.c):
`LedDisplayBacklightEnforceOn` applies system brightness to the internal layer,
`LedDisplayBacklightEnforceAuto` releases the reference-counted lock, and the
normal display timeout clears only the transient notification layer.
