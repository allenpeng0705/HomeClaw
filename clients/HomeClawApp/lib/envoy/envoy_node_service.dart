import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../chat_history_store.dart';
import 'envoy_identity.dart';
import 'envoy_protocol.dart';
import 'relay_client.dart';

// ============================================
// Data types
// ============================================

/// A contact discovered through the EnvoyMesh P2P mesh.
class EnvoyMeshContact {
  final String peerId;
  final String ownerId;
  final String? displayName;
  /// "human" or "agent"
  final String role;

  const EnvoyMeshContact({
    required this.peerId,
    required this.ownerId,
    this.displayName,
    this.role = 'human',
  });

  @override
  String toString() =>
      'EnvoyMeshContact(peerId: $peerId, displayName: $displayName, role: $role)';
}

/// A chat message received or sent through the P2P mesh.
class EnvoyMeshChatMessage {
  final String messageId;
  final String senderPeerId;
  final String senderOwnerId;
  final String? correlationId;
  final String text;
  final String receivedAt;

  const EnvoyMeshChatMessage({
    required this.messageId,
    required this.senderPeerId,
    required this.senderOwnerId,
    this.correlationId,
    required this.text,
    required this.receivedAt,
  });

  @override
  String toString() =>
      'EnvoyMeshChatMessage(from: $senderPeerId, text: "${text.length > 40 ? '${text.substring(0, 40)}…' : text}")';
}

// ============================================
// EnvoyNodeService
// ============================================

/// High-level service for EnvoyMesh P2P integration in the Flutter app.
///
/// Manages the Ed25519 identity, WebSocket connection to the home node
/// via [RelayClient], and exposes typed streams for inbound messages.
///
/// This is the primary API the Flutter UI uses for all P2P operations.
/// Follows the same pattern as [CoreService] — a service class that is
/// provided via Riverpod, not a StateNotifier itself.
///
/// Usage:
/// ```dart
/// final envoy = EnvoyNodeService();
/// await envoy.initialize();          // load or generate identity
/// await envoy.connect(homeNodeUrl);  // connect to home node
///
/// // Listen for incoming messages
/// envoy.onChatMessage.listen((msg) {
///   print('${msg.senderPeerId}: ${msg.text}');
/// });
///
/// // Send a message
/// await envoy.sendChat('envoy_agent_abc123', 'Hello!');
///
/// // Discover bridge agent
/// final bridge = await envoy.discoverBridgeAgent();
///
/// await envoy.dispose();
/// ```
class EnvoyNodeService {
  final FlutterSecureStorage _secureStorage;

  // ---- Storage keys ----
  static const _keyPublicKeyPem = 'envoy_public_key_pem';
  static const _keyPeerId = 'envoy_peer_id';
  static const _keyOwnerId = 'envoy_owner_id';
  static const _keyHomeNodeUrl = 'envoy_home_node_url';
  static const _keyPrivateKeyPem = 'envoy_private_key_pem';
  static const _keyPairedNodeInfo = 'envoy_paired_node_info';

  // ---- Loaded identity ----
  String? _peerId;
  String? _ownerId;
  String? _publicKeyPem;
  String? _privateKeyPem;

  // ---- Connection ----
  RelayClient? _client;

  // ---- Streams ----
  final _chatMessageController =
      StreamController<EnvoyMeshChatMessage>.broadcast();
  final _statusChangeController =
      StreamController<RelayClientState>.broadcast();

  EnvoyNodeService({FlutterSecureStorage? secureStorage})
      : _secureStorage = secureStorage ?? const FlutterSecureStorage();

  /// Test constructor: create a service with pre-loaded keys (no storage I/O).
  ///
  /// If [client] is provided it's used as the relay client; callbacks on
  /// the client must be wired by the caller if needed.
  @visibleForTesting
  EnvoyNodeService.withKeys({
    required String peerId,
    required String ownerId,
    required String publicKeyPem,
    required String privateKeyPem,
    RelayClient? client,
    FlutterSecureStorage? secureStorage,
  }) : _secureStorage = secureStorage ?? const FlutterSecureStorage(),
       _client = client {
    _peerId = peerId;
    _ownerId = ownerId;
    _publicKeyPem = publicKeyPem;
    _privateKeyPem = privateKeyPem;
  }

  /// Internal hook for tests to feed an inbound envelope through the
  /// handler and verify stream output.
  @visibleForTesting
  void handleTestEnvelope(
    Map<String, dynamic> envelopeJson,
    String remotePeerId,
  ) {
    _handleInboundEnvelope(envelopeJson, remotePeerId);
  }

  // ---- Public getters ----

  /// Own P2P peer ID (e.g. `envoy_abc123...`).
  String? get peerId => _peerId;

  /// Own owner ID (e.g. `envoy:owner:abc123...`).
  String? get ownerId => _ownerId;

  /// Own public key in PEM format.
  String? get publicKeyPem => _publicKeyPem;

  /// Whether [initialize] has completed and keys are loaded.
  bool get isInitialized => _peerId != null;

  /// Current WebSocket connection state.
  RelayClientState get connectionState =>
      _client?.state ?? RelayClientState.disconnected;

  /// The home node URL we're connected to, if any.
  String? get homeNodeUrl => _client?.url;

  /// Stream of typed chat messages received via P2P.
  Stream<EnvoyMeshChatMessage> get onChatMessage =>
      _chatMessageController.stream;

  /// Stream of RelayClient connection state changes.
  Stream<RelayClientState> get onStatusChange =>
      _statusChangeController.stream;

  // ============================================
  // Identity lifecycle
  // ============================================

  /// Load existing identity from storage, or generate a new one if none
  /// exists.
  ///
  /// Call once at app startup (like [CoreService.loadSettings]).
  /// After this returns, [isInitialized] is true.
  ///
  /// Idempotent: if keys are already loaded, does nothing.
  Future<void> initialize() async {
    if (isInitialized) return;

    final prefs = await SharedPreferences.getInstance();

    var publicKeyPem = prefs.getString(_keyPublicKeyPem);
    var privateKeyPem = await _secureStorage.read(key: _keyPrivateKeyPem);

    if (publicKeyPem == null ||
        publicKeyPem.isEmpty ||
        privateKeyPem == null ||
        privateKeyPem.isEmpty) {
      final keys = await generateEd25519KeyPair();
      publicKeyPem = keys.publicKeyPem;
      privateKeyPem = keys.privateKeyPem;

      await _secureStorage.write(key: _keyPrivateKeyPem, value: privateKeyPem);
      await prefs.setString(_keyPublicKeyPem, publicKeyPem);
    }

    _publicKeyPem = publicKeyPem;
    _privateKeyPem = privateKeyPem;
    _peerId = derivePeerId(publicKeyPem);
    _ownerId = deriveOwnerId(publicKeyPem);

    await prefs.setString(_keyPeerId, _peerId!);
    await prefs.setString(_keyOwnerId, _ownerId!);
  }

  // ============================================
  // Connection lifecycle
  // ============================================

  /// Connect to the home node's WebSocket relay.
  ///
  /// [homeNodeUrl] is the WebSocket URL (e.g. `ws://192.168.1.100:3030/ws`).
  /// Must call [initialize] first.
  ///
  /// If already connected, disconnects first then reconnects to the new URL.
  Future<void> connect(String homeNodeUrl) async {
    if (!isInitialized) {
      throw StateError('EnvoyNodeService not initialized — call initialize() first');
    }

    await disconnect();

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyHomeNodeUrl, homeNodeUrl);

    _client = RelayClient(
      url: homeNodeUrl,
      peerId: _peerId!,
      publicKeyPem: _publicKeyPem!,
      privateKeyPem: _privateKeyPem!,
      ownerId: _ownerId!,
      onEnvelope: _handleInboundEnvelope,
      onStateChange: (state) {
        _statusChangeController.add(state);
      },
    );

    await _client!.connect();
  }

  /// Disconnect from the home node and clean up.
  ///
  /// Safe to call when already disconnected.
  Future<void> disconnect() async {
    await _client?.disconnect();
    _client = null;
  }

  /// Get the last-used home node URL from storage, if any.
  Future<String?> getSavedHomeNodeUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_keyHomeNodeUrl);
  }

  // ============================================
  // Pairing (Phase 10A.6)
  // ============================================

  /// Save the paired node info from a scanned QR code.
  ///
  /// Persists to SharedPreferences so the bridge agent is remembered
  /// across app restarts.
  Future<void> savePairedNodeInfo(PairingPayload payload) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyPairedNodeInfo, jsonEncode({
      'wsUrl': payload.wsUrl,
      if (payload.relayPeerId != null) 'relayPeerId': payload.relayPeerId,
      if (payload.agentPeerId != null) 'agentPeerId': payload.agentPeerId,
      if (payload.agentPubKey != null) 'agentPubKey': payload.agentPubKey,
      if (payload.token != null) 'token': payload.token,
    }));
  }

  /// Load the paired node info from storage, if any.
  Future<PairingPayload?> getPairedNodeInfo() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_keyPairedNodeInfo);
    if (raw == null || raw.isEmpty) return null;
    try {
      final map = jsonDecode(raw) as Map<String, dynamic>;
      final wsUrl = map['wsUrl'] as String?;
      if (wsUrl == null || wsUrl.isEmpty) return null;
      return PairingPayload(
        wsUrl: wsUrl,
        relayPeerId: map['relayPeerId'] as String?,
        agentPeerId: map['agentPeerId'] as String?,
        agentPubKey: map['agentPubKey'] as String?,
        token: map['token'] as String?,
      );
    } catch (_) {
      return null;
    }
  }

  /// Send a device.pair.request to the bridge agent after scanning the
  /// pairing QR code.
  ///
  /// Must be connected. [agentPeerId] comes from the QR's `agentPeerId`
  /// field. The request includes our peer ID, owner ID, and public key
  /// so the home node can verify we're the same owner's device.
  Future<String> sendDevicePairRequest(
    String agentPeerId, {
    String? note,
    String? pairingToken,
  }) async {
    _requireConnected();
    return _client!.sendDevicePairRequest(
      recipientPeerId: agentPeerId,
      requesterOwnerId: _ownerId!,
      requesterDeviceId: _peerId!,
      requesterDevicePublicKeyPem: _publicKeyPem!,
      note: note,
    );
  }

  // ============================================
  // Messaging
  // ============================================

  /// Send a chat message to a P2P peer through the relay.
  ///
  /// [recipientPeerId] is the recipient's P2P peer ID.
  /// Returns the envelope [messageId].
  /// Throws [StateError] if not connected.
  ///
  /// The message is automatically persisted to [ChatHistoryStore] using
  /// [ownerId] as the user key and [recipientPeerId] as the friend key.
  Future<String> sendChat(String recipientPeerId, String text) async {
    _requireConnected();

    final messageId = await _client!.sendChatMessage(
      recipientPeerId: recipientPeerId,
      text: text,
    );

    // Persist outbound message to chat history
    try {
      await ChatHistoryStore().appendMessage(
        _ownerId!,
        recipientPeerId,
        text,
        true, // isUser = true (sent by us)
      );
    } catch (_) {}

    return messageId;
  }

  /// Send a chat message using owner IDs for chat history storage.
  ///
  /// Like [sendChat] but uses [recipientOwnerId] as the friend key for
  /// [ChatHistoryStore]. Use this when the contact is stored by owner ID
  /// rather than peer ID.
  Future<String> sendChatToOwner(
    String recipientPeerId,
    String recipientOwnerId,
    String text,
  ) async {
    _requireConnected();

    final messageId = await _client!.sendChatMessage(
      recipientPeerId: recipientPeerId,
      text: text,
    );

    try {
      await ChatHistoryStore().appendMessage(
        _ownerId!,
        recipientOwnerId,
        text,
        true,
      );
    } catch (_) {}

    return messageId;
  }

  // ============================================
  // Discovery
  // ============================================

  /// Get the home node's current status.
  Future<Map<String, dynamic>> getNodeStatus() async {
    _requireConnected();
    return _client!.getNodeStatus();
  }

  /// Get the home node's configuration.
  Future<Map<String, dynamic>> getNodeConfig() async {
    _requireConnected();
    return _client!.getNodeConfig();
  }

  /// Discover the bridge agent from the home node config.
  ///
  /// The bridge agent is the HomeClaw Core AI exposed as a P2P peer on the
  /// mesh. Returns null if the bridge is not enabled on the home node.
  Future<EnvoyMeshContact?> discoverBridgeAgent() async {
    _requireConnected();

    final config = await _client!.getNodeConfig();
    final bridge = config['bridgeStatus'] as Map<String, dynamic>?;
    if (bridge == null || bridge['enabled'] != true) return null;

    final agentPeerId = bridge['agentPeerId'] as String?;
    if (agentPeerId == null || agentPeerId.isEmpty) return null;

    return EnvoyMeshContact(
      peerId: agentPeerId,
      ownerId: _ownerId!,
      displayName: 'My Agent',
      role: 'agent',
    );
  }

  /// Get bonded contacts from the home node.
  ///
  /// Calls `getBonds` JSON-RPC and converts each bond to an
  /// [EnvoyMeshContact].
  Future<List<EnvoyMeshContact>> getBonds() async {
    _requireConnected();

    try {
      final bonds = await _client!.getBonds();
      return bonds.map((bond) {
        return EnvoyMeshContact(
          peerId: (bond['peerOwnerId'] as String?) ?? '',
          ownerId: (bond['peerOwnerId'] as String?) ?? '',
          displayName: bond['displayName'] as String?,
          role: 'human',
        );
      }).where((c) => c.peerId.isNotEmpty).toList();
    } catch (_) {
      return [];
    }
  }

  // ============================================
  // Internal
  // ============================================

  void _requireConnected() {
    if (_client == null || _client!.state != RelayClientState.connected) {
      throw StateError('not connected');
    }
  }

  void _handleInboundEnvelope(
    Map<String, dynamic> envelopeJson,
    String remotePeerId,
  ) {
    try {
      final envelope = parseEnvelope(envelopeJson);
      if (envelope.intent != EnvoyIntent.chatMessage) return;

      final chatPayload = parseChatMessagePayload(envelope.payload);

      final message = EnvoyMeshChatMessage(
        messageId: envelope.messageId,
        senderPeerId: envelope.senderPeerId,
        senderOwnerId: chatPayload.senderOwnerId,
        correlationId: envelope.correlationId,
        text: chatPayload.text,
        receivedAt: DateTime.now().toUtc().toIso8601String(),
      );

      _chatMessageController.add(message);

      // Persist inbound message to chat history
      try {
        ChatHistoryStore().appendMessage(
          _ownerId!,
          envelope.senderPeerId,
          chatPayload.text,
          false, // isUser = false (received)
        );
      } catch (_) {}
    } catch (_) {
      // Ignore parse errors for non-chat envelopes
    }
  }

  // ============================================
  // Cleanup
  // ============================================

  /// Release all resources.
  ///
  /// Call when the app is shutting down or the EnvoyNodeService is no
  /// longer needed. Safe to call multiple times.
  Future<void> dispose() async {
    await disconnect();
    // Don't await — controllers may be in a bad state
    try {
      await _chatMessageController.close();
    } catch (_) {}
    try {
      await _statusChangeController.close();
    } catch (_) {}
  }
}
