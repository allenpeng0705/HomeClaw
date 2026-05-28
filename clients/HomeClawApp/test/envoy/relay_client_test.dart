import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/envoy/envoy_identity.dart';
import 'package:home_claw_app/envoy/envoy_protocol.dart';
import 'package:home_claw_app/envoy/relay_client.dart';

void main() {
  group('relayReconnectDelayMs', () {
    test('exponential backoff then plateau at max delay', () {
      expect(relayReconnectDelayMs(-2), relayReconnectDelayMs(0));
      expect(relayReconnectDelayMs(-1), relayReconnectDelayMs(0));
      expect(relayReconnectDelayMs(0), kRelayReconnectBaseMs);
      expect(relayReconnectDelayMs(1), kRelayReconnectBaseMs * 2);
      expect(relayReconnectDelayMs(2), kRelayReconnectBaseMs * 4);
      expect(relayReconnectDelayMs(6), 32000);
      expect(relayReconnectDelayMs(7), kRelayReconnectMaxDelayMs);
      expect(relayReconnectDelayMs(99), kRelayReconnectMaxDelayMs);
    });
  });

  // ============================================
  // RelayClient state lifecycle
  // ============================================

  group('RelayClient state', () {
    test('starts in disconnected state', () async {
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

      expect(client.state, RelayClientState.disconnected);
    });

    test('calls onStateChange when state transitions', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final states = <RelayClientState>[];
      final client = RelayClient(
        url: 'ws://localhost:3030/ws',
        peerId: peerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
        ownerId: ownerId,
        onStateChange: (s) => states.add(s),
      );

      // Will fail to connect (no server), but should transition through connecting -> error
      try {
        await client.connect().timeout(const Duration(seconds: 2));
      } catch (_) {}

      // At minimum, we should see connecting state
      expect(states, contains(RelayClientState.connecting));
    });
  });

  // ============================================
  // sendChatMessage builds correct envelope
  // ============================================

  group('sendChatMessage envelope', () {
    test('builds signed envelope with correct fields', () async {
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

      // Manually build the envelope (sendChatMessage calls forwardEnvelope which needs a server)
      final payload = createChatMessagePayload(
        senderOwnerId: ownerId,
        text: 'Hello from mobile!',
      );

      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.chatMessage,
        recipientPeerId: 'envoy_agent_abc123',
        payload: payload.toJson(),
      ));

      expect(unsigned.version, '0.1');
      expect(unsigned.intent, EnvoyIntent.chatMessage);
      expect(unsigned.senderPeerId, peerId);
      expect(unsigned.recipientPeerId, 'envoy_agent_abc123');
      expect(unsigned.senderRole, EnvoyActorRole.human);
      expect(unsigned.recipientRole, EnvoyActorRole.human);

      // Parse the payload
      final chatPayload = parseChatMessagePayload(unsigned.payload);
      expect(chatPayload.senderOwnerId, ownerId);
      expect(chatPayload.text, 'Hello from mobile!');

      // Sign it
      final signature = await signCanonicalPayload(
        unsigned.toJson(),
        keys.privateKeyPem,
        keys.publicKeyPem,
      );

      final signed = unsigned.sign(signature);
      expect(signed.signature, signature);

      // Verify it
      final valid = await verifyCanonicalPayload(
        envelopeForSigning(signed),
        signed.signature,
        keys.publicKeyPem,
      );
      expect(valid, isTrue);
    });

    test('generates unique messageIds', () async {
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

      // Build two envelopes manually
      final u1 = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.chatMessage,
        recipientPeerId: 'peer-a',
        payload: {'senderOwnerId': ownerId, 'text': 'msg 1'},
      ));

      final u2 = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.chatMessage,
        recipientPeerId: 'peer-b',
        payload: {'senderOwnerId': ownerId, 'text': 'msg 2'},
      ));

      expect(u1.messageId, isNot(u2.messageId));
    });

    test('envelope serializes to valid JSON for RPC', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final payload = createChatMessagePayload(
        senderOwnerId: ownerId,
        text: 'test message',
      );

      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.chatMessage,
        recipientPeerId: 'envoy_agent_abc123',
        payload: payload.toJson(),
      ));

      final signature = await signCanonicalPayload(
        unsigned.toJson(),
        keys.privateKeyPem,
        keys.publicKeyPem,
      );
      final signed = unsigned.sign(signature);

      // This is what gets sent over WebSocket as params.envelope
      final rpcParams = {
        'envelope': signed.toJson(),
      };

      final json = jsonEncode(rpcParams);
      expect(json, isA<String>());

      // Verify it can be parsed back
      final parsed = jsonDecode(json) as Map<String, dynamic>;
      final parsedEnv = parseEnvelope(parsed['envelope']);
      expect(parsedEnv.messageId, unsigned.messageId);
      expect(parsedEnv.intent, EnvoyIntent.chatMessage);
    });
  });

  // ============================================
  // forwardEnvelope with relay.lookup payload
  // ============================================

  group('forwardEnvelope relay.lookup', () {
    test('builds relay.lookup envelope correctly', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);

      final payload = RelayLookupPayload(
        queryId: 'q1',
        capability: 'mesh.discovery',
        visibilityScope: RelayVisibility.public,
        maxResults: 5,
        expiresAt: DateTime.now().toUtc().add(const Duration(minutes: 5)).toIso8601String(),
      );

      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.relayLookup,
        payload: payload.toJson(),
      ));

      expect(unsigned.intent, EnvoyIntent.relayLookup);
      expect(unsigned.senderRole, EnvoyActorRole.agent);
      expect(unsigned.recipientRole, EnvoyActorRole.agent);

      final parsedPayload = parseRelayLookupPayload(unsigned.payload);
      expect(parsedPayload.queryId, 'q1');
      expect(parsedPayload.capability, 'mesh.discovery');
    });
  });

  // ============================================
  // Inbound envelope handling
  // ============================================

  group('inbound envelope', () {
    test('parse p2p:envelope event JSON', () {
      final eventJson = {
        'event': 'p2p:envelope',
        'data': {
          'envelope': {
            'version': '0.1',
            'messageId': 'msg-1',
            'createdAt': '2025-01-01T00:00:00.000Z',
            'senderPeerId': 'envoy_sender123',
            'senderPublicKey': 'pem-key',
            'senderRole': 'human',
            'recipientRole': 'human',
            'recipientPeerId': 'envoy_mobile123',
            'intent': 'chat.message',
            'payload': {
              'senderOwnerId': 'envoy:owner:sender',
              'text': 'Hello from home node!',
            },
            'signature': 'sig-data',
          },
          'remotePeerId': '12D3KooW...',
        },
      };

      final event = eventJson['event'] as String;
      expect(event, 'p2p:envelope');

      final data = eventJson['data'] as Map<String, dynamic>;
      final envelope = data['envelope'] as Map<String, dynamic>;

      final parsed = parseEnvelope(envelope);
      expect(parsed.intent, EnvoyIntent.chatMessage);
      expect(parsed.senderPeerId, 'envoy_sender123');
      expect(parsed.recipientPeerId, 'envoy_mobile123');

      final chatPayload = parseChatMessagePayload(parsed.payload);
      expect(chatPayload.text, 'Hello from home node!');
      expect(chatPayload.senderOwnerId, 'envoy:owner:sender');
    });

    test('verify inbound envelope signature', () async {
      // Generate sender keys
      final senderKeys = await generateEd25519KeyPair();
      final senderPeerId = derivePeerId(senderKeys.publicKeyPem);
      final senderOwnerId = deriveOwnerId(senderKeys.publicKeyPem);

      // Build and sign a chat.message as the sender
      final payload = createChatMessagePayload(
        senderOwnerId: senderOwnerId,
        text: 'Inbound test',
      );
      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: senderPeerId,
        senderPublicKey: senderKeys.publicKeyPem,
        intent: EnvoyIntent.chatMessage,
        recipientPeerId: 'envoy_recipient',
        payload: payload.toJson(),
      ));
      final signature = await signCanonicalPayload(
        unsigned.toJson(),
        senderKeys.privateKeyPem,
        senderKeys.publicKeyPem,
      );
      final signed = unsigned.sign(signature);

      // This simulates what the receiver does:
      // 1. Parse envelope from JSON
      final envelopeJson = signed.toJson();
      final parsed = parseEnvelope(envelopeJson);

      // 2. Verify signature using envelopeForSigning
      final unsignedForm = envelopeForSigning(parsed);
      final valid = await verifyCanonicalPayload(
        unsignedForm,
        parsed.signature,
        senderKeys.publicKeyPem, // sender's pub key from envelope
      );
      expect(valid, isTrue);

      // 3. Parse typed payload
      final chatPayload = parseChatMessagePayload(parsed.payload);
      expect(chatPayload.text, 'Inbound test');
    });

    test('rejects tampered inbound envelope', () async {
      final senderKeys = await generateEd25519KeyPair();
      final senderPeerId = derivePeerId(senderKeys.publicKeyPem);

      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: senderPeerId,
        senderPublicKey: senderKeys.publicKeyPem,
        intent: EnvoyIntent.chatMessage,
        recipientPeerId: 'envoy_recipient',
        payload: {'senderOwnerId': 'owner', 'text': 'original'},
      ));
      final signature = await signCanonicalPayload(
        unsigned.toJson(),
        senderKeys.privateKeyPem,
        senderKeys.publicKeyPem,
      );
      final signed = unsigned.sign(signature);

      // Tamper
      final tamperedJson = signed.toJson();
      (tamperedJson['payload'] as Map)['text'] = 'tampered';

      final unsignedForm = Map<String, dynamic>.from(tamperedJson);
      unsignedForm.remove('signature');

      final valid = await verifyCanonicalPayload(
        unsignedForm,
        signed.signature,
        senderKeys.publicKeyPem,
      );
      expect(valid, isFalse);
    });
  });

  // ============================================
  // Server push dispatch (p2p:envelope, bridge:status)
  // ============================================

  group('relayDispatchServerPush', () {
    test('bridge:status with Map<String,dynamic> data invokes onBridgeStatus', () {
      Map<String, dynamic>? got;
      relayDispatchServerPush(
        {
          'event': 'bridge:status',
          'data': {'enabled': true, 'agentPeerId': 'envoy_agent_xyz'},
        },
        onBridgeStatus: (m) => got = m,
      );
      expect(got, isNotNull);
      expect(got!['enabled'], isTrue);
      expect(got!['agentPeerId'], 'envoy_agent_xyz');
    });

    test('bridge:status with untyped Map copies to Map<String,dynamic>', () {
      Map<String, dynamic>? got;
      relayDispatchServerPush(
        {
          'event': 'bridge:status',
          'data': <dynamic, dynamic>{
            'enabled': false,
          },
        },
        onBridgeStatus: (m) => got = m,
      );
      expect(got, isNotNull);
      expect(got!['enabled'], isFalse);
    });

    test('bridge:status with non-map data does not invoke callback', () {
      var called = false;
      relayDispatchServerPush(
        {
          'event': 'bridge:status',
          'data': 'invalid',
        },
        onBridgeStatus: (_) => called = true,
      );
      expect(called, isFalse);
    });

    test('p2p:envelope invokes onEnvelope with remotePeerId', () {
      Map<String, dynamic>? env;
      String? rpid;
      relayDispatchServerPush(
        {
          'event': 'p2p:envelope',
          'data': {
            'envelope': {
              'version': '0.1',
              'messageId': 'm1',
              'createdAt': '2026-01-01T00:00:00.000Z',
              'senderPeerId': 'a',
              'senderPublicKey': 'pem',
              'senderRole': 'human',
              'recipientRole': 'human',
              'intent': 'chat.message',
              'payload': {'senderOwnerId': 'o', 'text': 'hi'},
              'signature': 'sig',
            },
            'remotePeerId': '12D3KooWabc',
          },
        },
        onEnvelope: (e, r) {
          env = e;
          rpid = r;
        },
      );
      expect(env, isNotNull);
      expect(env!['messageId'], 'm1');
      expect(rpid, '12D3KooWabc');
    });
  });

  // ============================================
  // JSON-RPC message format
  // ============================================

  group('JSON-RPC format', () {
    test('request shape matches JSON-RPC 2.0 (numeric id)', () {
      final request = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'forwardEnvelope',
        'params': {
          'envelope': {'version': '0.1', 'intent': 'chat.message'},
        },
      };

      expect(request['jsonrpc'], '2.0');
      expect(request.containsKey('id'), isTrue);
      expect(request.containsKey('method'), isTrue);
      expect(request.containsKey('params'), isTrue);
    });

    test('event format is valid', () {
      final event = {
        'event': 'p2p:envelope',
        'data': {
          'envelope': {},
          'remotePeerId': '12D3KooW...',
        },
      };

      expect(event.containsKey('event'), isTrue);
      expect(event.containsKey('data'), isTrue);
      expect(event.containsKey('id'), isFalse); // events don't have id
    });
  });

  // ============================================
  // Disconnect state
  // ============================================

  group('disconnect', () {
    test('disconnect resets state', () async {
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

      await client.disconnect();
      expect(client.state, RelayClientState.disconnected);
    });

    test('forwardEnvelope throws when disconnected', () async {
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

      // Build a signed envelope — this succeeds locally
      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.chatMessage,
        recipientPeerId: 'envoy_agent_abc123',
        payload: {'senderOwnerId': ownerId, 'text': 'hello'},
      ));
      final sig = await signCanonicalPayload(
        unsigned.toJson(),
        keys.privateKeyPem,
        keys.publicKeyPem,
      );
      final signed = unsigned.sign(sig);

      // But forwarding should fail because we're not connected
      expect(
        () => client.forwardEnvelope(signed),
        throwsStateError,
      );
    });
  });
}
