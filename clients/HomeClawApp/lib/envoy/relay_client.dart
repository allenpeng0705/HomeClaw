import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import 'envoy_identity.dart';
import 'envoy_protocol.dart';

/// Connection states for the relay client.
enum RelayClientState { disconnected, connecting, connected, error }

/// A WebSocket-based relay client that connects to an EnvoyMesh home node
/// and acts as a remote P2P peer with its own Ed25519 identity.
///
/// The home node acts as a P2P proxy — the Dart client signs envelopes with
/// its own keys, and the node forwards them into the libp2p mesh.
///
/// Protocol: JSON-RPC over WebSocket (same as the Social web UI).
class RelayClient {
  final String url;
  final String peerId;
  final String publicKeyPem;
  final String privateKeyPem;
  final String ownerId;

  WebSocketChannel? _channel;
  RelayClientState _state = RelayClientState.disconnected;
  StreamSubscription<dynamic>? _subscription;
  int _nextId = 1;
  final Map<String, Completer<Map<String, dynamic>>> _pending = {};
  Timer? _heartbeatTimer;
  Timer? _reconnectTimer;
  int _reconnectAttempts = 0;
  static const _maxReconnectAttempts = 5;
  static const _reconnectBaseMs = 500;

  /// Called when an inbound P2P envelope is received.
  final void Function(Map<String, dynamic> envelope, String remotePeerId)?
      onEnvelope;

  /// Called when the connection state changes.
  final void Function(RelayClientState state)? onStateChange;

  RelayClient({
    required this.url,
    required this.peerId,
    required this.publicKeyPem,
    required this.privateKeyPem,
    required this.ownerId,
    this.onEnvelope,
    this.onStateChange,
  });

  RelayClientState get state => _state;

  void _setState(RelayClientState newState) {
    if (_state != newState) {
      _state = newState;
      onStateChange?.call(_state);
    }
  }

  /// Connect to the home node's WebSocket.
  Future<void> connect() async {
    if (_state == RelayClientState.connecting ||
        _state == RelayClientState.connected) return;

    _setState(RelayClientState.connecting);
    _reconnectAttempts = 0;

    try {
      final uri = Uri.parse(url);
      _channel = WebSocketChannel.connect(uri);
      await _channel!.ready;

      _setState(RelayClientState.connected);
      _reconnectAttempts = 0;

      _subscription = _channel!.stream.listen(
        _handleMessage,
        onError: (error) {
          _handleDisconnect();
        },
        onDone: () {
          _handleDisconnect();
        },
      );

      _startHeartbeat();
    } catch (e) {
      _setState(RelayClientState.error);
      _scheduleReconnect();
    }
  }

  /// Disconnect and clean up.
  Future<void> disconnect() async {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _subscription?.cancel();
    _subscription = null;
    await _channel?.sink.close();
    _channel = null;
    // Fail all pending requests
    for (final c in _pending.values) {
      c.completeError('disconnected');
    }
    _pending.clear();
    _setState(RelayClientState.disconnected);
  }

  void _handleDisconnect() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _subscription?.cancel();
    _subscription = null;
    _channel = null;
    for (final c in _pending.values) {
      c.completeError('disconnected');
    }
    _pending.clear();
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (_reconnectAttempts >= _maxReconnectAttempts) {
      _setState(RelayClientState.error);
      return;
    }
    _setState(RelayClientState.connecting);
    final delay = _reconnectBaseMs * (1 << _reconnectAttempts);
    _reconnectAttempts++;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(Duration(milliseconds: delay), () {
      connect();
    });
  }

  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      _sendJson({'id': '_ping_${_nextId++}', 'method': 'getNodeStatus'});
    });
  }

  void _handleMessage(dynamic raw) {
    try {
      final msg = jsonDecode(raw as String) as Map<String, dynamic>;
      // Server push (event)
      if (msg.containsKey('event') && !msg.containsKey('id')) {
        final event = msg['event'] as String?;
        if (event == 'p2p:envelope') {
          final data = msg['data'] as Map<String, dynamic>?;
          if (data != null) {
            final env = data['envelope'] as Map<String, dynamic>?;
            final rpid = data['remotePeerId'] as String?;
            if (env != null) {
              onEnvelope?.call(env, rpid ?? '');
            }
          }
        }
        return;
      }

      // RPC response
      final id = msg['id'] as String?;
      if (id != null && _pending.containsKey(id)) {
        final completer = _pending.remove(id)!;
        if (msg.containsKey('error')) {
          completer.completeError(msg['error']);
        } else {
          completer.complete(msg);
        }
      }
    } catch (_) {
      // ignore parse errors for pings etc.
    }
  }

  void _sendJson(Map<String, dynamic> json) {
    if (_channel == null) return;
    _channel!.sink.add(jsonEncode(json));
  }

  /// Send a JSON-RPC request and wait for the response.
  Future<Map<String, dynamic>> _rpc(
    String method,
    Map<String, dynamic>? params,
  ) async {
    if (_channel == null) throw StateError('not connected');
    final id = 'rpc_${_nextId++}';
    final request = {'id': id, 'method': method, 'params': params ?? {}};
    final completer = Completer<Map<String, dynamic>>();
    _pending[id] = completer;
    _sendJson(request);
    return completer.future.timeout(
      const Duration(seconds: 30),
      onTimeout: () {
        _pending.remove(id);
        throw TimeoutException('RPC $method timed out');
      },
    );
  }

  // ============================================
  // Public API
  // ============================================

  /// Forward a pre-signed envelope into the P2P mesh.
  ///
  /// [envelope] is a signed [EnvoyEnvelope].
  /// [dialHints] are optional multiaddrs for the node to try when dialing.
  Future<void> forwardEnvelope(
    EnvoyEnvelope envelope, {
    List<String>? dialHints,
  }) async {
    await _rpc('forwardEnvelope', {
      'envelope': envelope.toJson(),
      if (dialHints != null && dialHints.isNotEmpty) 'dialHints': dialHints,
    });
  }

  /// Build, sign, and send a chat.message envelope through the relay.
  ///
  /// This is the primary method for sending chat messages from the mobile app.
  Future<String> sendChatMessage({
    required String recipientPeerId,
    required String text,
    String? correlationId,
  }) async {
    final payload = createChatMessagePayload(
      senderOwnerId: ownerId,
      text: text,
    );

    final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
      senderPeerId: peerId,
      senderPublicKey: publicKeyPem,
      intent: EnvoyIntent.chatMessage,
      recipientPeerId: recipientPeerId,
      payload: payload.toJson(),
      correlationId: correlationId,
    ));

    final signature = await signCanonicalPayload(
      unsigned.toJson(),
      privateKeyPem,
      publicKeyPem,
    );

    final signed = unsigned.sign(signature);

    await forwardEnvelope(signed);
    return signed.messageId;
  }

  /// Get the node's current status.
  Future<Map<String, dynamic>> getNodeStatus() async {
    return _rpc('getNodeStatus', null);
  }

  /// Get the node's configuration.
  Future<Map<String, dynamic>> getNodeConfig() async {
    return _rpc('getNodeConfig', null);
  }

  /// Get bonded contacts from the home node.
  ///
  /// Returns a list of bond records, each containing at minimum
  /// `peerOwnerId` and `displayName`.
  Future<List<Map<String, dynamic>>> getBonds() async {
    final result = await _rpc('getBonds', null);
    final bonds = result['result'] as List<dynamic>?;
    if (bonds == null) return [];
    return bonds.cast<Map<String, dynamic>>();
  }

  /// Build, sign, and send a device.pair.request envelope through the relay.
  ///
  /// Used by the mobile app after scanning the pairing QR code to request
  /// pairing with the bridge agent on the home node.
  Future<String> sendDevicePairRequest({
    required String recipientPeerId,
    required String requesterOwnerId,
    required String requesterDeviceId,
    required String requesterDevicePublicKeyPem,
    String? note,
  }) async {
    final payload = createDevicePairRequestPayload(
      requesterOwnerId: requesterOwnerId,
      requesterDeviceId: requesterDeviceId,
      requesterDevicePublicKeyPem: requesterDevicePublicKeyPem,
      note: note,
    );

    final unsigned = createUnsignedEnvelope(CreateEnvelopeInput(
      senderPeerId: peerId,
      senderPublicKey: publicKeyPem,
      intent: EnvoyIntent.devicePairRequest,
      recipientPeerId: recipientPeerId,
      payload: payload.toJson(),
    ));

    final signature = await signCanonicalPayload(
      unsigned.toJson(),
      privateKeyPem,
      publicKeyPem,
    );

    final signed = unsigned.sign(signature);
    await forwardEnvelope(signed);
    return signed.messageId;
  }
}
