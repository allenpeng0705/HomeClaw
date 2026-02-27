import 'dart:async';
import 'dart:convert';

import 'package:homeclaw_native/homeclaw_native.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

/// Connects to HomeClaw Browser plugin's /nodes-ws as a node.
/// Registers with [nodeId] and [capabilities]; handles incoming commands
/// (camera_snap, camera_clip, screen_record, notify) by calling native/plugins.
class NodeService {
  NodeService();

  final _native = HomeclawNative();

  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  String? _nodeId;
  bool _registered = false;

  bool get isConnected => _channel != null && _registered;
  String? get nodeId => _nodeId;

  /// Connect to [nodesUrl] (e.g. http://127.0.0.1:3020), register as [nodeId] with [capabilities].
  /// [capabilities] e.g. ['canvas', 'screen', 'camera', 'location'].
  Future<void> connect({
    required String nodesUrl,
    required String nodeId,
    List<String> capabilities = const ['screen', 'camera', 'notify'],
  }) async {
    await disconnect();
    final base = nodesUrl.trim().replaceFirst(RegExp(r'/$'), '');
    final wsUrl = base.replaceFirst(RegExp(r'^http'), 'ws');
    final uri = Uri.parse('$wsUrl/nodes-ws');
    _nodeId = nodeId;
    _channel = WebSocketChannel.connect(uri);
    _registered = false;

    _subscription = _channel!.stream.listen(
      (data) => _onMessage(data, nodeId, capabilities),
      onError: (_) => _registered = false,
      onDone: () => _registered = false,
      cancelOnError: false,
    );

    _channel!.sink.add(jsonEncode({
      'type': 'register',
      'node_id': nodeId,
      'capabilities': capabilities,
    }));
    _registered = true;
  }

  void _onMessage(dynamic data, String nid, List<String> caps) {
    Map<String, dynamic>? msg;
    try {
      msg = jsonDecode(data as String) as Map<String, dynamic>?;
    } catch (_) {
      return;
    }
    if (msg == null) return;
    if (msg['type'] == 'registered') {
      _registered = true;
      return;
    }
    if (msg['type'] != 'command') return;
    final id = msg['id'];
    final command = msg['command'] as String?;
    final params = msg['params'] as Map<String, dynamic>? ?? {};
    _handleCommand(nid, id, command ?? '', params);
  }

  Future<void> _handleCommand(String nid, dynamic id, String command, Map<String, dynamic> params) async {
    Map<String, dynamic> payload = {};

    switch (command) {
      case 'notify':
        final title = params['title'] as String? ?? 'Node';
        final body = params['body'] as String? ?? '';
        await _native.showNotification(title: title, body: body);
        payload = {'success': true, 'text': 'Notification shown'};
        break;
      case 'camera_snap':
        final path = await _native.cameraSnap();
        if (path != null && path.isNotEmpty) {
          payload = {'success': true, 'text': 'Photo captured', 'media': path};
        } else {
          payload = {'success': false, 'error': 'camera_not_available'};
        }
        break;
      case 'camera_clip':
        final duration = (params['duration'] as num?)?.toInt() ?? 5;
        final path = await _native.cameraClip(durationSec: duration, includeAudio: true);
        if (path != null && path.isNotEmpty) {
          payload = {'success': true, 'text': 'Clip recorded', 'media': path};
        } else {
          payload = {'success': false, 'error': 'camera_not_available'};
        }
        break;
      case 'screen_record':
        final duration = (params['duration'] as num?)?.toInt() ?? 10;
        final path = await _native.startScreenRecord(durationSec: duration, includeAudio: false);
        if (path != null && path.isNotEmpty) {
          payload = {'success': true, 'text': 'Screen recorded', 'media': path};
        } else {
          payload = {'success': false, 'error': 'screen_record_not_available'};
        }
        break;
      default:
        payload = {'success': false, 'error': 'command_not_supported', 'text': command};
    }

    _sendResult(id, payload);
  }

  void _sendResult(dynamic id, Map<String, dynamic> payload) {
    _channel?.sink.add(jsonEncode({
      'type': 'command_result',
      'id': id,
      'payload': payload,
    }));
  }

  Future<void> disconnect() async {
    await _subscription?.cancel();
    _subscription = null;
    await _channel?.sink.close();
    _channel = null;
    _registered = false;
  }
}
