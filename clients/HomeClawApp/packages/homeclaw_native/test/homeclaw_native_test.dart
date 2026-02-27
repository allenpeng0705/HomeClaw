import 'package:flutter_test/flutter_test.dart';
import 'package:homeclaw_native/homeclaw_native.dart';
import 'package:homeclaw_native/homeclaw_native_platform_interface.dart';
import 'package:homeclaw_native/homeclaw_native_method_channel.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';

class MockHomeclawNativePlatform
    with MockPlatformInterfaceMixin
    implements HomeclawNativePlatform {
  @override
  Future<String?> getPlatformVersion() => Future.value('42');

  @override
  Future<void> showNotification({required String title, required String body}) =>
      Future.value();

  @override
  Future<String?> startScreenRecord(
          {int durationSec = 10, bool includeAudio = false}) =>
      Future.value(null);

  @override
  Future<String?> cameraSnap({String? facing}) => Future.value(null);

  @override
  Future<String?> cameraClip(
          {int durationSec = 5, bool includeAudio = true}) =>
      Future.value(null);

  @override
  Future<Map<String, dynamic>?> systemRun(
          {required String command,
          List<String> args = const [],
          int? timeoutSec}) =>
      Future.value(null);

  @override
  Future<bool> getTraySupported() => Future.value(false);

  @override
  Future<void> setTrayIcon({String? iconPath, String? tooltip}) => Future.value();
}

void main() {
  final HomeclawNativePlatform initialPlatform = HomeclawNativePlatform.instance;

  test('$MethodChannelHomeclawNative is the default instance', () {
    expect(initialPlatform, isInstanceOf<MethodChannelHomeclawNative>());
  });

  test('getPlatformVersion', () async {
    HomeclawNative homeclawNativePlugin = HomeclawNative();
    MockHomeclawNativePlatform fakePlatform = MockHomeclawNativePlatform();
    HomeclawNativePlatform.instance = fakePlatform;

    expect(await homeclawNativePlugin.getPlatformVersion(), '42');
  });
}
