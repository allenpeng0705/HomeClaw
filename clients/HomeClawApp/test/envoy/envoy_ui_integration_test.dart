import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/envoy/envoy_node_service.dart';
import 'package:home_claw_app/envoy/relay_client.dart';
import 'package:home_claw_app/providers/envoy_providers.dart';
import 'package:home_claw_app/providers/friend_list_providers.dart';

// ============================================
// EnvoyMeshNotifier state transitions
// ============================================

void main() {
  group('EnvoyMeshNotifier', () {
    test('initial state is disconnected and uninitialized', () {
      final notifier = EnvoyMeshNotifier();
      expect(notifier.state.initialized, isFalse);
      expect(notifier.state.isConnected, isFalse);
      expect(notifier.state.connectionStatus, RelayClientState.disconnected);
      expect(notifier.state.contacts, isEmpty);
    });

    test('setInitialized sets peer and owner IDs', () {
      final notifier = EnvoyMeshNotifier();
      notifier.setInitialized('envoy_abc123', 'envoy:owner:abc123');

      expect(notifier.state.initialized, isTrue);
      expect(notifier.state.peerId, 'envoy_abc123');
      expect(notifier.state.ownerId, 'envoy:owner:abc123');
      // Connection status unchanged
      expect(notifier.state.connectionStatus, RelayClientState.disconnected);
    });

    test('setConnectionStatus updates status', () {
      final notifier = EnvoyMeshNotifier();
      notifier.setConnectionStatus(RelayClientState.connecting);
      expect(notifier.state.connectionStatus, RelayClientState.connecting);
      expect(notifier.state.isConnected, isFalse);

      notifier.setConnectionStatus(RelayClientState.connected);
      expect(notifier.state.connectionStatus, RelayClientState.connected);
      expect(notifier.state.isConnected, isTrue);
    });

    test('setConnected sets URL and connected status', () {
      final notifier = EnvoyMeshNotifier();
      notifier.setConnected('ws://localhost:3030/ws');

      expect(notifier.state.connectionStatus, RelayClientState.connected);
      expect(notifier.state.isConnected, isTrue);
      expect(notifier.state.homeNodeUrl, 'ws://localhost:3030/ws');
    });

    test('setDisconnected changes status to disconnected', () {
      final notifier = EnvoyMeshNotifier();
      notifier.setConnected('ws://localhost:3030/ws');
      notifier.setDisconnected();

      expect(notifier.state.connectionStatus, RelayClientState.disconnected);
      expect(notifier.state.isConnected, isFalse);
    });

    test('setConnecting sets connecting status', () {
      final notifier = EnvoyMeshNotifier();
      notifier.setConnecting();

      expect(notifier.state.connectionStatus, RelayClientState.connecting);
      expect(notifier.state.isConnected, isFalse);
    });

    test('setError sets error status and message', () {
      final notifier = EnvoyMeshNotifier();
      notifier.setError('Connection refused');

      expect(notifier.state.connectionStatus, RelayClientState.error);
      expect(notifier.state.error, 'Connection refused');
      expect(notifier.state.isConnected, isFalse);
    });

    test('clearError removes error but preserves status', () {
      final notifier = EnvoyMeshNotifier();
      notifier.setError('Connection refused');
      notifier.clearError();

      expect(notifier.state.error, isNull);
      expect(notifier.state.connectionStatus, RelayClientState.error);
    });

    test('setContacts updates contacts and clears loading', () {
      final notifier = EnvoyMeshNotifier();
      notifier.setLoadingContacts(true);
      expect(notifier.state.loadingContacts, isTrue);

      final contacts = [
        const EnvoyMeshContact(
          peerId: 'envoy_peer1',
          ownerId: 'envoy:owner:peer1',
          displayName: 'Alice',
        ),
        const EnvoyMeshContact(
          peerId: 'envoy_agent_1',
          ownerId: 'envoy:owner:abc',
          displayName: 'My Agent',
          role: 'agent',
        ),
      ];
      notifier.setContacts(contacts);

      expect(notifier.state.contacts.length, 2);
      expect(notifier.state.loadingContacts, isFalse);
    });

    test('setLoadingContacts toggles loading state', () {
      final notifier = EnvoyMeshNotifier();
      notifier.setLoadingContacts(true);
      expect(notifier.state.loadingContacts, isTrue);

      notifier.setLoadingContacts(false);
      expect(notifier.state.loadingContacts, isFalse);
    });

    test('consecutive state transitions compose correctly', () {
      final notifier = EnvoyMeshNotifier();

      // Initialize
      notifier.setInitialized('envoy_abc', 'envoy:owner:abc');
      expect(notifier.state.initialized, isTrue);

      // Connect
      notifier.setConnecting();
      expect(notifier.state.connectionStatus, RelayClientState.connecting);

      notifier.setConnected('ws://home:3030/ws');
      expect(notifier.state.isConnected, isTrue);
      expect(notifier.state.homeNodeUrl, 'ws://home:3030/ws');

      // Load contacts
      notifier.setContacts([
        const EnvoyMeshContact(
          peerId: 'envoy_agent',
          ownerId: 'envoy:owner:abc',
          displayName: 'My Agent',
          role: 'agent',
        ),
      ]);
      expect(notifier.state.bridgeAgentContact, isNotNull);

      // Disconnect
      notifier.setDisconnected();
      expect(notifier.state.isConnected, isFalse);
      // Contacts and identity survive disconnect
      expect(notifier.state.contacts, isNotEmpty);
      expect(notifier.state.peerId, 'envoy_abc');
    });
  });

  // ============================================
  // P2P display list merging (FriendListScreen logic)
  // ============================================

  group('FriendList P2P contact merging', () {
    test('bridge agent is prepended when present', () {
      final friends = <FriendEntry>[
        FriendEntry(id: '1', name: 'HomeClaw', type: null, preset: null),
        FriendEntry(id: '2', name: 'Reminder', type: null, preset: 'reminder'),
      ];

      final bridge = const EnvoyMeshContact(
        peerId: 'envoy_agent_abc',
        ownerId: 'envoy:owner:abc',
        displayName: 'My Agent',
        role: 'agent',
      );

      final display = <FriendEntry>[];
      if (bridge != null) {
        display.add(FriendEntry(
          id: 'p2p_agent_${bridge.peerId}',
          name: bridge.displayName ?? 'My Agent',
          type: 'p2p_agent',
          userId: bridge.ownerId,
        ));
      }
      display.addAll(friends);

      expect(display.length, 3);
      expect(display[0].type, 'p2p_agent');
      expect(display[0].name, 'My Agent');
      expect(display[0].userId, 'envoy:owner:abc');
      expect(display[1].name, 'HomeClaw');
      expect(display[2].name, 'Reminder');
    });

    test('no bridge agent when not present', () {
      final friends = <FriendEntry>[
        FriendEntry(id: '1', name: 'HomeClaw', type: null, preset: null),
      ];

      const EnvoyMeshContact? bridge = null;

      final display = <FriendEntry>[];
      if (bridge != null) {
        display.add(FriendEntry(
          id: 'p2p_agent_${bridge.peerId}',
          name: bridge.displayName ?? 'My Agent',
          type: 'p2p_agent',
          userId: bridge.ownerId,
        ));
      }
      display.addAll(friends);

      expect(display.length, 1);
      expect(display[0].type, isNot('p2p_agent'));
    });

    test('bridge agent without displayName uses default', () {
      const bridge = EnvoyMeshContact(
        peerId: 'envoy_agent_xyz',
        ownerId: 'envoy:owner:xyz',
        role: 'agent',
      );

      final entry = FriendEntry(
        id: 'p2p_agent_${bridge.peerId}',
        name: bridge.displayName ?? 'My Agent',
        type: 'p2p_agent',
        userId: bridge.ownerId,
      );

      expect(entry.name, 'My Agent');
      expect(entry.id, 'p2p_agent_envoy_agent_xyz');
    });

    test('envoyMeshState bridgeAgentContact filters correctly', () {
      final state = EnvoyMeshState(contacts: [
        const EnvoyMeshContact(
          peerId: 'envoy_peer1',
          ownerId: 'envoy:owner:peer1',
          displayName: 'Alice',
          role: 'human',
        ),
        const EnvoyMeshContact(
          peerId: 'envoy_agent_1',
          ownerId: 'envoy:owner:abc',
          displayName: 'My Agent',
          role: 'agent',
        ),
        const EnvoyMeshContact(
          peerId: 'envoy_peer2',
          ownerId: 'envoy:owner:peer2',
          displayName: 'Bob',
          role: 'human',
        ),
      ]);

      final bridge = state.bridgeAgentContact;
      expect(bridge, isNotNull);
      expect(bridge!.peerId, 'envoy_agent_1');
      expect(bridge.role, 'agent');

      final humans = state.humanContacts;
      expect(humans.length, 2);
      expect(humans.every((c) => c.role == 'human'), isTrue);
    });
  });

  // ============================================
  // EnvoyMeshState computed properties
  // ============================================

  group('EnvoyMeshState computed', () {
    test('isConnected covers all states', () {
      expect(
        const EnvoyMeshState(connectionStatus: RelayClientState.connected)
            .isConnected,
        isTrue,
      );
      expect(
        const EnvoyMeshState(connectionStatus: RelayClientState.disconnected)
            .isConnected,
        isFalse,
      );
      expect(
        const EnvoyMeshState(connectionStatus: RelayClientState.connecting)
            .isConnected,
        isFalse,
      );
      expect(
        const EnvoyMeshState(connectionStatus: RelayClientState.error)
            .isConnected,
        isFalse,
      );
    });

    test('bridgeAgentContact returns null when only humans', () {
      final state = EnvoyMeshState(contacts: [
        const EnvoyMeshContact(
          peerId: 'envoy_peer1',
          ownerId: 'envoy:owner:peer1',
          displayName: 'Alice',
        ),
      ]);
      expect(state.bridgeAgentContact, isNull);
    });

    test('bridgeAgentContact returns null for empty contacts', () {
      const state = EnvoyMeshState();
      expect(state.bridgeAgentContact, isNull);
    });

    test('humanContacts is empty when only agent present', () {
      final state = EnvoyMeshState(contacts: [
        const EnvoyMeshContact(
          peerId: 'envoy_agent_1',
          ownerId: 'envoy:owner:abc',
          role: 'agent',
        ),
      ]);
      expect(state.humanContacts, isEmpty);
    });

    test('copyWith clearError removes error field', () {
      const state = EnvoyMeshState(error: 'something failed');
      final cleared = state.copyWith(clearError: true);
      expect(cleared.error, isNull);
    });

    test('copyWith preserves unspecified fields', () {
      const state = EnvoyMeshState(
        connectionStatus: RelayClientState.connected,
        peerId: 'envoy_abc',
        ownerId: 'envoy:owner:abc',
        initialized: true,
        homeNodeUrl: 'ws://localhost:3030/ws',
      );

      final copy = state.copyWith(connectionStatus: RelayClientState.error);
      expect(copy.connectionStatus, RelayClientState.error);
      expect(copy.peerId, 'envoy_abc');
      expect(copy.ownerId, 'envoy:owner:abc');
      expect(copy.initialized, isTrue);
      expect(copy.homeNodeUrl, 'ws://localhost:3030/ws');
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
      );
      expect(contact.role, 'human');
    });

    test('agent role is stored explicitly', () {
      const contact = EnvoyMeshContact(
        peerId: 'envoy_agent_abc',
        ownerId: 'envoy:owner:abc',
        displayName: 'My Agent',
        role: 'agent',
      );
      expect(contact.role, 'agent');
    });

    test('toString includes displayName', () {
      const contact = EnvoyMeshContact(
        peerId: 'envoy_abc',
        ownerId: 'envoy:owner:abc',
        displayName: 'Alice',
      );
      expect(contact.toString(), contains('Alice'));
    });

    test('toString for agent role', () {
      const contact = EnvoyMeshContact(
        peerId: 'envoy_agent_abc',
        ownerId: 'envoy:owner:abc',
        displayName: 'My Agent',
        role: 'agent',
      );
      expect(contact.toString(), contains('agent'));
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

    test('correlationId can be null', () {
      const message = EnvoyMeshChatMessage(
        messageId: 'msg-2',
        senderPeerId: 'envoy_sender',
        senderOwnerId: 'envoy:owner:sender',
        text: 'Hi',
        receivedAt: '2025-01-01T00:00:00.000Z',
      );

      expect(message.correlationId, isNull);
    });

    test('toString truncates long text', () {
      final longText = 'a' * 100;
      final message = EnvoyMeshChatMessage(
        messageId: 'msg-3',
        senderPeerId: 'envoy_sender',
        senderOwnerId: 'envoy:owner:sender',
        text: longText,
        receivedAt: '2025-01-01T00:00:00.000Z',
      );

      final str = message.toString();
      expect(str.length, lessThan(longText.length + 50));
      expect(str, contains('…'));
    });
  });
}
