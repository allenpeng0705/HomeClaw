import 'package:plugin_platform_interface/plugin_platform_interface.dart';

import 'homeclaw_native_method_channel.dart';

abstract class HomeclawNativePlatform extends PlatformInterface {
  /// Constructs a HomeclawNativePlatform.
  HomeclawNativePlatform() : super(token: _token);

  static final Object _token = Object();

  static HomeclawNativePlatform _instance = MethodChannelHomeclawNative();

  /// The default instance of [HomeclawNativePlatform] to use.
  ///
  /// Defaults to [MethodChannelHomeclawNative].
  static HomeclawNativePlatform get instance => _instance;

  /// Platform-specific implementations should set this with their own
  /// platform-specific class that extends [HomeclawNativePlatform] when
  /// they register themselves.
  static set instance(HomeclawNativePlatform instance) {
    PlatformInterface.verifyToken(instance, _token);
    _instance = instance;
  }

  Future<String?> getPlatformVersion() {
    throw UnimplementedError('platformVersion() has not been implemented.');
  }

  /// Show a local notification. No-op if not implemented.
  Future<void> showNotification({required String title, required String body}) {
    throw UnimplementedError('showNotification() has not been implemented.');
  }

  /// Start screen recording. Returns file path or data URL, or null if unimplemented/failed.
  Future<String?> startScreenRecord({
    int durationSec = 10,
    bool includeAudio = false,
  }) {
    throw UnimplementedError('startScreenRecord() has not been implemented.');
  }

  /// Take a photo. [facing] e.g. "front" or "back". Returns path or data URL, or null.
  Future<String?> cameraSnap({String? facing}) {
    throw UnimplementedError('cameraSnap() has not been implemented.');
  }

  /// Record a short video clip. Returns path or data URL, or null.
  Future<String?> cameraClip({
    int durationSec = 5,
    bool includeAudio = true,
  }) {
    throw UnimplementedError('cameraClip() has not been implemented.');
  }

  /// Run a shell command (desktop/Android with allowlist). Returns null if unimplemented or denied.
  Future<Map<String, dynamic>?> systemRun({
    required String command,
    List<String> args = const [],
    int? timeoutSec,
  }) {
    throw UnimplementedError('systemRun() has not been implemented.');
  }

  /// True if tray/menu bar is supported on this platform.
  Future<bool> getTraySupported() {
    throw UnimplementedError('getTraySupported() has not been implemented.');
  }

  /// Set tray icon (desktop). No-op if not implemented.
  Future<void> setTrayIcon({String? iconPath, String? tooltip}) {
    throw UnimplementedError('setTrayIcon() has not been implemented.');
  }
}
