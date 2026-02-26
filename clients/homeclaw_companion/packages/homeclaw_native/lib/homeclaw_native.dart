import 'package:flutter/services.dart';

import 'homeclaw_native_platform_interface.dart';

/// Native capabilities for HomeClaw companion (notifications, screen record, camera, etc.).
/// For voice input use the [homeclaw_voice] package.
/// Methods may return null or false when a feature is not implemented on the current platform.
class HomeclawNative {
  final HomeclawNativePlatform _platform = HomeclawNativePlatform.instance;

  Future<String?> getPlatformVersion() => _platform.getPlatformVersion();

  /// Show a local notification. Ignores [PlatformException] if not implemented.
  Future<void> showNotification({
    required String title,
    required String body,
  }) async {
    try {
      await _platform.showNotification(title: title, body: body);
    } on PlatformException {
      // Not implemented on this platform
    }
  }

  /// Start screen recording. Returns file path or data URL, or null if unimplemented/failed.
  Future<String?> startScreenRecord({
    int durationSec = 10,
    bool includeAudio = false,
  }) async {
    try {
      return await _platform.startScreenRecord(
        durationSec: durationSec,
        includeAudio: includeAudio,
      );
    } on PlatformException {
      return null;
    }
  }

  /// Take a photo. [facing] e.g. "front" or "back". Returns path or data URL, or null.
  Future<String?> cameraSnap({String? facing}) async {
    try {
      return await _platform.cameraSnap(facing: facing);
    } on PlatformException {
      return null;
    }
  }

  /// Record a short video clip. Returns path or data URL, or null.
  Future<String?> cameraClip({
    int durationSec = 5,
    bool includeAudio = true,
  }) async {
    try {
      return await _platform.cameraClip(
        durationSec: durationSec,
        includeAudio: includeAudio,
      );
    } on PlatformException {
      return null;
    }
  }

  /// Run a shell command (desktop/Android with allowlist). Returns null if unimplemented or denied.
  /// Map keys: stdout, stderr, exitCode.
  Future<Map<String, dynamic>?> systemRun({
    required String command,
    List<String> args = const [],
    int? timeoutSec,
  }) async {
    try {
      return await _platform.systemRun(
        command: command,
        args: args,
        timeoutSec: timeoutSec,
      );
    } on PlatformException {
      return null;
    }
  }

  /// True if tray/menu bar is supported on this platform.
  Future<bool> getTraySupported() async {
    try {
      return await _platform.getTraySupported();
    } on PlatformException {
      return false;
    }
  }

  /// Set tray icon (desktop). No-op if not implemented.
  Future<void> setTrayIcon({String? iconPath, String? tooltip}) async {
    try {
      await _platform.setTrayIcon(iconPath: iconPath, tooltip: tooltip);
    } on PlatformException {
      // Not implemented
    }
  }

  /// Get APNs device token (iOS/macOS only, no Firebase). Returns null if not supported or permission denied.
  Future<String?> getApnsToken() async {
    try {
      return await _platform.getApnsToken();
    } on PlatformException {
      return null;
    }
  }
}
