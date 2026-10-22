#include "backlight.h"
#include <notification/notification_messages.h>

// Keep the persisted mode indices: 5s, Auto, 1m, 5m, 10m, 20m, 60m, Inf.
static const uint32_t timeout_ms[] = {5000, 0, 60000, 300000, 600000, 1200000, 3600000, 0};

void air_stats_backlight_init(AirStatsBacklight* backlight, NotificationApp* notifications) {
    *backlight = (AirStatsBacklight){.notifications = notifications, .mode = 1};
}

void air_stats_backlight_release(AirStatsBacklight* backlight) {
    if(backlight->locked) {
        notification_message_block(
            backlight->notifications, &sequence_display_backlight_enforce_auto);
        backlight->locked = false;
    }
}

void air_stats_backlight_wake(AirStatsBacklight* backlight) {
    if(backlight->mode == 1) return;

    backlight->last_activity_tick = furi_get_tick();
    if(!backlight->locked) {
        // The notification service applies the system's configured brightness.
        notification_message_block(
            backlight->notifications, &sequence_display_backlight_enforce_on);
        // Clear any old notification layer/timer; the locked internal layer stays lit.
        notification_message_block(
            backlight->notifications, &sequence_display_backlight_off);
        backlight->locked = true;
    }
}

void air_stats_backlight_set_mode(AirStatsBacklight* backlight, uint8_t mode) {
    backlight->mode = mode < COUNT_OF(timeout_ms) ? mode : 1;
    if(backlight->mode == 1) {
        air_stats_backlight_release(backlight);
        notification_message_block(backlight->notifications, &sequence_display_backlight_on);
    } else {
        air_stats_backlight_wake(backlight);
    }
}

void air_stats_backlight_update(AirStatsBacklight* backlight) {
    uint32_t timeout = timeout_ms[backlight->mode];
    if(backlight->locked && timeout &&
       (uint32_t)(furi_get_tick() - backlight->last_activity_tick) >= furi_ms_to_ticks(timeout)) {
        air_stats_backlight_release(backlight);
        notification_message_block(backlight->notifications, &sequence_display_backlight_off);
    }
}
