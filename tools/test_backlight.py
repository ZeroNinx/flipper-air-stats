#!/usr/bin/env python3
"""Compile the production backlight controller against a simulated notification service."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

FURI = r'''
#pragma once
#include <stdbool.h>
#include <stdint.h>
#define COUNT_OF(a) (sizeof(a) / sizeof((a)[0]))
uint32_t furi_get_tick(void);
uint32_t furi_ms_to_ticks(uint32_t ms);
'''
NOTIFICATIONS = r'''
#pragma once
#include <stdint.h>
typedef struct {
    uint8_t brightness;
    uint8_t internal_light;
    uint8_t actual_light;
    unsigned locks;
    unsigned calls;
} NotificationApp;
typedef int NotificationSequence;
extern const NotificationSequence sequence_display_backlight_enforce_on;
extern const NotificationSequence sequence_display_backlight_enforce_auto;
extern const NotificationSequence sequence_display_backlight_on;
extern const NotificationSequence sequence_display_backlight_off;
void notification_message_block(NotificationApp*, const NotificationSequence*);
'''
TEST = r'''
#include <assert.h>
#include <stdio.h>
#include "helpers/backlight.h"

const NotificationSequence sequence_display_backlight_enforce_on = 1;
const NotificationSequence sequence_display_backlight_enforce_auto = 2;
const NotificationSequence sequence_display_backlight_on = 3;
const NotificationSequence sequence_display_backlight_off = 4;
static uint32_t tick;
uint32_t furi_get_tick(void) { return tick; }
uint32_t furi_ms_to_ticks(uint32_t ms) { return ms; }

// Model the firmware's scaled internal layer and reference-counted backlight lock.
void notification_message_block(NotificationApp* service, const NotificationSequence* seq) {
    service->calls++;
    switch(*seq) {
    case 1:
        assert(service->locks == 0); // A repeat apply/activity must never take a second lock.
        service->locks++;
        service->internal_light = service->brightness;
        break;
    case 2:
        assert(service->locks == 1); // Never release a lock owned by another app.
        service->locks--;
        service->internal_light = 0;
        break;
    case 3:
        service->actual_light = service->brightness;
        break;
    case 4:
        service->actual_light = service->internal_light;
        break;
    default:
        assert(false);
    }
}

int main(void) {
    NotificationApp service = {.brightness = 51, .actual_light = 255};
    AirStatsBacklight controller;
    air_stats_backlight_init(&controller, &service);
    air_stats_backlight_release(&controller);
    assert(service.calls == 0);

    air_stats_backlight_set_mode(&controller, 7);
    assert(controller.locked && service.locks == 1);
    assert(service.actual_light == 51); // Repair a stale HAL value using system brightness.
    unsigned calls = service.calls;
    for(unsigned second = 0; second < 120; second++) {
        tick += 1000;
        air_stats_backlight_update(&controller);
        // The firmware's normal timeout resets only its notification layer.
        if(second == 30) service.actual_light = service.internal_light;
        assert(service.actual_light == 51);
    }
    assert(service.calls == calls); // No five-second polling writes.
    air_stats_backlight_set_mode(&controller, 7);
    air_stats_backlight_wake(&controller);
    assert(service.calls == calls && service.locks == 1);

    air_stats_backlight_set_mode(&controller, 1);
    assert(!controller.locked && service.locks == 0);
    calls = service.calls;
    tick += 3600000;
    service.actual_light = service.internal_light; // Auto obeys the system timeout.
    air_stats_backlight_wake(&controller);
    air_stats_backlight_update(&controller);
    air_stats_backlight_release(&controller);
    assert(service.actual_light == 0 && service.calls == calls);

    const uint8_t modes[] = {0, 2, 3, 4, 5, 6};
    const uint32_t durations[] = {5000, 60000, 300000, 600000, 1200000, 3600000};
    for(unsigned i = 0; i < COUNT_OF(modes); i++) {
        air_stats_backlight_set_mode(&controller, modes[i]);
        tick += durations[i] - 1;
        air_stats_backlight_update(&controller);
        assert(controller.locked && service.actual_light == 51);
        air_stats_backlight_wake(&controller); // Activity restarts the entire interval.
        tick += durations[i] - 1;
        air_stats_backlight_update(&controller);
        assert(controller.locked);
        tick++;
        air_stats_backlight_update(&controller);
        assert(!controller.locked && service.locks == 0 && service.actual_light == 0);
        calls = service.calls;
        tick += durations[i];
        air_stats_backlight_update(&controller);
        assert(service.calls == calls); // Expiry is handled once.
        air_stats_backlight_wake(&controller);
        assert(controller.locked && service.actual_light == 51);
        air_stats_backlight_release(&controller);
    }

    tick = UINT32_MAX - 2000;
    air_stats_backlight_set_mode(&controller, 0);
    tick += 4999;
    air_stats_backlight_update(&controller);
    assert(controller.locked);
    tick++;
    air_stats_backlight_update(&controller);
    assert(!controller.locked && service.locks == 0);

    air_stats_backlight_set_mode(&controller, 7);
    air_stats_backlight_set_mode(&controller, 255); // Invalid mode falls back to Auto.
    assert(controller.mode == 1 && service.locks == 0);
    air_stats_backlight_release(&controller);
    puts("Backlight: system brightness, Inf, Auto, all timeouts, activity, balanced locks and tick rollover passed");
}
'''

with tempfile.TemporaryDirectory(prefix="air-stats-backlight-") as directory:
    work = Path(directory)
    (work / "notification").mkdir()
    (work / "furi.h").write_text(FURI)
    (work / "notification/notification.h").write_text(NOTIFICATIONS)
    (work / "notification/notification_messages.h").write_text('#include "notification.h"\n')
    (work / "test.c").write_text(TEST)
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(work), "-I", str(ROOT),
         str(ROOT / "helpers/backlight.c"), str(work / "test.c"), "-o", str(work / "test")],
        check=True,
    )
    subprocess.run([str(work / "test")], check=True)
