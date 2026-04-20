import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/models/permission_item.dart';

void main() {
  group('PermissionItem', () {
    test('creates valid instance', () {
      final item = PermissionItem(
        permission: 'camera',
        friendlyName: 'Camera',
        description: 'Take photos and record video',
        isGranted: true,
      );
      expect(item.permission, 'camera');
      expect(item.friendlyName, 'Camera');
      expect(item.description, 'Take photos and record video');
      expect(item.isGranted, true);
    });

    test('isGranted defaults to false', () {
      final item = PermissionItem(
        permission: 'microphone',
        friendlyName: 'Microphone',
        description: 'Record audio',
      );
      expect(item.isGranted, false);
    });

    test('grantedBy can be set', () {
      final item = PermissionItem(
        permission: 'location',
        friendlyName: 'Location',
        description: 'Access location',
        isGranted: true,
        grantedBy: 'user',
      );
      expect(item.grantedBy, 'user');
    });
  });
}
