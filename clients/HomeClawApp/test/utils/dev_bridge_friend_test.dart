import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/utils/dev_bridge_friend.dart';

void main() {
  group('devBridgeBackend', () {
    test('null preset + claudecode id → claude', () {
      expect(devBridgeBackend(friendPreset: null, friendId: 'claudecode'), 'claude');
    });

    test('null preset + cursor id → cursor', () {
      expect(devBridgeBackend(friendPreset: null, friendId: 'cursor'), 'cursor');
    });

    test('null preset + trae id → trae', () {
      expect(devBridgeBackend(friendPreset: '', friendId: 'trae'), 'trae');
    });

    test('preset takes precedence over legacy friend id', () {
      expect(devBridgeBackend(friendPreset: 'claude', friendId: 'cursor'), 'claude');
    });

    test('non-bridge friend returns null', () {
      expect(devBridgeBackend(friendPreset: null, friendId: 'Gary'), isNull);
    });
  });

  group('isDevBridgeFriend', () {
    test('false for user friend', () {
      expect(
        isDevBridgeFriend(
          isUserFriend: true,
          friendPreset: 'cursor',
          friendId: 'x',
        ),
        false,
      );
    });

    test('true for legacy claudecode id', () {
      expect(
        isDevBridgeFriend(
          isUserFriend: false,
          friendPreset: null,
          friendId: 'claudecode',
        ),
        true,
      );
    });
  });

  group('isTraeDisabledInCompanion', () {
    test('legacy trae id', () {
      expect(
        isTraeDisabledInCompanion(
          isUserFriend: false,
          friendPreset: null,
          friendId: 'trae',
        ),
        true,
      );
    });

    test('preset trae', () {
      expect(
        isTraeDisabledInCompanion(
          isUserFriend: false,
          friendPreset: 'trae',
          friendId: 'my-trae',
        ),
        true,
      );
    });

    test('false for cursor', () {
      expect(
        isTraeDisabledInCompanion(
          isUserFriend: false,
          friendPreset: 'cursor',
          friendId: 'cursor',
        ),
        false,
      );
    });

    test('false for user friend even if id looks like trae', () {
      expect(
        isTraeDisabledInCompanion(
          isUserFriend: true,
          friendPreset: null,
          friendId: 'trae',
        ),
        false,
      );
    });
  });
}
