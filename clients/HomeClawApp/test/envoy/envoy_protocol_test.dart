import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/envoy/envoy_identity.dart';
import 'package:home_claw_app/envoy/envoy_protocol.dart';

void main() {
  // ============================================
  // Intent parsing
  // ============================================

  group('EnvoyIntent', () {
    test('parseIntent round-trips all intents', () {
      for (final intent in EnvoyIntent.values) {
        final wireStr = envoyIntentToString(intent);
        final parsed = parseIntent(wireStr);
        expect(parsed, intent);
      }
    });

    test('parseIntent returns null for invalid string', () {
      expect(parseIntent('invalid.intent'), isNull);
      expect(parseIntent(''), isNull);
      expect(parseIntent('chat message'), isNull);
    });
  });

  // ============================================
  // ChatMessagePayload
  // ============================================

  group('ChatMessagePayload', () {
    test('fromJson / toJson round-trip', () {
      final payload = ChatMessagePayload(
        senderOwnerId: 'envoy:owner:abc123',
        text: 'Hello, world!',
      );
      final json = payload.toJson();
      expect(json, {'senderOwnerId': 'envoy:owner:abc123', 'text': 'Hello, world!'});

      final parsed = ChatMessagePayload.fromJson(json);
      expect(parsed.senderOwnerId, 'envoy:owner:abc123');
      expect(parsed.text, 'Hello, world!');
    });

    test('createChatMessagePayload', () {
      final payload = createChatMessagePayload(
        senderOwnerId: 'envoy:owner:abc123',
        text: 'hello',
      );
      expect(payload.senderOwnerId, 'envoy:owner:abc123');
      expect(payload.text, 'hello');
    });

    test('rejects missing senderOwnerId', () {
      expect(
        () => ChatMessagePayload.fromJson({'text': 'hello'}),
        throwsFormatException,
      );
    });

    test('rejects missing text', () {
      expect(
        () => ChatMessagePayload.fromJson({'senderOwnerId': 'x'}),
        throwsFormatException,
      );
    });

    test('rejects text over 4000 chars', () {
      expect(
        () => ChatMessagePayload.fromJson({
          'senderOwnerId': 'x',
          'text': 'a' * 4001,
        }),
        throwsFormatException,
      );
    });

    test('accepts text at exactly 4000 chars', () {
      final payload = ChatMessagePayload.fromJson({
        'senderOwnerId': 'x',
        'text': 'a' * 4000,
      });
      expect(payload.text.length, 4000);
    });
  });

  // ============================================
  // SystemPingPayload
  // ============================================

  group('SystemPingPayload', () {
    test('with message', () {
      final payload = SystemPingPayload(nonce: 'n1', message: 'hello');
      final json = payload.toJson();
      expect(json, {'nonce': 'n1', 'message': 'hello'});

      final parsed = SystemPingPayload.fromJson(json);
      expect(parsed.nonce, 'n1');
      expect(parsed.message, 'hello');
    });

    test('without message', () {
      final payload = SystemPingPayload(nonce: 'n1');
      final json = payload.toJson();
      expect(json, {'nonce': 'n1'});
      expect(json.containsKey('message'), isFalse);

      final parsed = SystemPingPayload.fromJson(json);
      expect(parsed.nonce, 'n1');
      expect(parsed.message, isNull);
    });

    test('createSystemPingPayload generates nonce', () {
      final p1 = createSystemPingPayload();
      final p2 = createSystemPingPayload();
      expect(p1.nonce, isNotEmpty);
      expect(p1.nonce, isNot(p2.nonce));
    });

    test('rejects missing nonce', () {
      expect(
        () => SystemPingPayload.fromJson({}),
        throwsFormatException,
      );
    });

    test('rejects message over 512 chars', () {
      // 512 chars is allowed, 513 is not
      expect(
        () => SystemPingPayload.fromJson({
          'nonce': 'n',
          'message': 'a' * 513,
        }),
        throwsFormatException,
      );
    });
  });

  // ============================================
  // SystemSignalPayload
  // ============================================

  group('SystemSignalPayload', () {
    test('fromJson / toJson round-trip', () {
      final json = {
        'ownerId': 'envoy:owner:abc',
        'ownerPublicKeyPem': '-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n',
        'deviceId': 'envoy:device:xyz',
        'deviceCertificate': {
          'version': '0.1',
          'certificateId': 'cert-1',
          'ownerId': 'envoy:owner:abc',
          'deviceId': 'envoy:device:xyz',
          'devicePublicKeyPem': '-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n',
          'deviceProfile': 'primary',
          'capabilities': ['mesh.listen'],
          'issuedAt': '2025-01-01T00:00:00.000Z',
          'expiresAt': null,
          'signature': 'sig1',
        },
        'deviceProfile': 'primary',
        'capabilities': ['mesh.listen'],
        'supportedProtocolVersions': ['0.1'],
        'status': 'online',
      };

      final parsed = SystemSignalPayload.fromJson(json);
      expect(parsed.ownerId, 'envoy:owner:abc');
      expect(parsed.status, 'online');
      expect(parsed.listenAddrs, isEmpty);
      expect(parsed.publicTopics, isEmpty);

      final reJson = parsed.toJson();
      expect(reJson['ownerId'], 'envoy:owner:abc');
      expect(reJson['status'], 'online');
    });

    test('defaults status to online', () {
      final json = {
        'ownerId': 'envoy:owner:abc',
        'ownerPublicKeyPem': 'pem',
        'deviceId': 'envoy:device:xyz',
        'deviceCertificate': {'version': '0.1'},
        'deviceProfile': 'primary',
        'capabilities': ['mesh.listen'],
        'supportedProtocolVersions': ['0.1'],
      };

      final parsed = SystemSignalPayload.fromJson(json);
      expect(parsed.status, 'online');
    });

    test('rejects invalid status', () {
      final json = {
        'ownerId': 'envoy:owner:abc',
        'ownerPublicKeyPem': 'pem',
        'deviceId': 'envoy:device:xyz',
        'deviceCertificate': {'version': '0.1'},
        'deviceProfile': 'primary',
        'capabilities': ['mesh.listen'],
        'supportedProtocolVersions': ['0.1'],
        'status': 'invalid',
      };

      expect(
        () => SystemSignalPayload.fromJson(json),
        throwsFormatException,
      );
    });
  });

  // ============================================
  // Relay payloads
  // ============================================

  group('RelayPeersRequestPayload', () {
    test('empty payload', () {
      const payload = RelayPeersRequestPayload();
      expect(payload.toJson(), {});
      final parsed = RelayPeersRequestPayload.fromJson({});
      expect(parsed.toJson(), {});
    });
  });

  group('RelayPeersResponsePayload', () {
    test('fromJson / toJson round-trip', () {
      final json = {
        'requestMessageId': 'msg-1',
        'peers': [
          {
            'peerId': 'peer-1',
            'ownerId': 'owner-1',
            'multiaddrs': ['/p2p-circuit/...'],
          },
        ],
      };

      final parsed = RelayPeersResponsePayload.fromJson(json);
      expect(parsed.requestMessageId, 'msg-1');
      expect(parsed.peers.length, 1);
      expect(parsed.peers[0].peerId, 'peer-1');
      expect(parsed.peers[0].ownerId, 'owner-1');
      expect(parsed.peers[0].multiaddrs, ['/p2p-circuit/...']);

      final reJson = parsed.toJson();
      expect(reJson['peers'], isA<List>());
    });

    test('empty peers list', () {
      final parsed = RelayPeersResponsePayload.fromJson({
        'requestMessageId': 'msg-1',
      });
      expect(parsed.peers, isEmpty);
      // toJson omits empty arrays
      expect((parsed.toJson() as Map)['peers'], null);
    });
  });

  group('RelayLookupPayload', () {
    test('by targetPeerId', () {
      final json = {
        'queryId': 'q1',
        'targetPeerId': 'peer-1',
        'expiresAt': '2025-01-01T00:00:00.000Z',
      };

      final parsed = RelayLookupPayload.fromJson(json);
      expect(parsed.queryId, 'q1');
      expect(parsed.targetPeerId, 'peer-1');
      expect(parsed.maxResults, 20);
      expect(parsed.maxHops, 0);
      expect(parsed.maxFanout, 2);
      expect(parsed.visibilityScope, RelayVisibility.public);
    });

    test('by targetOwnerId', () {
      final parsed = RelayLookupPayload.fromJson({
        'queryId': 'q1',
        'targetOwnerId': 'owner-1',
        'expiresAt': '2025-01-01T00:00:00.000Z',
      });
      expect(parsed.targetOwnerId, 'owner-1');
    });

    test('by capability', () {
      final parsed = RelayLookupPayload.fromJson({
        'queryId': 'q1',
        'capability': 'mesh.listen',
        'expiresAt': '2025-01-01T00:00:00.000Z',
      });
      expect(parsed.capability, 'mesh.listen');
    });

    test('by topicHash', () {
      final parsed = RelayLookupPayload.fromJson({
        'queryId': 'q1',
        'topicHash': 'abc123',
        'expiresAt': '2025-01-01T00:00:00.000Z',
      });
      expect(parsed.topicHash, 'abc123');
    });

    test('rejects without target', () {
      expect(
        () => RelayLookupPayload.fromJson({
          'queryId': 'q1',
          'expiresAt': '2025-01-01T00:00:00.000Z',
        }),
        throwsFormatException,
      );
    });

    test('custom visibility and limits', () {
      final parsed = RelayLookupPayload.fromJson({
        'queryId': 'q1',
        'targetPeerId': 'peer-1',
        'visibilityScope': 'bonded',
        'maxResults': 5,
        'maxHops': 1,
        'maxFanout': 3,
        'expiresAt': '2025-01-01T00:00:00.000Z',
      });
      expect(parsed.visibilityScope, RelayVisibility.bonded);
      expect(parsed.maxResults, 5);
      expect(parsed.maxHops, 1);
      expect(parsed.maxFanout, 3);
    });
  });

  group('RelayLookupResponsePayload', () {
    test('fromJson / toJson round-trip', () {
      final json = {
        'queryId': 'q1',
        'peers': [
          {
            'peerId': 'peer-1',
            'ownerId': 'owner-1',
            'multiaddrs': ['/p2p-circuit/...'],
            'viaRelayId': 'relay-1',
            'capabilities': ['mesh.listen'],
            'visibility': 'public',
          },
        ],
        'relayHints': [
          {
            'relayId': 'relay-1',
            'multiaddrs': ['/ip4/1.2.3.4/tcp/4001'],
          },
        ],
        'truncated': false,
        'expiresAt': '2025-01-01T00:00:00.000Z',
      };

      final parsed = RelayLookupResponsePayload.fromJson(json);
      expect(parsed.queryId, 'q1');
      expect(parsed.peers.length, 1);
      expect(parsed.peers[0].peerId, 'peer-1');
      expect(parsed.peers[0].viaRelayId, 'relay-1');
      expect(parsed.relayHints.length, 1);
      expect(parsed.relayHints[0].relayId, 'relay-1');
      expect(parsed.truncated, isFalse);
    });
  });

  group('RelayHintsRequestPayload', () {
    test('fromJson / toJson round-trip', () {
      final json = {
        'reason': 'bootstrap',
        'region': 'us-west',
        'maxResults': 5,
        'expiresAt': '2025-01-01T00:00:00.000Z',
      };

      final parsed = RelayHintsRequestPayload.fromJson(json);
      expect(parsed.reason, 'bootstrap');
      expect(parsed.region, 'us-west');
      expect(parsed.maxResults, 5);
    });

    test('defaults', () {
      final parsed = RelayHintsRequestPayload.fromJson({
        'expiresAt': '2025-01-01T00:00:00.000Z',
      });
      expect(parsed.reason, 'refresh');
      expect(parsed.maxResults, 10);
      expect(parsed.region, isNull);
    });

    test('rejects invalid reason', () {
      expect(
        () => RelayHintsRequestPayload.fromJson({
          'reason': 'unknown',
          'expiresAt': '2025-01-01T00:00:00.000Z',
        }),
        throwsFormatException,
      );
    });
  });

  // ============================================
  // RelayHint
  // ============================================

  group('RelayHint', () {
    test('fromJson / toJson round-trip', () {
      final json = {
        'relayId': 'relay-1',
        'level': 3,
        'region': 'us-west',
        'multiaddrs': ['/ip4/1.2.3.4/tcp/4001'],
        'scoreHint': 0.85,
        'expiresAt': '2025-01-01T00:00:00.000Z',
      };

      final parsed = RelayHint.fromJson(json);
      expect(parsed.relayId, 'relay-1');
      expect(parsed.level, 3);
      expect(parsed.region, 'us-west');
      expect(parsed.multiaddrs, ['/ip4/1.2.3.4/tcp/4001']);
      expect(parsed.scoreHint, 0.85);
      expect(parsed.expiresAt, '2025-01-01T00:00:00.000Z');
    });

    test('minimal relayId only', () {
      final parsed = RelayHint.fromJson({'relayId': 'relay-1'});
      expect(parsed.relayId, 'relay-1');
      expect(parsed.level, isNull);
      expect(parsed.multiaddrs, isEmpty);
      // toJson omits nulls and empty arrays
      expect(parsed.toJson(), {'relayId': 'relay-1'});
    });
  });

  // ============================================
  // Envelope construction (createUnsignedEnvelope)
  // ============================================

  group('createUnsignedEnvelope', () {
    test('creates chat.message envelope with human roles', () {
      final envelope = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: 'envoy_abc',
        senderPublicKey: '-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----\n',
        intent: EnvoyIntent.chatMessage,
        payload: {'senderOwnerId': 'owner1', 'text': 'hello'},
      ));

      expect(envelope.version, '0.1');
      expect(envelope.intent, EnvoyIntent.chatMessage);
      expect(envelope.senderRole, EnvoyActorRole.human);
      expect(envelope.recipientRole, EnvoyActorRole.human);
      expect(envelope.messageId, isNotEmpty);
      expect(envelope.createdAt, isNotEmpty);
    });

    test('creates system.ping envelope with system/agent roles', () {
      final envelope = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: 'envoy_abc',
        senderPublicKey: 'pem',
        intent: EnvoyIntent.systemPing,
        payload: {'nonce': 'n1'},
      ));

      expect(envelope.senderRole, EnvoyActorRole.system);
      expect(envelope.recipientRole, EnvoyActorRole.agent);
    });

    test('creates relay.lookup envelope with agent/agent roles', () {
      final envelope = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: 'envoy_abc',
        senderPublicKey: 'pem',
        intent: EnvoyIntent.relayLookup,
        payload: {'queryId': 'q1', 'targetPeerId': 'peer-1'},
      ));

      expect(envelope.senderRole, EnvoyActorRole.agent);
      expect(envelope.recipientRole, EnvoyActorRole.agent);
    });

    test('uses provided messageId and createdAt', () {
      final envelope = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: 'envoy_abc',
        senderPublicKey: 'pem',
        intent: EnvoyIntent.chatMessage,
        payload: {'senderOwnerId': 'o', 'text': 't'},
        messageId: 'custom-id',
        createdAt: '2025-01-01T00:00:00.000Z',
      ));

      expect(envelope.messageId, 'custom-id');
      expect(envelope.createdAt, '2025-01-01T00:00:00.000Z');
    });

    test('uses provided roles', () {
      final envelope = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: 'envoy_abc',
        senderPublicKey: 'pem',
        intent: EnvoyIntent.chatMessage,
        payload: {'senderOwnerId': 'o', 'text': 't'},
        senderRole: EnvoyActorRole.agent,
        recipientRole: EnvoyActorRole.human,
        agentCredential: {'version': '0.1', 'credentialId': 'cred-1'},
      ));

      expect(envelope.senderRole, EnvoyActorRole.agent);
      expect(envelope.recipientRole, EnvoyActorRole.human);
    });

    test('requires agentCredential for agent chat.message', () {
      expect(
        () => createUnsignedEnvelope(CreateEnvelopeInput(
          senderPeerId: 'envoy_abc',
          senderPublicKey: 'pem',
          intent: EnvoyIntent.chatMessage,
          payload: {'senderOwnerId': 'o', 'text': 't'},
          senderRole: EnvoyActorRole.agent,
        )),
        throwsArgumentError,
      );
    });

    test('allows agent chat.message with agentCredential', () {
      final envelope = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: 'envoy_abc',
        senderPublicKey: 'pem',
        intent: EnvoyIntent.chatMessage,
        payload: {'senderOwnerId': 'o', 'text': 't'},
        senderRole: EnvoyActorRole.agent,
        agentCredential: {'version': '0.1', 'credentialId': 'cred-1'},
      ));

      expect(envelope.senderRole, EnvoyActorRole.agent);
      expect(envelope.agentCredential, isNotNull);
    });
  });

  // ============================================
  // Envelope parsing (parseEnvelope)
  // ============================================

  group('parseEnvelope', () {
    test('parses valid signed envelope from JSON object', () {
      final json = {
        'version': '0.1',
        'messageId': 'msg-1',
        'createdAt': '2025-01-01T00:00:00.000Z',
        'senderPeerId': 'envoy_abc',
        'senderPublicKey': 'pem',
        'senderRole': 'human',
        'recipientRole': 'human',
        'intent': 'chat.message',
        'payload': {'senderOwnerId': 'owner1', 'text': 'hello'},
        'signature': 'sig-data',
      };

      final envelope = parseEnvelope(json);
      expect(envelope.version, '0.1');
      expect(envelope.messageId, 'msg-1');
      expect(envelope.intent, EnvoyIntent.chatMessage);
      expect(envelope.senderRole, EnvoyActorRole.human);
      expect(envelope.signature, 'sig-data');
    });

    test('parses valid signed envelope from JSON string', () {
      const jsonStr = '{"version":"0.1","messageId":"msg-1","createdAt":"2025-01-01T00:00:00.000Z","senderPeerId":"envoy_abc","senderPublicKey":"pem","senderRole":"human","recipientRole":"human","intent":"chat.message","payload":{"senderOwnerId":"o","text":"t"},"signature":"sig"}';

      final envelope = parseEnvelope(jsonStr);
      expect(envelope.messageId, 'msg-1');
      expect(envelope.signature, 'sig');
    });

    test('rejects missing signature', () {
      final json = {
        'version': '0.1',
        'messageId': 'msg-1',
        'createdAt': '2025-01-01T00:00:00.000Z',
        'senderPeerId': 'envoy_abc',
        'senderPublicKey': 'pem',
        'senderRole': 'human',
        'recipientRole': 'human',
        'intent': 'chat.message',
        'payload': {},
      };

      expect(() => parseEnvelope(json), throwsFormatException);
    });

    test('rejects invalid version', () {
      expect(
        () => parseEnvelope({
          'version': '0.2',
          'messageId': 'm',
          'createdAt': '2025-01-01T00:00:00.000Z',
          'senderPeerId': 'p',
          'senderPublicKey': 'k',
          'senderRole': 'human',
          'recipientRole': 'human',
          'intent': 'chat.message',
          'payload': {},
          'signature': 'sig',
        }),
        throwsFormatException,
      );
    });

    test('rejects invalid intent', () {
      expect(
        () => parseEnvelope({
          'version': '0.1',
          'messageId': 'm',
          'createdAt': '2025-01-01T00:00:00.000Z',
          'senderPeerId': 'p',
          'senderPublicKey': 'k',
          'senderRole': 'human',
          'recipientRole': 'human',
          'intent': 'invalid.intent',
          'payload': {},
          'signature': 'sig',
        }),
        throwsFormatException,
      );
    });

    test('rejects non-object input', () {
      expect(() => parseEnvelope('not-json'), throwsFormatException);
      expect(() => parseEnvelope(42), throwsFormatException);
    });

    test('envelopeForSigning strips signature', () {
      final envelope = parseEnvelope({
        'version': '0.1',
        'messageId': 'msg-1',
        'createdAt': '2025-01-01T00:00:00.000Z',
        'senderPeerId': 'envoy_abc',
        'senderPublicKey': 'pem',
        'senderRole': 'human',
        'recipientRole': 'human',
        'intent': 'chat.message',
        'payload': {'senderOwnerId': 'o', 'text': 't'},
        'signature': 'sig',
      });

      final unsigned = envelopeForSigning(envelope);
      expect(unsigned.containsKey('signature'), isFalse);
      expect(unsigned['version'], '0.1');
      expect(unsigned['messageId'], 'msg-1');
    });

    test('envelopeAsUnsigned drops signature', () {
      final envelope = parseEnvelope({
        'version': '0.1',
        'messageId': 'msg-1',
        'createdAt': '2025-01-01T00:00:00.000Z',
        'senderPeerId': 'envoy_abc',
        'senderPublicKey': 'pem',
        'senderRole': 'human',
        'recipientRole': 'human',
        'intent': 'chat.message',
        'payload': {'senderOwnerId': 'o', 'text': 't'},
        'signature': 'sig',
      });

      final unsigned = envelopeAsUnsigned(envelope);
      expect(unsigned, isA<UnsignedEnvoyEnvelope>());
    });
  });

  // ============================================
  // Role Policy
  // ============================================

  group('evaluateEnvelopeRolePolicy', () {
    test('allows human ↔ human chat', () {
      expect(
        evaluateEnvelopeRolePolicy(
          EnvoyIntent.chatMessage,
          EnvoyActorRole.human,
          EnvoyActorRole.human,
        ),
        isTrue,
      );
    });

    test('allows human ↔ agent chat', () {
      expect(
        evaluateEnvelopeRolePolicy(
          EnvoyIntent.chatMessage,
          EnvoyActorRole.human,
          EnvoyActorRole.agent,
        ),
        isTrue,
      );
    });

    test('allows agent ↔ human chat', () {
      expect(
        evaluateEnvelopeRolePolicy(
          EnvoyIntent.chatMessage,
          EnvoyActorRole.agent,
          EnvoyActorRole.human,
        ),
        isTrue,
      );
    });

    test('allows agent ↔ agent chat', () {
      expect(
        evaluateEnvelopeRolePolicy(
          EnvoyIntent.chatMessage,
          EnvoyActorRole.agent,
          EnvoyActorRole.agent,
        ),
        isTrue,
      );
    });

    test('disallows system in chat', () {
      expect(
        evaluateEnvelopeRolePolicy(
          EnvoyIntent.chatMessage,
          EnvoyActorRole.system,
          EnvoyActorRole.human,
        ),
        isFalse,
      );
      expect(
        evaluateEnvelopeRolePolicy(
          EnvoyIntent.chatMessage,
          EnvoyActorRole.human,
          EnvoyActorRole.system,
        ),
        isFalse,
      );
    });

    test('requires agent for task intents', () {
      expect(
        evaluateEnvelopeRolePolicy(
          EnvoyIntent.taskPropose,
          EnvoyActorRole.human,
          EnvoyActorRole.agent,
        ),
        isFalse,
      );
      expect(
        evaluateEnvelopeRolePolicy(
          EnvoyIntent.taskPropose,
          EnvoyActorRole.agent,
          EnvoyActorRole.human,
        ),
        isFalse,
      );
      expect(
        evaluateEnvelopeRolePolicy(
          EnvoyIntent.taskPropose,
          EnvoyActorRole.agent,
          EnvoyActorRole.agent,
        ),
        isTrue,
      );
    });

    test('requires agent for report.create', () {
      expect(
        evaluateEnvelopeRolePolicy(
          EnvoyIntent.reportCreate,
          EnvoyActorRole.human,
          EnvoyActorRole.agent,
        ),
        isFalse,
      );
      expect(
        evaluateEnvelopeRolePolicy(
          EnvoyIntent.reportCreate,
          EnvoyActorRole.agent,
          EnvoyActorRole.agent,
        ),
        isTrue,
      );
    });

    test('allows other intents with any roles', () {
      expect(
        evaluateEnvelopeRolePolicy(
          EnvoyIntent.systemPing,
          EnvoyActorRole.system,
          EnvoyActorRole.agent,
        ),
        isTrue,
      );
    });
  });

  // ============================================
  // Parse functions for typed payloads
  // ============================================

  group('parseChatMessagePayload', () {
    test('parses valid payload', () {
      final payload = parseChatMessagePayload({
        'senderOwnerId': 'owner-1',
        'text': 'hello',
      });
      expect(payload.senderOwnerId, 'owner-1');
      expect(payload.text, 'hello');
    });

    test('rejects non-object', () {
      expect(
        () => parseChatMessagePayload('not an object'),
        throwsFormatException,
      );
    });
  });

  group('parseSystemPingPayload', () {
    test('parses valid payload', () {
      final payload = parseSystemPingPayload({'nonce': 'n1'});
      expect(payload.nonce, 'n1');
    });
  });

  group('parseRelayPeersRequestPayload', () {
    test('parses empty payload', () {
      final payload = parseRelayPeersRequestPayload({});
      expect(payload.toJson(), {});
    });
  });

  group('parseRelayPeersResponsePayload', () {
    test('parses valid payload', () {
      final payload = parseRelayPeersResponsePayload({
        'requestMessageId': 'msg-1',
        'peers': [
          {'peerId': 'p1', 'ownerId': 'o1'},
        ],
      });
      expect(payload.requestMessageId, 'msg-1');
      expect(payload.peers.length, 1);
    });
  });

  group('parseRelayLookupPayload', () {
    test('parses valid payload', () {
      final payload = parseRelayLookupPayload({
        'queryId': 'q1',
        'targetPeerId': 'peer-1',
        'expiresAt': '2025-01-01T00:00:00.000Z',
      });
      expect(payload.queryId, 'q1');
      expect(payload.targetPeerId, 'peer-1');
    });
  });

  group('parseRelayLookupResponsePayload', () {
    test('parses valid payload', () {
      final payload = parseRelayLookupResponsePayload({
        'queryId': 'q1',
        'expiresAt': '2025-01-01T00:00:00.000Z',
      });
      expect(payload.queryId, 'q1');
    });
  });

  group('parseRelayHintsRequestPayload', () {
    test('parses valid payload', () {
      final payload = parseRelayHintsRequestPayload({
        'expiresAt': '2025-01-01T00:00:00.000Z',
      });
      expect(payload.reason, 'refresh');
    });
  });

  group('parseRelayHintsResponsePayload', () {
    test('parses valid payload', () {
      final payload = parseRelayHintsResponsePayload({
        'relayHints': [
          {'relayId': 'r1'}
        ],
        'expiresAt': '2025-01-01T00:00:00.000Z',
      });
      expect(payload.relayHints.length, 1);
    });
  });

  group('parseSystemSignalPayload', () {
    test('parses valid payload', () {
      final payload = parseSystemSignalPayload({
        'ownerId': 'envoy:owner:abc',
        'ownerPublicKeyPem': 'pem',
        'deviceId': 'envoy:device:xyz',
        'deviceCertificate': {'version': '0.1'},
        'deviceProfile': 'primary',
        'capabilities': ['mesh.listen'],
        'supportedProtocolVersions': ['0.1'],
      });
      expect(payload.ownerId, 'envoy:owner:abc');
    });
  });

  // ============================================
  // Full round-trip: construct → sign → parse → verify
  // ============================================

  group('full round-trip', () {
    test('construct chat.message, sign, parse back', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);

      // 1. Build unsigned envelope
      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.chatMessage,
        payload: createChatMessagePayload(
          senderOwnerId: deriveOwnerId(keys.publicKeyPem),
          text: 'Hello from Dart!',
        ).toJson(),
      ));

      // 2. Sign it
      final signature = await signCanonicalPayload(
        unsigned.toJson(),
        keys.privateKeyPem,
        keys.publicKeyPem,
      );

      // 3. Attach signature
      final signed = unsigned.sign(signature);

      // 4. Serialize to JSON
      final jsonStr = jsonEncode(signed.toJson());

      // 5. Parse back
      final parsed = parseEnvelope(jsonStr);
      expect(parsed.messageId, unsigned.messageId);
      expect(parsed.intent, EnvoyIntent.chatMessage);
      expect(parsed.senderPeerId, peerId);
      expect(parsed.signature, signature);

      // 6. Verify signature
      final unsignedForVerify = envelopeForSigning(parsed);
      final valid = await verifyCanonicalPayload(
        unsignedForVerify,
        parsed.signature,
        keys.publicKeyPem,
      );
      expect(valid, isTrue);

      // 7. Parse typed payload
      final chatPayload = parseChatMessagePayload(parsed.payload);
      expect(chatPayload.text, 'Hello from Dart!');
    });

    test('signature verification fails on tampered envelope', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);

      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: peerId,
        senderPublicKey: keys.publicKeyPem,
        intent: EnvoyIntent.chatMessage,
        payload: {'senderOwnerId': 'o', 'text': 'original'},
      ));

      final signature = await signCanonicalPayload(
        unsigned.toJson(),
        keys.privateKeyPem,
        keys.publicKeyPem,
      );

      final signed = unsigned.sign(signature);
      // Tamper with payload
      final tamperedJson = signed.toJson();
      (tamperedJson['payload'] as Map)['text'] = 'tampered';

      final unsignedForVerify = Map<String, dynamic>.from(tamperedJson);
      unsignedForVerify.remove('signature');

      final valid = await verifyCanonicalPayload(
        unsignedForVerify,
        signature,
        keys.publicKeyPem,
      );
      expect(valid, isFalse);
    });
  });
}
