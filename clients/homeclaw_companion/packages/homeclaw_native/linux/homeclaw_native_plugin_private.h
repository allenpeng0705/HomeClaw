#include <flutter_linux/flutter_linux.h>

#include "include/homeclaw_native/homeclaw_native_plugin.h"

// This file exposes some plugin internals for unit testing. See
// https://github.com/flutter/flutter/issues/88724 for current limitations
// in the unit-testable API.

// Handles the getPlatformVersion method call.
FlMethodResponse *get_platform_version();

// Shows a notification (title, body). Uses notify-send if available.
FlMethodResponse *show_notification(const gchar *title, const gchar *body);

// Screen record for duration_sec seconds using ffmpeg x11grab. Returns path or NULL.
FlMethodResponse *start_screen_record(int duration_sec, gboolean include_audio);
