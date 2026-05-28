import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/chat_history_store.dart';
import 'package:home_claw_app/envoy/envoy_identity.dart';
import 'package:home_claw_app/envoy/envoy_node_service.dart';
import 'package:home_claw_app/envoy/envoy_protocol.dart';
import 'package:home_claw_app/envoy/relay_client.dart';
import 'package:home_claw_app/providers/envoy_providers.dart';

/// Helper: build a valid signed chat.message envelope for test use.
Future<Map<String, dynamic>> _buildSignedChatEnvelope({
  required String text,
  String senderPeerId = 'envoy_sender123',
  String senderOwnerId = 'envoy:owner:sender',
  String recipientPeerId = 'envoy_mobile123',
  required String publicKeyPem,
  required String privateKeyPem,
}) async {
  final payload = createChatMessagePayload(
    senderOwnerId: senderOwnerId,
    text: text,
  );

  final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
    senderPeerId: senderPeerId,
    senderPublicKey: publicKeyPem,
    intent: EnvoyIntent.chatMessage,
    recipientPeerId: recipientPeerId,
    payload: payload.toJson(),
  ));

  final signature = await signCanonicalPayload(
    unsigned.toJson(),
    privateKeyPem,
    publicKeyPem,
  );

  return unsigned.sign(signature).toJson();
}

Future<Map<String, dynamic>> _buildSignedSystemPingEnvelope({
  required String text,
  String senderPeerId = 'envoy_sender123',
  String recipientPeerId = 'envoy_mobile123',
  required String publicKeyPem,
  required String privateKeyPem,
}) async {
  final payload = createSystemPingPayload(message: text);

  final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
    senderPeerId: senderPeerId,
    senderPublicKey: publicKeyPem,
    intent: EnvoyIntent.systemPing,
    recipientPeerId: recipientPeerId,
    payload: payload.toJson(),
  ));

  final signature = await signCanonicalPayload(
    unsigned.toJson(),
    privateKeyPem,
    publicKeyPem,
  );

  return unsigned.sign(signature).toJson();
}

void main() {
  // ============================================
  // EnvoyNodeService identity lifecycle
  // ============================================

  group('EnvoyNodeService identity', () {
    test('starts uninitialized', () {
      final service = EnvoyNodeService();
      expect(service.isInitialized, isFalse);
      expect(service.peerId, isNull);
      expect(service.ownerId, isNull);
      expect(service.publicKeyPem, isNull);
      expect(service.connectionState, RelayClientState.disconnected);
    });

    test('withKeys sets identity fields', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      expect(service.isInitialized, isTrue);
      expect(service.peerId, peerId);
      expect(service.ownerId, ownerId);
      expect(service.publicKeyPem, keys.publicKeyPem);
    });

    test('withKeys is disconnected by default', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      expect(service.connectionState, RelayClientState.disconnected);
      expect(service.homeNodeUrl, isNull);
    });
  });

  // ============================================
  // Connection lifecycle
  // ============================================

  group('connection lifecycle', () {
    test('connect throws StateError when not initialized', () async {
      final service = EnvoyNodeService();

      expect(
        () => service.connect('ws://localhost:3030/ws'),
        throwsStateError,
      );
    });

    test('withKeys allows setting up connection state', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      // Create a RelayClient in disconnected state with callbacks wired
      final client = RelayClient(
        url: 'ws://localhost:3030/ws',
        peerId: peerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
        ownerId: ownerId,
      );

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
        client: client,
      );

      // Connection state reflects the client's state
      expect(service.connectionState, RelayClientState.disconnected);
    });

    test('disconnect is safe when not connected', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      // Should not throw
      await service.disconnect();
      expect(service.connectionState, RelayClientState.disconnected);
    });
  });

  // ============================================
  // Messaging error guards
  // ============================================

  group('messaging error guards', () {
    test('sendChat throws StateError when not initialized', () async {
      final service = EnvoyNodeService();

      expect(
        () => service.sendChat('envoy_recipient', 'hello'),
        throwsStateError,
      );
    });

    test('sendChat throws StateError when not connected', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      expect(
        () => service.sendChat('envoy_recipient', 'hello'),
        throwsStateError,
      );
    });

    test('sendChatToOwner throws StateError when not connected', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      expect(
        () => service.sendChatToOwner('envoy_recipient', 'envoy:owner:recipient', 'hello'),
        throwsStateError,
      );
    });

    test('getNodeStatus throws StateError when not connected', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      expect(
        () => service.getNodeStatus(),
        throwsStateError,
      );
    });

    test('discoverBridgeAgent throws StateError when not connected', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      expect(
        () => service.discoverBridgeAgent(),
        throwsStateError,
      );
    });

    test('getBonds throws StateError when not connected', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      expect(
        () => service.getBonds(),
        throwsStateError,
      );
    });
  });

  // ============================================
  // Inbound envelope handling
  // ============================================

  group('inbound envelope handling', () {
    test('chat.message envelope emits on chatMessage stream', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      // Collect chat messages
      final messages = <EnvoyMeshChatMessage>[];
      final sub = service.onChatMessage.listen(messages.add);

      // Build a signed chat.message from a sender
      final senderKeys = await generateEd25519KeyPair();
      final envelopeJson = await _buildSignedChatEnvelope(
        text: 'Hello from peer!',
        senderPeerId: 'envoy_sender123',
        senderOwnerId: 'envoy:owner:sender',
        recipientPeerId: peerId,
        publicKeyPem: senderKeys.publicKeyPem,
        privateKeyPem: senderKeys.privateKeyPem,
      );

      service.handleTestEnvelope(envelopeJson, '');

      // Allow stream to deliver
      await Future.delayed(const Duration(milliseconds: 10));

      expect(messages.length, 1);
      expect(messages[0].text, 'Hello from peer!');
      expect(messages[0].senderPeerId, 'envoy_sender123');
      expect(messages[0].senderOwnerId, 'envoy:owner:sender');

      await sub.cancel();
    });

    test('system.ping envelope does NOT emit on chatMessage stream', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      final messages = <EnvoyMeshChatMessage>[];
      final sub = service.onChatMessage.listen(messages.add);

      final senderKeys = await generateEd25519KeyPair();
      final envelopeJson = await _buildSignedSystemPingEnvelope(
        text: 'ping!',
        senderPeerId: 'envoy_sender123',
        recipientPeerId: peerId,
        publicKeyPem: senderKeys.publicKeyPem,
        privateKeyPem: senderKeys.privateKeyPem,
      );

      service.handleTestEnvelope(envelopeJson, '');

      await Future.delayed(const Duration(milliseconds: 10));

      expect(messages, isEmpty);

      await sub.cancel();
    });

    test('correlationId is passed through to EmvoyMeshChatMessage', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      final messages = <EnvoyMeshChatMessage>[];
      final sub = service.onChatMessage.listen(messages.add);

      final senderKeys = await generateEd25519KeyPair();
      final senderPeerId = derivePeerId(senderKeys.publicKeyPem);

      // Build envelope with correlationId
      final payload = createChatMessagePayload(
        senderOwnerId: 'envoy:owner:sender',
        text: 'threaded reply',
      );

      final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
        senderPeerId: senderPeerId,
        senderPublicKey: senderKeys.publicKeyPem,
        intent: EnvoyIntent.chatMessage,
        recipientPeerId: peerId,
        payload: payload.toJson(),
        correlationId: 'corr_thread_42',
      ));

      final signature = await signCanonicalPayload(
        unsigned.toJson(),
        senderKeys.privateKeyPem,
        senderKeys.publicKeyPem,
      );

      final envelopeJson = unsigned.sign(signature).toJson();

      service.handleTestEnvelope(envelopeJson, '');

      await Future.delayed(const Duration(milliseconds: 10));

      expect(messages.length, 1);
      expect(messages[0].correlationId, 'corr_thread_42');

      await sub.cancel();
    });
  });

  // ============================================
  // Status change stream
  // ============================================

  group('status change stream', () {
    test('stream is a broadcast stream', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      // Should allow multiple listeners (broadcast)
      final sub1 = service.onStatusChange.listen((_) {});
      final sub2 = service.onStatusChange.listen((_) {});

      expect(sub1, isNotNull);
      expect(sub2, isNotNull);

      await sub1.cancel();
      await sub2.cancel();
    });
  });

  // ============================================
  // EnvoyMeshState
  // ============================================

  group('EnvoyMeshState', () {
    test('default state is disconnected and uninitialized', () {
      const state = EnvoyMeshState();
      expect(state.connectionStatus, RelayClientState.disconnected);
      expect(state.initialized, isFalse);
      expect(state.isConnected, isFalse);
      expect(state.peerId, isNull);
      expect(state.ownerId, isNull);
      expect(state.contacts, isEmpty);
    });

    test('copyWith preserves fields', () {
      const state = EnvoyMeshState(
        connectionStatus: RelayClientState.connected,
        peerId: 'envoy_abc',
        ownerId: 'envoy:owner:abc',
        initialized: true,
        homeNodeUrl: 'ws://localhost:3030/ws',
      );

      final copy = state.copyWith(connectionStatus: RelayClientState.disconnected);

      expect(copy.connectionStatus, RelayClientState.disconnected);
      expect(copy.peerId, 'envoy_abc');
      expect(copy.ownerId, 'envoy:owner:abc');
      expect(copy.initialized, isTrue);
      expect(copy.homeNodeUrl, 'ws://localhost:3030/ws');
    });

    test('copyWith clearError removes error', () {
      const state = EnvoyMeshState(error: 'something failed');
      final copy = state.copyWith(clearError: true);
      expect(copy.error, isNull);
    });

    test('isConnected returns true only when connected', () {
      expect(
        const EnvoyMeshState(connectionStatus: RelayClientState.connected).isConnected,
        isTrue,
      );
      expect(
        const EnvoyMeshState(connectionStatus: RelayClientState.disconnected).isConnected,
        isFalse,
      );
      expect(
        const EnvoyMeshState(connectionStatus: RelayClientState.connecting).isConnected,
        isFalse,
      );
      expect(
        const EnvoyMeshState(connectionStatus: RelayClientState.reconnectBackoff).isConnected,
        isFalse,
      );
      expect(
        const EnvoyMeshState(connectionStatus: RelayClientState.error).isConnected,
        isFalse,
      );
    });

    test('bridgeAgentContact returns agent contact', () {
      final bridgeAgent = EnvoyMeshContact(
        peerId: 'envoy_agent_abc',
        ownerId: null,
        displayName: 'My Agent',
        role: 'agent',
        kind: EnvoyMeshContactKind.bridgeAgent,
      );

      final state = EnvoyMeshState(contacts: [
        bridgeAgent,
        EnvoyMeshContact(
          peerId: 'envoy_peer1',
          ownerId: 'envoy:owner:peer1',
          displayName: 'Alice',
          role: 'human',
          kind: EnvoyMeshContactKind.bondedHuman,
        ),
      ]);

      expect(state.bridgeAgentContact, isNotNull);
      expect(state.bridgeAgentContact!.peerId, 'envoy_agent_abc');
    });

    test('bridgeAgentContact returns null when no agent', () {
      final state = EnvoyMeshState(contacts: [
        EnvoyMeshContact(
          peerId: 'envoy_peer1',
          ownerId: 'envoy:owner:peer1',
          displayName: 'Alice',
          role: 'human',
          kind: EnvoyMeshContactKind.bondedHuman,
        ),
      ]);

      expect(state.bridgeAgentContact, isNull);
    });

    test('humanContacts filters out agent contacts', () {
      final state = EnvoyMeshState(contacts: [
        EnvoyMeshContact(
          peerId: 'envoy_agent_abc',
          ownerId: null,
          displayName: 'My Agent',
          role: 'agent',
          kind: EnvoyMeshContactKind.bridgeAgent,
        ),
        EnvoyMeshContact(
          peerId: 'envoy_peer1',
          ownerId: 'envoy:owner:peer1',
          displayName: 'Alice',
          role: 'human',
          kind: EnvoyMeshContactKind.bondedHuman,
        ),
        EnvoyMeshContact(
          peerId: 'envoy_peer2',
          ownerId: 'envoy:owner:peer2',
          displayName: 'Bob',
          role: 'human',
          kind: EnvoyMeshContactKind.bondedHuman,
        ),
      ]);

      final humans = state.humanContacts;
      expect(humans.length, 2);
      expect(humans.every((c) => c.role == 'human'), isTrue);
    });
  });

  // ============================================
  // EnvoyMeshContact
  // ============================================

  group('EnvoyMeshContact', () {
    test('default role is human', () {
      const contact = EnvoyMeshContact(
        peerId: 'envoy_abc',
        ownerId: 'envoy:owner:abc',
        kind: EnvoyMeshContactKind.bondedHuman,
      );
      expect(contact.role, 'human');
    });

    test('agent role is stored', () {
      const contact = EnvoyMeshContact(
        peerId: 'envoy_agent_abc',
        ownerId: null,
        displayName: 'My Agent',
        role: 'agent',
        kind: EnvoyMeshContactKind.bridgeAgent,
      );
      expect(contact.role, 'agent');
    });

    test('toString includes displayName', () {
      const contact = EnvoyMeshContact(
        peerId: 'envoy_abc',
        ownerId: 'envoy:owner:abc',
        displayName: 'Alice',
        kind: EnvoyMeshContactKind.bondedHuman,
      );
      expect(contact.toString(), contains('Alice'));
    });
  });

  // ============================================
  // EnvoyMeshChatMessage
  // ============================================

  group('EnvoyMeshChatMessage', () {
    test('constructor sets all fields', () {
      const message = EnvoyMeshChatMessage(
        messageId: 'msg-1',
        senderPeerId: 'envoy_sender',
        senderOwnerId: 'envoy:owner:sender',
        correlationId: 'corr-1',
        text: 'Hello!',
        receivedAt: '2025-01-01T00:00:00.000Z',
      );

      expect(message.messageId, 'msg-1');
      expect(message.senderPeerId, 'envoy_sender');
      expect(message.senderOwnerId, 'envoy:owner:sender');
      expect(message.correlationId, 'corr-1');
      expect(message.text, 'Hello!');
      expect(message.receivedAt, '2025-01-01T00:00:00.000Z');
    });
  });

  // ============================================
  // Dispose
  // ============================================

  group('dispose', () {
    test('dispose releases resources', () async {
      final keys = await generateEd25519KeyPair();
      final peerId = derivePeerId(keys.publicKeyPem);
      final ownerId = deriveOwnerId(keys.publicKeyPem);

      final service = EnvoyNodeService.withKeys(
        peerId: peerId,
        ownerId: ownerId,
        publicKeyPem: keys.publicKeyPem,
        privateKeyPem: keys.privateKeyPem,
      );

      await service.dispose();

      // Should not throw (safe to call multiple times)
      await service.dispose();
    });
  });
}
