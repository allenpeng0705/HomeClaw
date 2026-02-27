import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'homeclaw_native_platform_interface.dart';

/// An implementation of [HomeclawNativePlatform] that uses method channels.
class MethodChannelHomeclawNative extends HomeclawNativePlatform {
  /// The method channel used to interact with the native platform.
  @visibleForTesting
  final methodChannel = const MethodChannel('homeclaw_native');

  @override
  Future<String?> getPlatformVersion() async {
    final version = await methodChannel.invokeMethod<String>('getPlatformVersion');
    return version;
  }

  @override
  Future<void> showNotification({
    required String title,
    required String body,
  }) async {
    await methodChannel.invokeMethod<void>('showNotification', {
      'title': title,
      'body': body,
    });
  }

  @override
  Future<String?> startScreenRecord({
    int durationSec = 10,
    bool includeAudio = false,
  }) async {
    final result = await methodChannel.invokeMethod<String?>(
      'startScreenRecord',
      {'durationSec': durationSec, 'includeAudio': includeAudio},
    );
    return result;
  }

  @override
  Future<String?> cameraSnap({String? facing}) async {
    final result = await methodChannel.invokeMethod<String?>(
      'cameraSnap',
      {'facing': facing},
    );
    return result;
  }

  @override
  Future<String?> cameraClip({
    int durationSec = 5,
    bool includeAudio = true,
  }) async {
    final result = await methodChannel.invokeMethod<String?>(
      'cameraClip',
      {'durationSec': durationSec, 'includeAudio': includeAudio},
    );
    return result;
  }

  @override
  Future<Map<String, dynamic>?> systemRun({
    required String command,
    List<String> args = const [],
    int? timeoutSec,
  }) async {
    final result = await methodChannel.invokeMethod<Map<Object?, Object?>>(
      'systemRun',
      {
        'command': command,
        'args': args,
        ...? timeoutSec != null ? {'timeoutSec': timeoutSec} : null,
      },
    );
    final entries = result?.entries;
    if (entries == null) return null;
    return Map<String, dynamic>.fromEntries(
      entries.map((e) => MapEntry(e.key?.toString() ?? '', e.value)),
    );
  }

  @override
  Future<bool> getTraySupported() async {
    final result = await methodChannel.invokeMethod<bool>('getTraySupported');
    return result ?? false;
  }

  @override
  Future<void> setTrayIcon({String? iconPath, String? tooltip}) async {
    final args = <String, dynamic>{
      ...? (iconPath != null ? {'iconPath': iconPath} : null),
      ...? (tooltip != null ? {'tooltip': tooltip} : null),
    };
    await methodChannel.invokeMethod<void>('setTrayIcon', args);
  }

  @override
  Future<String?> getApnsToken() async {
    final result = await methodChannel.invokeMethod<String?>('getApnsToken');
    return result;
  }
}
