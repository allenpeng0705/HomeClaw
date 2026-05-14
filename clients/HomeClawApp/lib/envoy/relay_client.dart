import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import 'envoy_identity.dart';
import 'envoy_protocol.dart';
import 'relay_transport.dart';

/// Max time to wait for the WebSocket handshake to complete.
const Duration kRelayConnectTimeout = Duration(seconds: 10);

String? _trimOrNull(String? s) {
  final t = s?.trim();
  if (t == null || t.isEmpty) return null;
  return t;
}

/// Closing a stuck socket can hang forever on some platforms; never await unbounded.
const Duration kRelaySinkCloseTimeout = Duration(seconds: 2);

/// Base delay in ms for [RelayClient] reconnect backoff.
const int kRelayReconnectBaseMs = 500;

/// Max reconnect attempts before error state.
const int kRelayReconnectMaxAttempts = 5;

/// Reconnect delay for attempt index `0..n-1` (same formula as [RelayClient._scheduleReconnect]).
int relayReconnectDelayMs(int attemptIndex) {
  final i = attemptIndex < 0 ? 0 : attemptIndex;
  return kRelayReconnectBaseMs * (1 << i);
}

/// WebSocket payloads may arrive as UTF-8 [List<int>] (not only [String]); return JSON text or null.
String? relayDecodeWsText(dynamic raw) {
  if (raw is String) {
    final t = raw.trim();
    return t.isEmpty ? null : t;
  }
  if (raw is List<int>) {
    try {
      final t = utf8.decode(raw, allowMalformed: false).trim();
      return t.isEmpty ? null : t;
    } catch (_) {
      return null;
    }
  }
  return null;
}

/// Normalize JSON-RPC `id` for pending lookup ([int], [double] 1.0, [String] "42", etc.).
String relayWireCorrKey(dynamic idRaw) {
  if (idRaw == null) return '';
  if (idRaw is int) return '$idRaw';
  if (idRaw is double) {
    final d = idRaw;
    if (d.isFinite && d == d.roundToDouble()) {
      return d.toInt().toString();
    }
    return d.toString();
  }
  if (idRaw is num) {
    final d = idRaw.toDouble();
    if (d.isFinite && d == d.roundToDouble()) return d.toInt().toString();
    return '$idRaw';
  }
  return idRaw.toString();
}

/// Handles one server push frame (`event` without JSON-RPC `id`).
///
/// Exposed for unit tests; [RelayClient] calls this from [_handleMessage].
void relayDispatchServerPush(
  Map<String, dynamic> msg, {
  void Function(Map<String, dynamic> envelope, String remotePeerId)? onEnvelope,
  void Function(Map<String, dynamic> data)? onBridgeStatus,
}) {
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
  } else if (event == 'bridge:status') {
    final raw = msg['data'];
    if (raw is Map<String, dynamic>) {
      onBridgeStatus?.call(raw);
    } else if (raw is Map) {
      onBridgeStatus?.call(Map<String, dynamic>.from(raw));
    }
  }
}

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
  /// Monotonic JSON-RPC correlation id sent on the wire (integer; relays often coerce ids).
  int _nextRpcId = 1;
  final Map<String, Completer<dynamic>> _pending = {};
  Timer? _heartbeatTimer;
  Timer? _reconnectTimer;
  int _reconnectAttempts = 0;

  /// Set by [EnvoyNodeService] after JSON-RPC probes succeed ([enablePeriodicKeepalive]).
  bool _wantKeepalive = false;
  /// First RPC method that answered during [assertRelayHealthy]; used for heartbeat.
  String _keepaliveRpcMethod = 'getNodeStatus';
  /// Exact `params` shape that succeeded in [assertRelayHealthy] (`null` = omit).
  Map<String, dynamic>? _keepaliveRpcParams;

  /// Optional HTTP headers for the WebSocket upgrade (e.g. pairing token via
  /// Authorization). Ignored on web; reconnect reuses these headers.
  final Map<String, dynamic>? connectHeaders;

  /// When pairing supplies `pairingProbeToken` at construction time, [assertRelayHealthy]
  /// tries `"params": {"token": …}`, then `peerId`/`target` + token maps, before omitting `params`.
  final String? _pairingProbeToken;
  /// Relay peer id from the pairing QR (`relayPeerId`); included in some RPC probe param shapes.
  final String? _pairingRelayPeerId;

  /// Called when an inbound P2P envelope is received.
  final void Function(Map<String, dynamic> envelope, String remotePeerId)?
      onEnvelope;

  /// Called when the connection state changes.
  final void Function(RelayClientState state)? onStateChange;

  /// Called when the home node pushes `bridge:status` (bridge enabled/disabled, etc.).
  final void Function(Map<String, dynamic> data)? onBridgeStatus;

  RelayClient({
    required this.url,
    required this.peerId,
    required this.publicKeyPem,
    required this.privateKeyPem,
    required this.ownerId,
    Map<String, dynamic>? connectHeaders,
    String? pairingProbeToken,
    String? pairingRelayPeerId,
    this.onEnvelope,
    this.onStateChange,
    this.onBridgeStatus,
  })  : connectHeaders = (connectHeaders == null || connectHeaders.isEmpty)
            ? null
            : Map<String, dynamic>.from(connectHeaders),
        _pairingProbeToken = _trimOrNull(pairingProbeToken),
        _pairingRelayPeerId = _trimOrNull(pairingRelayPeerId);

  RelayClientState get state => _state;

  void _setState(RelayClientState newState) {
    if (_state != newState) {
      _state = newState;
      onStateChange?.call(_state);
    }
  }

  /// Connect to the home node's WebSocket.
  ///
  /// On handshake or protocol errors throws so callers (e.g. pairing) can
  /// surface a real failure. Automatic reconnect runs only after a connection
  /// was established and later dropped ([_handleDisconnect]).
  Future<void> connect() async {
    if (_state == RelayClientState.connected) return;

    _setState(RelayClientState.connecting);

    WebSocketChannel? ch;
    try {
      final uri = Uri.parse(url);
      ch = openRelayTransport(
        uri,
        handshakeTimeout: kRelayConnectTimeout,
        headers: connectHeaders,
      );
      _channel = ch;
      await _channel!.ready.timeout(kRelayConnectTimeout);

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

      if (_wantKeepalive) _startHeartbeat();
    } catch (e, st) {
      _heartbeatTimer?.cancel();
      _heartbeatTimer = null;
      _subscription?.cancel();
      _subscription = null;
      try {
        final s = ch?.sink;
        if (s != null) {
          try {
            await s.close().timeout(kRelaySinkCloseTimeout);
          } catch (_) {}
        }
      } catch (_) {}
      _channel = null;
      _setState(RelayClientState.error);
      Error.throwWithStackTrace(e, st);
    }
  }

  /// Disconnect and clean up.
  Future<void> disconnect() async {
    _wantKeepalive = false;
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _subscription?.cancel();
    _subscription = null;
    final sink = _channel?.sink;
    _channel = null;
    if (sink != null) {
      try {
        await sink.close().timeout(kRelaySinkCloseTimeout);
      } catch (_) {}
    }
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
    final sink = _channel?.sink;
    _channel = null;
    if (sink != null) {
      unawaited(
        sink.close().timeout(kRelaySinkCloseTimeout).catchError((_) {}),
      );
    }
    for (final c in _pending.values) {
      c.completeError('disconnected');
    }
    _pending.clear();
    // Do not reconnect until [enablePeriodicKeepalive] pairs the relay; otherwise
    // a timer-fired [connect] races with [assertRelayHealthy] on the same client.
    if (!_wantKeepalive) {
      _reconnectTimer?.cancel();
      _reconnectTimer = null;
      _setState(RelayClientState.disconnected);
      return;
    }
    _scheduleReconnect();
  }

  /// JSON-RPC 2.0 envelope (matches Social / home-node relay expectations).
  Map<String, dynamic> _jsonRpcRequest({
    required Object id,
    required String method,
    Map<String, dynamic>? params,
  }) {
    final m = <String, dynamic>{
      'jsonrpc': '2.0',
      'id': id,
      'method': method,
    };
    // `null`: omit params (legacy-friendly). `{}`: send `"params": {}` for strict parsers.
    if (params != null) {
      m['params'] = params;
    }
    return m;
  }

  /// True when wire error looks like JSON-RPC `-32601` method not found.
  static bool _looksLikeRpcMethodNotFound(Object e) {
    if (e is TimeoutException) return false;
    final s = e.toString().toLowerCase();
    return s.contains('32601') ||
        s.contains('method not found') ||
        s.contains('unknown method') ||
        s.contains('procedure not found');
  }

  static bool _looksLikeDisconnect(Object e) =>
      e == 'disconnected' || e.toString().contains('disconnected');

  static bool _looksLikeRpcNotConnected(Object e) =>
      e is StateError && e.message.contains('not connected');

  List<Map<String, dynamic>?> _relayProbeParamVariants() {
    final t = _pairingProbeToken;
    final pid = _pairingRelayPeerId;
    final v = <Map<String, dynamic>?>[<String, dynamic>{}];
    if (t != null) {
      v.add(<String, dynamic>{'token': t});
      if (pid != null) {
        v.add(<String, dynamic>{'peerId': pid, 'token': t});
        v.add(<String, dynamic>{'target': pid, 'token': t});
      }
    }
    v.add(null);
    return v;
  }

  /// Methods tried in order so pairing works across relay naming variants / versions.
  static const List<String> kRelayHealthyProbeMethods = [
    'getNodeStatus',
    'get_node_status',
    'relay.getSummary',
    'relay.summary',
    'getSummary',
    'get_summary',
    'getNodeConfig',
    'get_node_config',
    'getBonds',
    'get_bonds',
  ];

  static Map<String, dynamic> relayProbePayloadAsStatusMap(dynamic r,
      String method) {
    if (r is Map<String, dynamic>) return r;
    if (r is Map) return Map<String, dynamic>.from(r);
    if (r is List) {
      return {'probeMethod': method, 'relayBondProbe': true, 'bonds': r};
    }
    return {'probeMethod': method, 'relayProbeOk': true, if (r != null) 'value': r};
  }

  /// After connect: confirm relay speaks JSON-RPC and pick a heartbeat method that exists.
  Future<Map<String, dynamic>> assertRelayHealthy() async {
    Object? last;
    final variants = _relayProbeParamVariants();
    outer:
    for (final meth in kRelayHealthyProbeMethods) {
      for (var pi = 0; pi < variants.length; pi++) {
        final pv = variants[pi];
        try {
          final r = await _rpc(meth, pv);
          _keepaliveRpcMethod = meth;
          _keepaliveRpcParams =
              pv == null ? null : Map<String, dynamic>.from(pv);
          return relayProbePayloadAsStatusMap(r, meth);
        } catch (e, st) {
          last = e;
          if (_looksLikeRpcMethodNotFound(e)) continue outer;
          // Relay dropped socket (or `_channel` cleared) mid-probe; next param style needs a fresh WS.
          final hasMoreParamStyles = pi + 1 < variants.length;
          if (hasMoreParamStyles &&
              (_looksLikeDisconnect(e) || _looksLikeRpcNotConnected(e))) {
            try {
              await connect();
            } catch (_) {
              Error.throwWithStackTrace(e, st);
            }
            continue;
          }
          Error.throwWithStackTrace(e, st);
        }
      }
    }
    throw StateError(
      'Envoy relay: no RPC probe succeeded (tried '
      '${kRelayHealthyProbeMethods.join(", ")}): $last',
    );
  }

  /// Enables [Timer.periodic] JSON-RPC pings using the method that passed [assertRelayHealthy].
  void enablePeriodicKeepalive() {
    _wantKeepalive = true;
    if (_state == RelayClientState.connected) _startHeartbeat();
  }

  static Object _normalizeRpcError(Object err) {
    if (err is Map) {
      final code = err['code'];
      final message = err['message'];
      final data = err['data'];
      if (message is String && message.isNotEmpty) {
        if (code != null) {
          return 'RPC error $code: $message${data != null ? ' ($data)' : ''}';
        }
        return message;
      }
      try {
        return jsonEncode(err);
      } catch (_) {
        return err.toString();
      }
    }
    return err;
  }

  void _scheduleReconnect() {
    if (_reconnectAttempts >= kRelayReconnectMaxAttempts) {
      _setState(RelayClientState.error);
      return;
    }
    _setState(RelayClientState.connecting);
    final delay = kRelayReconnectBaseMs * (1 << _reconnectAttempts);
    _reconnectAttempts++;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(Duration(milliseconds: delay), () {
      connect();
    });
  }

  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      final idStr = '${_nextRpcId++}';
      _sendJson(_jsonRpcRequest(
        id: idStr,
        method: _keepaliveRpcMethod,
        params: _keepaliveRpcParams,
      ));
    });
  }

  void _dispatchOneDecoded(dynamic decoded) {
    if (decoded is List) {
      for (final e in decoded) {
        _dispatchOneDecoded(e);
      }
      return;
    }
    if (decoded is Map<String, dynamic>) {
      _dispatchDecodedMap(decoded);
      return;
    }
    if (decoded is Map) {
      _dispatchDecodedMap(Map<String, dynamic>.from(decoded));
      return;
    }
  }

  void _dispatchDecodedMap(Map<String, dynamic> msg) {
    dynamic dynId(String k) => msg[k];

    final corr =
        dynId('id') ??
        dynId('msgId') ??
        dynId('rpcId') ??
        dynId('requestId') ??
        dynId('replyId');
    final corrKey = corr == null ? '' : relayWireCorrKey(corr);
    final isLegacyEventPush = msg.containsKey('event') &&
        corr == null &&
        !msg.containsKey('jsonrpc');
    if (isLegacyEventPush) {
      relayDispatchServerPush(
        msg,
        onEnvelope: onEnvelope,
        onBridgeStatus: onBridgeStatus,
      );
      return;
    }

    if (corrKey.isEmpty || !_pending.containsKey(corrKey)) {
      return;
    }
    final completer = _pending.remove(corrKey)!;
    if (msg.containsKey('error') && msg['error'] != null) {
      completer.completeError(
        _normalizeRpcError(msg['error'] as Object),
      );
    } else if (msg.containsKey('result')) {
      completer.complete(msg['result']);
    } else if (msg.containsKey('payload')) {
      completer.complete(msg['payload']);
    } else {
      completer.complete(null);
    }
  }

  void _handleMessage(dynamic raw) {
    try {
      final text = relayDecodeWsText(raw);
      if (text == null) return;
      dynamic decoded = jsonDecode(text);
      _dispatchOneDecoded(decoded);
    } catch (_) {
      // ignore parse errors for pings etc.
    }
  }

  void _sendJson(Map<String, dynamic> json) {
    if (_channel == null) return;
    _channel!.sink.add(jsonEncode(json));
  }

  /// Send a JSON-RPC request and wait for the response.
  ///
  /// Returns the JSON-RPC `result` field (unwrapped), which may be a map,
  /// list, null, etc., depending on the method.
  Future<dynamic> _rpc(
    String method,
    Map<String, dynamic>? params,
  ) async {
    if (_channel == null) throw StateError('not connected');
    // String wire ids: some home-node relays reject numeric JSON-RPC `id` values.
    final idStr = '${_nextRpcId++}';
    final corr = relayWireCorrKey(idStr);
    final request = _jsonRpcRequest(id: idStr, method: method, params: params);
    final completer = Completer<dynamic>();
    _pending[corr] = completer;
    _sendJson(request);
    return completer.future.timeout(
      const Duration(seconds: 30),
      onTimeout: () {
        _pending.remove(corr);
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
    final params = <String, dynamic>{
      'envelope': envelope.toJson(),
      if (dialHints != null && dialHints.isNotEmpty) 'dialHints': dialHints,
    };
    try {
      await _rpc('forwardEnvelope', params);
      return;
    } catch (e) {
      if (!_looksLikeRpcMethodNotFound(e)) rethrow;
    }
    await _rpc('forward_envelope', params);
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

  /// Same fields as embedded in [getNodeConfig] when bridge is enabled.
  Future<Map<String, dynamic>> getBridgeStatus() async {
    try {
      final r = await _rpc('getBridgeStatus', null);
      if (r is Map<String, dynamic>) return r;
      if (r is Map) return Map<String, dynamic>.from(r);
      throw StateError('getBridgeStatus: unexpected result type ${r.runtimeType}');
    } catch (e) {
      if (!_looksLikeRpcMethodNotFound(e)) rethrow;
    }
    final r = await _rpc('get_bridge_status', null);
    if (r is Map<String, dynamic>) return r;
    if (r is Map) return Map<String, dynamic>.from(r);
    throw StateError(
      'getBridgeStatus (get_bridge_status): unexpected result type ${r.runtimeType}',
    );
  }

  /// Get the node's current status.
  ///
  /// Tries camelCase and snake_case method names exposed by different relays.
  Future<Map<String, dynamic>> getNodeStatus() async {
    const methods = [
      'getNodeStatus',
      'get_node_status',
      'relay.getSummary',
      'relay.summary',
      'getSummary',
      'get_summary',
    ];
    Object? last;
    for (final meth in methods) {
      try {
        final r = await _rpc(meth, null);
        if (r is Map<String, dynamic>) return r;
        if (r is Map) return Map<String, dynamic>.from(r);
        throw StateError(
          'getNodeStatus: unexpected result type ${r.runtimeType}',
        );
      } catch (e) {
        last = e;
        if (_looksLikeRpcMethodNotFound(e)) continue;
        rethrow;
      }
    }
    throw StateError('getNodeStatus: no method succeeded (${last ?? 'unknown'})');
  }

  /// Get the node's configuration.
  Future<Map<String, dynamic>> getNodeConfig() async {
    try {
      final r = await _rpc('getNodeConfig', null);
      if (r is Map<String, dynamic>) return r;
      if (r is Map) return Map<String, dynamic>.from(r);
      throw StateError('getNodeConfig: unexpected result type ${r.runtimeType}');
    } catch (e) {
      if (!_looksLikeRpcMethodNotFound(e)) rethrow;
    }
    final r = await _rpc('get_node_config', null);
    if (r is Map<String, dynamic>) return r;
    if (r is Map) return Map<String, dynamic>.from(r);
    throw StateError(
      'getNodeConfig (get_node_config): unexpected result type ${r.runtimeType}',
    );
  }

  /// Get bonded contacts from the home node.
  ///
  /// Returns a list of bond records, each containing at minimum
  /// `peerOwnerId` and `displayName`.
  Future<List<Map<String, dynamic>>> getBonds() async {
    dynamic r;
    try {
      r = await _rpc('getBonds', null);
      return _normalizeBondsResult(r);
    } catch (e) {
      if (!_looksLikeRpcMethodNotFound(e)) rethrow;
    }
    r = await _rpc('get_bonds', null);
    return _normalizeBondsResult(r);
  }

  List<Map<String, dynamic>> _normalizeBondsResult(dynamic r) {
    if (r is! List) return [];
    final out = <Map<String, dynamic>>[];
    for (final e in r) {
      if (e is Map<String, dynamic>) {
        out.add(e);
      } else if (e is Map) {
        out.add(Map<String, dynamic>.from(e));
      }
    }
    return out;
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
    String? pairingToken,
  }) async {
    final payload = createDevicePairRequestPayload(
      requesterOwnerId: requesterOwnerId,
      requesterDeviceId: requesterDeviceId,
      requesterDevicePublicKeyPem: requesterDevicePublicKeyPem,
      note: note,
      pairingToken: pairingToken,
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
