#pragma once

#include <furi.h>
#include <notification/notification.h>

typedef struct {
    NotificationApp* notifications;
    uint32_t last_activity_tick;
    uint8_t mode;
    bool locked;
} AirStatsBacklight;

void air_stats_backlight_init(AirStatsBacklight* backlight, NotificationApp* notifications);
void air_stats_backlight_set_mode(AirStatsBacklight* backlight, uint8_t mode);
void air_stats_backlight_wake(AirStatsBacklight* backlight);
void air_stats_backlight_update(AirStatsBacklight* backlight);
void air_stats_backlight_release(AirStatsBacklight* backlight);
