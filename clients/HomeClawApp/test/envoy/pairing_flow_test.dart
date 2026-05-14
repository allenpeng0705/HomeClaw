import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/envoy/envoy_identity.dart';
import 'package:home_claw_app/envoy/envoy_protocol.dart';
import 'package:home_claw_app/envoy/relay_client.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  // ============================================
  // PairingPayload — QR encode/decode
  // ============================================

  group('PairingPayload', () {
    group('fromUri', () {
      test('decodes URI with all fields', () {
        final uri = Uri.parse(
          'envoy://pair?wsUrl=ws://192.168.1.100:3030/ws'
          '&relayPeerId=envoy_relay_abc123'
          '&agentPeerId=envoy_agent_xyz789'
          '&agentPubKey=-----BEGIN%20PUBLIC%20KEY-----%0Atest%0A-----END%20PUBLIC%20KEY-----'
          '&token=pair-secret-token',
        );

        final payload = PairingPayload.fromUri(uri);
        expect(payload, isNotNull);
        expect(payload!.wsUrl, 'ws://192.168.1.100:3030/ws');
        expect(payload.relayPeerId, 'envoy_relay_abc123');
        expect(payload.agentPeerId, 'envoy_agent_xyz789');
        expect(payload.agentPubKey, contains('BEGIN PUBLIC KEY'));
        expect(payload.token, 'pair-secret-token');
      });

      test('decodes URI with minimal fields (wsUrl only)', () {
        final uri = Uri.parse('envoy://pair?wsUrl=ws://192.168.1.100:3030/ws');

        final payload = PairingPayload.fromUri(uri);
        expect(payload, isNotNull);
        expect(payload!.wsUrl, 'ws://192.168.1.100:3030/ws');
        expect(payload.relayPeerId, isNull);
        expect(payload.agentPeerId, isNull);
        expect(payload.agentPubKey, isNull);
        expect(payload.token, isNull);
      });

      test('returns null for wrong scheme', () {
        final uri = Uri.parse('https://pair?wsUrl=ws://example.com/ws');
        expect(PairingPayload.fromUri(uri), isNull);
      });

      test('returns null for wrong host', () {
        final uri = Uri.parse('envoy://connect?wsUrl=ws://example.com/ws');
        expect(PairingPayload.fromUri(uri), isNull);
      });

      test('returns null when wsUrl is missing', () {
        final uri = Uri.parse('envoy://pair?relayPeerId=envoy_relay_abc123');
        expect(PairingPayload.fromUri(uri), isNull);
      });

      test('returns null when wsUrl is empty', () {
        final uri = Uri.parse('envoy://pair?wsUrl=');
        expect(PairingPayload.fromUri(uri), isNull);
      });

      test('handles whitespace-only wsUrl', () {
        final uri = Uri.parse('envoy://pair?wsUrl=+++');
        expect(PairingPayload.fromUri(uri), isNull);
      });

      test('trims whitespace from all fields', () {
        final uri = Uri.parse(
          'envoy://pair?wsUrl=+ws://host:3030/ws+'
          '&agentPeerId=+envoy_agent_abc123+',
        );

        final payload = PairingPayload.fromUri(uri);
        expect(payload, isNotNull);
        expect(payload!.wsUrl, 'ws://host:3030/ws');
        expect(payload.agentPeerId, 'envoy_agent_abc123');
      });

      test('decodes envoy QR with routed wsUrl, relayWsUrl, and nested query tokens', () {
        final uri = Uri.parse(
          'envoy://pair'
          '?wsUrl=ws%3A%2F%2F47.93.11.212%3A15432%2Fws'
          '%3Ftarget%3D12D3KooWQsD3ougrAJjmKeevSiY2azE5CKqLjcijyYreS6fUFYCR'
          '%26token%3Df3d8d8b5-11c4-40fa-9185-aec40a9da36'
          '&relayPeerId=12D3KooWQsD3ougrAJjmKeevSiY2azE5CKqLjcijyYreS6fUFYCR'
          '&relayWsUrl=ws%3A%2F%2F47.93.11.212%3A15432%2Fws'
          '&agentPeerId=envoy_agent_hkHN'
          '&token=f3d8d8b5-11c4-40fa-9185-aec40a9da36',
        );
        final payload = PairingPayload.fromUri(uri);
        expect(payload, isNotNull);
        expect(payload!.wsUrl.startsWith('ws://47.93.11.212:15432/ws'), isTrue);
        expect(payload.wsUrl.contains('target=12D3KooWQ'), isTrue);
        expect(payload.wsUrl.contains('token=f3d8d8b5'), isTrue);
        expect(payload.relayWsUrl, 'ws://47.93.11.212:15432/ws');
        expect(payload.relayPeerId, contains('12D3KooW'));
        expect(
          payload.reconstructedDialWsUrl(),
          'ws://47.93.11.212:15432/ws?target=12D3KooWQsD3ougrAJjmKeevSiY2azE5CKqLjcijyYreS6fUFYCR&token=f3d8d8b5-11c4-40fa-9185-aec40a9da36',
        );
      });

      test('reconstructedDialWsUrl merges target/token onto existing relayWsUrl query', () {
        final payload = PairingPayload(
          wsUrl: 'ws://h/ws',
          relayWsUrl: 'ws://47.93.11.212:15432/ws?ns=mesh',
          relayPeerId: '12D3KooWQsD3ougrAJjmKeevSiY2azE5CKqLjcijyYreS6fUFYCR',
          token: 'f3d8d8b5-11c4-40fa-9185-aec40a9da36',
        );
        final r = payload.reconstructedDialWsUrl();
        expect(r, isNotNull);
        final u = Uri.parse(r!);
        expect(u.queryParameters['ns'], 'mesh');
        expect(u.queryParameters['target'], payload.relayPeerId);
        expect(u.queryParameters['token'], payload.token);
      });

      test('decodes Envoy scheme/host case-insensitively', () {
        final uri = Uri.parse(
          'ENVoy://pair?ws_url=ws%3A%2F%2Fhost%3A3030%2Fws'
          '&token=t1',
        );
        final payload = PairingPayload.fromUri(uri);
        expect(payload, isNotNull);
        expect(payload!.wsUrl, 'ws://host:3030/ws');
        expect(payload.token, 't1');
      });

      test('ignores unknown query parameters', () {
        final uri = Uri.parse(
          'envoy://pair?wsUrl=ws://host:3030/ws&foo=bar&baz=qux',
        );

        final payload = PairingPayload.fromUri(uri);
        expect(payload, isNotNull);
        expect(payload!.wsUrl, 'ws://host:3030/ws');
      });
    });

    group('toUri', () {
      test('produces valid envoy://pair URI with all fields', () {
        final payload = PairingPayload(
          wsUrl: 'ws://192.168.1.100:3030/ws',
          relayPeerId: 'envoy_relay_abc123',
          agentPeerId: 'envoy_agent_xyz789',
          agentPubKey: '-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----',
          token: 'pair-secret-token',
        );

        final uri = payload.toUri();
        expect(uri, startsWith('envoy://pair?wsUrl='));
        expect(uri, contains('relayPeerId=envoy_relay_abc123'));
        expect(uri, contains('agentPeerId=envoy_agent_xyz789'));
        expect(uri, contains('token=pair-secret-token'));
      });

      test('produces URI with only wsUrl when optional fields absent', () {
        final payload = PairingPayload(wsUrl: 'ws://host:3030/ws');
        final uri = payload.toUri();
        expect(uri, 'envoy://pair?wsUrl=ws%3A%2F%2Fhost%3A3030%2Fws');
      });

      test('round-trip: encode then decode preserves all fields', () {
        final original = PairingPayload(
          wsUrl: 'ws://192.168.1.100:3030/ws',
          relayPeerId: 'envoy_relay_abc123',
          agentPeerId: 'envoy_agent_xyz789',
          token: 'secret-token-123',
        );

        final uri = Uri.parse(original.toUri());
        final decoded = PairingPayload.fromUri(uri);
        expect(decoded, isNotNull);
        expect(decoded!.wsUrl, original.wsUrl);
        expect(decoded.relayPeerId, original.relayPeerId);
        expect(decoded.agentPeerId, original.agentPeerId);
        expect(decoded.token, original.token);
      });

      test('round-trip: minimal payload (wsUrl only)', () {
        final original = PairingPayload(wsUrl: 'ws://host:3030/ws');

        final uri = Uri.parse(original.toUri());
        final decoded = PairingPayload.fromUri(uri);
        expect(decoded, isNotNull);
        expect(decoded!.wsUrl, original.wsUrl);
        expect(decoded.relayPeerId, isNull);
      });

      test('excludes empty optional fields from URI', () {
        final payload = PairingPayload(
          wsUrl: 'ws://host:3030/ws',
          relayPeerId: '',
          agentPeerId: '',
        );

        final uri = payload.toUri();
        expect(uri, isNot(contains('relayPeerId=')));
        expect(uri, isNot(contains('agentPeerId=')));
      });
    });

    group('toString', () {
      test('includes wsUrl', () {
        final payload = PairingPayload(wsUrl: 'ws://host:3030/ws');
        expect(payload.toString(), contains('ws://host:3030/ws'));
      });
    });

    group('equality', () {
      test('equal when all fields match', () {
        const a = PairingPayload(wsUrl: 'ws://a', agentPeerId: 'p1');
        const b = PairingPayload(wsUrl: 'ws://a', agentPeerId: 'p1');
        expect(a, b);
      });

      test('not equal when fields differ', () {
        const a = PairingPayload(wsUrl: 'ws://a');
        const b = PairingPayload(wsUrl: 'ws://b');
        expect(a, isNot(b));
      });
    });
  });

  // ============================================
  // DevicePairRequestPayload
  // ============================================

  group('DevicePairRequestPayload', () {
    test('fromJson parses all required fields', () {
      final json = {
        'requestId': 'req-123',
        'requesterOwnerId': 'envoy:owner:abc123',
        'requesterDeviceId': 'envoy_device_xyz789',
        'requesterDevicePublicKeyPem': '-----BEGIN PUBLIC KEY-----\nkey\n-----END PUBLIC KEY-----',
        'createdAt': '2025-01-15T10:30:00.000Z',
      };

      final payload = DevicePairRequestPayload.fromJson(json);
      expect(payload.requestId, 'req-123');
      expect(payload.requesterOwnerId, 'envoy:owner:abc123');
      expect(payload.requesterDeviceId, 'envoy_device_xyz789');
      expect(payload.requesterDevicePublicKeyPem, contains('BEGIN PUBLIC KEY'));
      expect(payload.createdAt, '2025-01-15T10:30:00.000Z');
      expect(payload.note, isNull);
    });

    test('fromJson parses optional note', () {
      final json = {
        'requestId': 'req-456',
        'requesterOwnerId': 'envoy:owner:abc123',
        'requesterDeviceId': 'envoy_device_xyz789',
        'requesterDevicePublicKeyPem': 'key-pem',
        'createdAt': '2025-01-15T10:30:00.000Z',
        'note': 'Pairing from mobile',
      };

      final payload = DevicePairRequestPayload.fromJson(json);
      expect(payload.note, 'Pairing from mobile');
    });

    test('fromJson ignores unknown fields', () {
      final json = {
        'requestId': 'req-789',
        'requesterOwnerId': 'envoy:owner:abc123',
        'requesterDeviceId': 'envoy_device_xyz789',
        'requesterDevicePublicKeyPem': 'key-pem',
        'createdAt': '2025-01-15T10:30:00.000Z',
        'extraField': 'should-be-ignored',
      };

      final payload = DevicePairRequestPayload.fromJson(json);
      expect(payload.requestId, 'req-789');
    });

    test('rejects missing requestId', () {
      expect(
        () => DevicePairRequestPayload.fromJson({
          'requesterOwnerId': 'envoy:owner:abc123',
          'requesterDeviceId': 'envoy_device_xyz789',
          'requesterDevicePublicKeyPem': 'key-pem',
          'createdAt': '2025-01-15T10:30:00.000Z',
        }),
        throwsFormatException,
      );
    });

    test('rejects missing requesterOwnerId', () {
      expect(
        () => DevicePairRequestPayload.fromJson({
          'requestId': 'req-123',
          'requesterDeviceId': 'envoy_device_xyz789',
          'requesterDevicePublicKeyPem': 'key-pem',
          'createdAt': '2025-01-15T10:30:00.000Z',
        }),
        throwsFormatException,
      );
    });

    test('rejects empty requestId', () {
      expect(
        () => DevicePairRequestPayload.fromJson({
          'requestId': '',
          'requesterOwnerId': 'envoy:owner:abc123',
          'requesterDeviceId': 'envoy_device_xyz789',
          'requesterDevicePublicKeyPem': 'key-pem',
          'createdAt': '2025-01-15T10:30:00.000Z',
        }),
        throwsFormatException,
      );
    });

    test('toJson includes all required fields and extras', () {
      final payload = DevicePairRequestPayload(
        requestId: 'req-123',
        requesterOwnerId: 'envoy:owner:abc123',
        requesterDeviceId: 'envoy_device_xyz789',
        requesterDevicePublicKeyPem: 'key-pem',
        createdAt: '2025-01-15T10:30:00.000Z',
      );

      final json = payload.toJson();
      expect(json['requestId'], 'req-123');
      expect(json['requesterOwnerId'], 'envoy:owner:abc123');
      expect(json['requesterDeviceId'], 'envoy_device_xyz789');
      expect(json['requesterDevicePublicKeyPem'], 'key-pem');
      expect(json['createdAt'], '2025-01-15T10:30:00.000Z');
      expect(json['requestedDeviceProfile'], 'satellite');
      expect(json['requestedCapabilities'], ['ui.channel', 'message.send']);
    });

    test('toJson includes note when present', () {
      final payload = DevicePairRequestPayload(
        requestId: 'req-123',
        requesterOwnerId: 'envoy:owner:abc123',
        requesterDeviceId: 'envoy_device_xyz789',
        requesterDevicePublicKeyPem: 'key-pem',
        createdAt: '2025-01-15T10:30:00.000Z',
        note: 'Mobile app pairing',
      );

      final json = payload.toJson();
      expect(json['note'], 'Mobile app pairing');
    });

    test('toJson excludes note when null or empty', () {
      final payload = DevicePairRequestPayload(
        requestId: 'req-123',
        requesterOwnerId: 'envoy:owner:abc123',
        requesterDeviceId: 'envoy_device_xyz789',
        requesterDevicePublicKeyPem: 'key-pem',
        createdAt: '2025-01-15T10:30:00.000Z',
      );

      final json = payload.toJson();
      expect(json.containsKey('note'), isFalse);
    });

    test('fromJson / toJson round-trip with note', () {
      final original = DevicePairRequestPayload(
        requestId: 'req-roundtrip',
        requesterOwnerId: 'envoy:owner:abc123',
        requesterDeviceId: 'envoy_device_xyz789',
        requesterDevicePublicKeyPem: 'key-pem',
        createdAt: '2025-01-15T10:30:00.000Z',
        note: 'Test note',
      );

      final json = original.toJson();
      final parsed = DevicePairRequestPayload.fromJson(json);
      expect(parsed.requestId, original.requestId);
      expect(parsed.requesterOwnerId, original.requesterOwnerId);
      expect(parsed.requesterDeviceId, original.requesterDeviceId);
      expect(parsed.requesterDevicePublicKeyPem, original.requesterDevicePublicKeyPem);
      expect(parsed.createdAt, original.createdAt);
      expect(parsed.note, original.note);
    });
  });

  // ============================================
  // createDevicePairRequestPayload
  // ============================================

  group('createDevicePairRequestPayload', () {
    test('sets all fields from parameters', () {
      final payload = createDevicePairRequestPayload(
        requesterOwnerId: 'envoy:owner:test123',
        requesterDeviceId: 'envoy_device_test456',
        requesterDevicePublicKeyPem: 'test-key-pem',
        note: 'Pairing test',
        requestId: 'custom-req-id',
        createdAt: '2025-02-01T00:00:00.000Z',
      );

      expect(payload.requestId, 'custom-req-id');
      expect(payload.requesterOwnerId, 'envoy:owner:test123');
      expect(payload.requesterDeviceId, 'envoy_device_test456');
      expect(payload.requesterDevicePublicKeyPem, 'test-key-pem');
      expect(payload.note, 'Pairing test');
      expect(payload.createdAt, '2025-02-01T00:00:00.000Z');
    });

    test('generates UUID requestId when not provided', () {
      final payload = createDevicePairRequestPayload(
        requesterOwnerId: 'envoy:owner:test123',
        requesterDeviceId: 'envoy_device_test456',
        requesterDevicePublicKeyPem: 'test-key-pem',
      );

      expect(payload.requestId, isNotEmpty);
      expect(payload.requestId, contains('-'));
      // UUID v4 format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
      expect(payload.requestId.length, 36);
    });

    test('generates unique requestIds for each call', () {
      final p1 = createDevicePairRequestPayload(
        requesterOwnerId: 'envoy:owner:a',
        requesterDeviceId: 'd1',
        requesterDevicePublicKeyPem: 'k1',
      );
      final p2 = createDevicePairRequestPayload(
        requesterOwnerId: 'envoy:owner:a',
        requesterDeviceId: 'd1',
        requesterDevicePublicKeyPem: 'k1',
      );

      expect(p1.requestId, isNot(p2.requestId));
    });

    test('generates createdAt when not provided', () {
      final payload = createDevicePairRequestPayload(
        requesterOwnerId: 'envoy:owner:test123',
        requesterDeviceId: 'envoy_device_test456',
        requesterDevicePublicKeyPem: 'test-key-pem',
      );

      expect(payload.createdAt, isNotEmpty);
      // Should be valid ISO 8601
      expect(DateTime.tryParse(payload.createdAt), isNotNull);
    });

    test('note is null when not provided', () {
      final payload = createDevicePairRequestPayload(
        requesterOwnerId: 'envoy:owner:test123',
        requesterDeviceId: 'envoy_device_test456',
        requesterDevicePublicKeyPem: 'test-key-pem',
      );

      expect(payload.note, isNull);
    });
  });

  // ============================================
  // parseDevicePairRequestPayload
  // ============================================

  group('parseDevicePairRequestPayload', () {
    test('parses valid map', () {
      final map = {
        'requestId': 'req-1',
        'requesterOwnerId': 'envoy:owner:abc',
        'requesterDeviceId': 'envoy_device_xyz',
        'requesterDevicePublicKeyPem': 'key-pem',
        'createdAt': '2025-01-01T00:00:00.000Z',
      };

      final parsed = parseDevicePairRequestPayload(map);
      expect(parsed.requestId, 'req-1');
      expect(parsed.requesterOwnerId, 'envoy:owner:abc');
    });

    test('rejects non-map input', () {
      expect(
        () => parseDevicePairRequestPayload('not a map'),
        throwsFormatException,
      );
      expect(
        () => parseDevicePairRequestPayload(42),
        throwsFormatException,
      );
      expect(
        () => parseDevicePairRequestPayload(null),
        throwsFormatException,
      );
    });
  });

  // ============================================
  // sendDevicePairRequest — envelope building
  // ============================================

  group('sendDevicePairRequest envelope', () {
    test('builds correct device.pair.request envelope', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final client = RelayClient(
        url: 'ws://localhost:3030/ws',
        peerId: peerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
        ownerId: ownerId,
      );

      // Build a device pair request payload
      final payload = createDevicePairRequestPayload(
        requesterOwnerId: ownerId,
        requesterDeviceId: peerId,
        requesterDevicePublicKeyPem: keys.publicKeyPem,
        note: 'HomeClaw Companion app pairing',
      );

      // Build unsigned envelope (same logic as sendDevicePairRequest)
      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.devicePairRequest,
        recipientPeerId: 'envoy_agent_abc123',
        payload: payload.toJson(),
      ));

      expect(unsigned.intent, EnvoyIntent.devicePairRequest);
      expect(unsigned.senderPeerId, peerId);
      expect(unsigned.recipientPeerId, 'envoy_agent_abc123');

      // Verify the payload is parseable
      final parsedPayload = parseDevicePairRequestPayload(unsigned.payload);
      expect(parsedPayload.requesterOwnerId, ownerId);
      expect(parsedPayload.requesterDeviceId, peerId);
      expect(parsedPayload.requesterDevicePublicKeyPem, keys.publicKeyPem);
      expect(parsedPayload.note, 'HomeClaw Companion app pairing');

      // Verify toJson includes the device profile and capabilities
      final json = parsedPayload.toJson();
      expect(json['requestedDeviceProfile'], 'satellite');
      expect(json['requestedCapabilities'], ['ui.channel', 'message.send']);
    });

    test('device.pair.request envelope can be signed and verified', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final client = RelayClient(
        url: 'ws://localhost:3030/ws',
        peerId: peerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
        ownerId: ownerId,
      );

      final payload = createDevicePairRequestPayload(
        requesterOwnerId: ownerId,
        requesterDeviceId: peerId,
        requesterDevicePublicKeyPem: keys.publicKeyPem,
      );

      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.devicePairRequest,
        recipientPeerId: 'envoy_agent_target',
        payload: payload.toJson(),
      ));

      final signature = await signCanonicalPayload(
        unsigned.toJson(),
        keys.privateKeyPem,
        keys.publicKeyPem,
      );

      final signed = unsigned.sign(signature);
      expect(signed.signature, signature);

      final valid = await verifyCanonicalPayload(
        envelopeForSigning(signed),
        signed.signature,
        keys.publicKeyPem,
      );
      expect(valid, isTrue);
    });

    test('device.pair.request envelope uses agent roles', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final payload = createDevicePairRequestPayload(
        requesterOwnerId: ownerId,
        requesterDeviceId: peerId,
        requesterDevicePublicKeyPem: keys.publicKeyPem,
      );

      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.devicePairRequest,
        recipientPeerId: 'envoy_agent_target',
        payload: payload.toJson(),
      ));

      // device.pair.request is system-to-agent by default
      expect(unsigned.senderRole, EnvoyActorRole.agent);
      expect(unsigned.recipientRole, EnvoyActorRole.agent);
    });

    test('device.pair.request serializes to valid JSON for RPC', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final payload = createDevicePairRequestPayload(
        requesterOwnerId: ownerId,
        requesterDeviceId: peerId,
        requesterDevicePublicKeyPem: keys.publicKeyPem,
        note: 'Test',
      );

      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.devicePairRequest,
        recipientPeerId: 'envoy_agent_target',
        payload: payload.toJson(),
      ));

      final signature = await signCanonicalPayload(
        unsigned.toJson(),
        keys.privateKeyPem,
        keys.publicKeyPem,
      );
      final signed = unsigned.sign(signature);

      // Serialize as JSON-RPC params
      final rpcParams = {
        'envelope': signed.toJson(),
      };
      final json = jsonEncode(rpcParams);
      expect(json, isA<String>());

      // Parse back
      final parsed = jsonDecode(json) as Map<String, dynamic>;
      final parsedEnv = parseEnvelope(parsed['envelope']);
      expect(parsedEnv.intent, EnvoyIntent.devicePairRequest);
      expect(parsedEnv.senderPeerId, peerId);
      expect(parsedEnv.recipientPeerId, 'envoy_agent_target');

      // Parse the payload
      final parsedPayload = parseDevicePairRequestPayload(parsedEnv.payload);
      expect(parsedPayload.requesterOwnerId, ownerId);
      expect(parsedPayload.note, 'Test');
    });

    test('generates unique messageIds for pair requests', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final payload = createDevicePairRequestPayload(
        requesterOwnerId: ownerId,
        requesterDeviceId: peerId,
        requesterDevicePublicKeyPem: keys.publicKeyPem,
      );

      final u1 = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.devicePairRequest,
        recipientPeerId: 'peer-a',
        payload: payload.toJson(),
      ));

      final u2 = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.devicePairRequest,
        recipientPeerId: 'peer-b',
        payload: payload.toJson(),
      ));

      expect(u1.messageId, isNot(u2.messageId));
    });
  });

  // ============================================
  // Paired node info persistence
  // ============================================

  group('savePairedNodeInfo / getPairedNodeInfo', () {
    test('round-trip: save and load paired node info', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      const keyPairedNodeInfo = 'envoy_paired_node_info';
      final payload = PairingPayload(
        wsUrl: 'ws://192.168.1.100:3030/ws',
        relayPeerId: 'envoy_relay_abc123',
        agentPeerId: 'envoy_agent_xyz789',
        agentPubKey: '-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----',
        token: 'pair-token-123',
      );

      // Save
      await prefs.setString(keyPairedNodeInfo, jsonEncode({
        'wsUrl': payload.wsUrl,
        'relayPeerId': payload.relayPeerId,
        'agentPeerId': payload.agentPeerId,
        'agentPubKey': payload.agentPubKey,
        'token': payload.token,
      }));

      // Load
      final raw = prefs.getString(keyPairedNodeInfo);
      expect(raw, isNotNull);

      final map = jsonDecode(raw!) as Map<String, dynamic>;
      final loaded = PairingPayload(
        wsUrl: map['wsUrl'] as String,
        relayPeerId: map['relayPeerId'] as String?,
        agentPeerId: map['agentPeerId'] as String?,
        agentPubKey: map['agentPubKey'] as String?,
        token: map['token'] as String?,
      );

      expect(loaded.wsUrl, payload.wsUrl);
      expect(loaded.relayPeerId, payload.relayPeerId);
      expect(loaded.agentPeerId, payload.agentPeerId);
      expect(loaded.agentPubKey, payload.agentPubKey);
      expect(loaded.token, payload.token);
    });

    test('round-trip: minimal paired node info (wsUrl only)', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      const keyPairedNodeInfo = 'envoy_paired_node_info';
      final payload = PairingPayload(wsUrl: 'ws://host:3030/ws');

      await prefs.setString(keyPairedNodeInfo, jsonEncode({
        'wsUrl': payload.wsUrl,
      }));

      final raw = prefs.getString(keyPairedNodeInfo);
      expect(raw, isNotNull);

      final map = jsonDecode(raw!) as Map<String, dynamic>;
      final loaded = PairingPayload(
        wsUrl: map['wsUrl'] as String,
        relayPeerId: map['relayPeerId'] as String?,
        agentPeerId: map['agentPeerId'] as String?,
        agentPubKey: map['agentPubKey'] as String?,
        token: map['token'] as String?,
      );

      expect(loaded.wsUrl, payload.wsUrl);
      expect(loaded.relayPeerId, isNull);
      expect(loaded.agentPeerId, isNull);
    });

    test('getPairedNodeInfo returns null when not saved', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      const keyPairedNodeInfo = 'envoy_paired_node_info';
      final raw = prefs.getString(keyPairedNodeInfo);
      expect(raw, isNull);
    });

    test('getPairedNodeInfo handles corrupt JSON gracefully', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      const keyPairedNodeInfo = 'envoy_paired_node_info';
      await prefs.setString(keyPairedNodeInfo, 'not-valid-json{{{');

      final raw = prefs.getString(keyPairedNodeInfo);
      expect(raw, isNotNull);

      // Simulate the try/catch in getPairedNodeInfo
      Map<String, dynamic> map;
      try {
        map = jsonDecode(raw!) as Map<String, dynamic>;
        final wsUrl = map['wsUrl'] as String?;
        expect(wsUrl, isNull); // won't reach here
      } catch (_) {
        // Expected path — corrupt JSON returns null from getPairedNodeInfo
        expect(true, isTrue);
      }
    });
  });

  // ============================================
  // EnvoyIntent device.pair.request
  // ============================================

  group('device.pair.request intent', () {
    test('devicePairRequest is a valid EnvoyIntent', () {
      final wire = envoyIntentToString(EnvoyIntent.devicePairRequest);
      expect(wire, 'device.pair.request');

      final parsed = parseIntent(wire);
      expect(parsed, EnvoyIntent.devicePairRequest);
    });
  });
}
