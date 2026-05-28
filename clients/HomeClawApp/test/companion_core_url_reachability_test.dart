import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/core_service.dart';

void main() {
  group('CoreService.heuristicCompanionCoreUrlGloballyReachable', () {
    test('false for LAN / special IPv4', () {
      expect(
        CoreService.heuristicCompanionCoreUrlGloballyReachable(
          'http://192.168.0.1:9000',
        ),
        false,
      );
      expect(
        CoreService.heuristicCompanionCoreUrlGloballyReachable(
          'http://10.0.0.2:9000',
        ),
        false,
      );
      expect(
        CoreService.heuristicCompanionCoreUrlGloballyReachable(
          'http://172.31.255.254:9000',
        ),
        false,
      );
      expect(
        CoreService.heuristicCompanionCoreUrlGloballyReachable(
          'http://127.0.0.1:9000/',
        ),
        false,
      );
    });

    test('false for localhost, .local, single-label hosts', () {
      expect(
        CoreService.heuristicCompanionCoreUrlGloballyReachable(
          'https://localhost:9000/',
        ),
        false,
      );
      expect(
        CoreService.heuristicCompanionCoreUrlGloballyReachable(
          'http://nas.local:9000',
        ),
        false,
      );
      expect(
        CoreService.heuristicCompanionCoreUrlGloballyReachable(
          'http://homeserver:9000',
        ),
        false,
      );
    });

    test('true for typical public DNS hostname', () {
      expect(
        CoreService.heuristicCompanionCoreUrlGloballyReachable(
          'https://core.example.com:443/',
        ),
        true,
      );
      expect(
        CoreService.heuristicCompanionCoreUrlGloballyReachable(
          'http://abc123.ngrok-free.app/',
        ),
        true,
      );
    });

    test('false for ambiguous / invalid URLs', () {
      expect(CoreService.heuristicCompanionCoreUrlGloballyReachable(''), false);
      expect(
        CoreService.heuristicCompanionCoreUrlGloballyReachable(
          'not-a-uri',
        ),
        false,
      );
    });

    test('true for non-private IPv4', () {
      expect(
        CoreService.heuristicCompanionCoreUrlGloballyReachable(
          'http://8.8.8.8:9000',
        ),
        true,
      );
    });
  });
}
