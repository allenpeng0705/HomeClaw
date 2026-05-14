import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/core_service.dart';
import 'package:home_claw_app/envoy/envoy_node_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Minimal [EnvoyNodeService] stand-in for Core `/ws` tunnel behavior (no real relay).
class FakeEnvoyNodeForCoreWs extends EnvoyNodeService {
  FakeEnvoyNodeForCoreWs()
      : super.withKeys(
          peerId: 'test_peer',
          ownerId: 'test_owner',
          publicKeyPem:
              '-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----',
          privateKeyPem:
              '-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEIBog\n-----END PRIVATE KEY-----',
        );

  final StreamController<String> _wsText = StreamController<String>.broadcast();

  int openCount = 0;
  int closeCount = 0;
  final List<String> sentTexts = [];
  bool openReturnsOk = true;
  bool sendReturnsOk = true;

  @override
  bool get isRelayConnected => true;

  @override
  Stream<String> get onHomeClawCoreWsText => _wsText.stream;

  @override
  Future<Map<String, dynamic>> homeClawCoreWsOpen({
    required String pathWithQuery,
    Duration timeout = const Duration(seconds: 45),
  }) async {
    openCount++;
    expect(pathWithQuery.startsWith('/ws'), true);
    if (openReturnsOk) {
      // Run after the CoreService listener subscribes (post-open).
      Future<void>.delayed(Duration.zero, () {
        if (!_wsText.isClosed) {
          _wsText.add(
            jsonEncode({'event': 'connected', 'session_id': 'test-sid'}),
          );
        }
      });
      return {'ok': true};
    }
    return {'ok': false, 'error': 'test-deny-open'};
  }

  @override
  Future<Map<String, dynamic>> homeClawCoreWsSend({
    required String text,
    Duration timeout = const Duration(seconds: 30),
  }) async {
    sentTexts.add(text);
    if (!sendReturnsOk) {
      return {'ok': false, 'error': 'test-deny-send'};
    }
    return {'ok': true};
  }

  @override
  Future<void> homeClawCoreWsClose() async {
    closeCount++;
  }

  @override
  Future<void> dispose() async {
    await _wsText.close();
    await super.dispose();
  }
}

void main() {
  HttpServer? loopback;
  late int loopbackPort;

  setUpAll(() async {
    loopback = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    loopbackPort = loopback!.port;
    loopback!.listen((HttpRequest req) async {
      if (req.uri.path != '/ws') {
        req.response.statusCode = 404;
        await req.response.close();
        return;
      }
      try {
        if (WebSocketTransformer.isUpgradeRequest(req)) {
          final socket = await WebSocketTransformer.upgrade(req);
          socket.add(jsonEncode({'event': 'connected', 'session_id': 'loopback-sid'}));
          socket.listen((_) {}, onDone: () {}, onError: (_) {});
        } else {
          req.response.statusCode = 400;
          await req.response.close();
        }
      } catch (_) {
        try {
          await req.response.close();
        } catch (_) {}
      }
    });
  });

  tearDownAll(() async {
    await loopback?.close(force: true);
    loopback = null;
  });

  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
    CoreService.testOverrideCoreWsHandshakeTimeout =
        const Duration(seconds: 2);
  });

  tearDown(() {
    CoreService.testOverrideCoreWsHandshakeTimeout = null;
  });

  test('Core /ws uses Envoy tunnel when routing on and relay is connected', () async {
    SharedPreferences.setMockInitialValues({
      'core_base_url': 'http://127.0.0.1:$loopbackPort',
      'core_api_key': 'test-key',
      'core_http_via_envoy': true,
    });

    final fake = FakeEnvoyNodeForCoreWs();
    final core = CoreService();
    await core.loadSettings();
    core.bindEnvoyForCoreHttp(fake);

    await core.testEnsureCoreWsConnectedForCompanion('alice');

    expect(fake.openCount, 1);
    expect(core.testDebugCoreWsUsesCompanionTunnel, true);
    expect(core.testDebugCoreWsSessionId, 'test-sid');

    final hasRegister = fake.sentTexts.any((t) {
      final m = jsonDecode(t);
      return m is Map &&
          m['event'] == 'register' &&
          m['user_id'] == 'alice';
    });
    expect(hasRegister, true);

    await core.testTearDownCoreWebSocketForCompanion();
    await fake.dispose();
  });

  test('Core /ws does not call homeClawCoreWsOpen when Envoy HTTP routing is off', () async {
    SharedPreferences.setMockInitialValues({
      'core_base_url': 'http://127.0.0.1:$loopbackPort',
      'core_api_key': 'k',
      'core_http_via_envoy': false,
    });

    final fake = FakeEnvoyNodeForCoreWs();
    final core = CoreService();
    await core.loadSettings();
    core.bindEnvoyForCoreHttp(fake);

    await core.testEnsureCoreWsConnectedForCompanion();

    expect(fake.openCount, 0);
    expect(core.testDebugCoreWsUsesCompanionTunnel, false);
    expect(core.testDebugCoreWsSessionId, 'loopback-sid');

    await core.testTearDownCoreWebSocketForCompanion();
    await fake.dispose();
  });

  test('Core /ws closes tunnel and falls back when homeClawCoreWsOpen returns ok: false',
      () async {
    SharedPreferences.setMockInitialValues({
      'core_base_url': 'http://127.0.0.1:$loopbackPort',
      'core_api_key': 'k',
      'core_http_via_envoy': true,
    });

    final fake = FakeEnvoyNodeForCoreWs()..openReturnsOk = false;
    final core = CoreService();
    await core.loadSettings();
    core.bindEnvoyForCoreHttp(fake);

    await core.testEnsureCoreWsConnectedForCompanion();

    expect(fake.openCount, 1);
    expect(fake.closeCount >= 1, isTrue);
    expect(core.testDebugCoreWsUsesCompanionTunnel, false);
    expect(core.testDebugCoreWsSessionId, 'loopback-sid');

    await core.testTearDownCoreWebSocketForCompanion();
    await fake.dispose();
  });

  test('homeClawCoreWsSend ok:false tears down companion /ws tunnel', () async {
    SharedPreferences.setMockInitialValues({
      'core_base_url': 'http://127.0.0.1:$loopbackPort',
      'core_api_key': 'k',
      'core_http_via_envoy': true,
    });

    final fake = FakeEnvoyNodeForCoreWs()..sendReturnsOk = false;
    final core = CoreService();
    await core.loadSettings();
    core.bindEnvoyForCoreHttp(fake);

    await core.testEnsureCoreWsConnectedForCompanion('alice');
    await Future<void>.delayed(const Duration(milliseconds: 30));

    expect(core.testDebugCoreWsUsesCompanionTunnel, false);
    expect(core.testDebugCoreWsSessionId, isNull);
    expect(fake.closeCount >= 1, isTrue);

    await core.testTearDownCoreWebSocketForCompanion();
    await fake.dispose();
  });
}
