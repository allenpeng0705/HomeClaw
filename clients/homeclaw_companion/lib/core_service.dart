import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'node_service.dart';

/// HomeClaw Core API client.
/// Sends messages via POST /inbound and returns the reply text.
class CoreService {
  /// Timeout for sending a message (POST /inbound). Tool use (e.g. document_read + summarize) can take several minutes; use 600 for large PDFs.
  static const int sendMessageTimeoutSeconds = 600;

  static const String _keyBaseUrl = 'core_base_url';
  static const String _keyApiKey = 'core_api_key';
  static const String _keyExecAllowlist = 'exec_allowlist';
  static const String _keyCanvasUrl = 'canvas_url';
  static const String _keyNodesUrl = 'nodes_url';
  static const String _keyShowProgress = 'show_progress_during_long_tasks';
  static const String _defaultBaseUrl = 'http://127.0.0.1:9000';

  String _baseUrl = _defaultBaseUrl;
  String? _apiKey;
  List<String> _execAllowlist = [];
  String? _canvasUrl;
  String? _nodesUrl;
  bool _showProgressDuringLongTasks = true;

  String get baseUrl => _baseUrl;
  bool get showProgressDuringLongTasks => _showProgressDuringLongTasks;
  String? get apiKey => _apiKey;
  List<String> get execAllowlist => List.unmodifiable(_execAllowlist);
  String? get canvasUrl => _canvasUrl;
  String? get nodesUrl => _nodesUrl;

  NodeService? _nodeService;
  NodeService? get nodeService => _nodeService;

  /// WebSocket to Core /ws for push: when open, Core can push async inbound results and proactive messages (cron, reminders).
  WebSocketChannel? _coreWsChannel;
  StreamSubscription? _coreWsSubscription;
  String? _coreWsSessionId;
  String? _coreWsBaseUrl; // base URL we connected to; reconnect if _baseUrl changed
  final Map<String, Completer<Map<String, dynamic>>> _pendingInboundResult = {};
  final StreamController<Map<String, dynamic>> _pushMessageController = StreamController<Map<String, dynamic>>.broadcast();
  /// Stream of proactive push messages from Core (cron, reminders, record_date). UI can listen and show in chat or as notification.
  Stream<Map<String, dynamic>> get pushMessageStream => _pushMessageController.stream;

  /// True if [fullCommand] is allowed by the exec allowlist.
  /// Each entry is either an exact executable name (e.g. "ls") or a regex pattern (e.g. "^/usr/bin/.*").
  bool isExecAllowed(String fullCommand) {
    final trimmed = fullCommand.trim();
    if (trimmed.isEmpty) return false;
    final executable = trimmed.split(RegExp(r'\s+')).first;
    for (final entry in _execAllowlist) {
      final s = entry.trim();
      if (s.isEmpty) continue;
      try {
        final reg = RegExp(s);
        if (reg.hasMatch(trimmed)) return true;
      } catch (_) {
        if (executable == s) return true;
      }
    }
    return false;
  }

  Future<void> loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = (prefs.getString(_keyBaseUrl) ?? _defaultBaseUrl).trim();
    if (_baseUrl.isEmpty) _baseUrl = _defaultBaseUrl;
    _apiKey = prefs.getString(_keyApiKey)?.trim();
    if (_apiKey != null && _apiKey!.isEmpty) _apiKey = null;
    try {
      final allowlistJson = prefs.getString(_keyExecAllowlist);
      _execAllowlist = allowlistJson != null && allowlistJson.isNotEmpty
          ? (jsonDecode(allowlistJson) as List<dynamic>).map((e) => e.toString()).toList()
          : [];
    } catch (_) {
      _execAllowlist = [];
    }
    _canvasUrl = prefs.getString(_keyCanvasUrl)?.trim();
    if (_canvasUrl != null && _canvasUrl!.isEmpty) _canvasUrl = null;
    _nodesUrl = prefs.getString(_keyNodesUrl)?.trim();
    if (_nodesUrl != null && _nodesUrl!.isEmpty) _nodesUrl = null;
    _showProgressDuringLongTasks = prefs.getBool(_keyShowProgress) ?? true;
  }

  Future<void> saveShowProgressDuringLongTasks(bool value) async {
    _showProgressDuringLongTasks = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyShowProgress, value);
  }

  Future<void> saveSettings({required String baseUrl, String? apiKey}) async {
    _baseUrl = baseUrl.trim().replaceFirst(RegExp(r'/$'), '');
    _apiKey = apiKey?.trim().isEmpty == true ? null : apiKey?.trim();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyBaseUrl, _baseUrl);
    if (_apiKey != null) {
      await prefs.setString(_keyApiKey, _apiKey!);
    } else {
      await prefs.remove(_keyApiKey);
    }
  }

  Future<void> saveExecAllowlist(List<String> list) async {
    _execAllowlist = list;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyExecAllowlist, jsonEncode(_execAllowlist));
  }

  Future<void> saveCanvasUrl(String? url) async {
    _canvasUrl = url?.trim().isEmpty == true ? null : url?.trim();
    final prefs = await SharedPreferences.getInstance();
    if (_canvasUrl != null) {
      await prefs.setString(_keyCanvasUrl, _canvasUrl!);
    } else {
      await prefs.remove(_keyCanvasUrl);
    }
  }

  Future<void> saveNodesUrl(String? url) async {
    _nodesUrl = url?.trim().isEmpty == true ? null : url?.trim();
    final prefs = await SharedPreferences.getInstance();
    if (_nodesUrl != null) {
      await prefs.setString(_keyNodesUrl, _nodesUrl!);
    } else {
      await prefs.remove(_keyNodesUrl);
    }
  }

  /// Connect as a node to the plugin at [nodesUrl] with [nodeId].
  Future<void> connectAsNode({required String nodesUrl, String nodeId = 'companion'}) async {
    await _nodeService?.disconnect();
    _nodeService = NodeService();
    await _nodeService!.connect(
      nodesUrl: nodesUrl,
      nodeId: nodeId,
      capabilities: ['screen', 'camera', 'notify'],
    );
    _nodesUrl = nodesUrl.trim().replaceFirst(RegExp(r'/$'), '');
    await saveNodesUrl(_nodesUrl);
  }

  /// Disconnect the node if connected.
  Future<void> disconnectNode() async {
    await _nodeService?.disconnect();
    _nodeService = null;
  }

  Map<String, String> _authHeaders() {
    final headers = <String, String>{};
    if (_apiKey != null && _apiKey!.isNotEmpty) {
      headers['X-API-Key'] = _apiKey!;
      headers['Authorization'] = 'Bearer $_apiKey';
    }
    return headers;
  }

  /// Check if Core is reachable. Returns true if we get any HTTP response (200, 401, 404, etc.), false on timeout/connection error.
  Future<bool> checkConnection() async {
    try {
      final url = Uri.parse('$_baseUrl/api/config/core');
      final response = await http.get(url, headers: _authHeaders()).timeout(const Duration(seconds: 5));
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Upload file(s) to Core POST /api/upload. Returns list of paths Core can read.
  /// Throws on network or API error.
  Future<List<String>> uploadFiles(List<String> filePaths) async {
    if (filePaths.isEmpty) return [];
    final url = Uri.parse('$_baseUrl/api/upload');
    final request = http.MultipartRequest('POST', url);
    request.headers.addAll(_authHeaders());
    for (final p in filePaths) {
      final file = File(p);
      if (!await file.exists()) continue;
      final name = path.basename(p);
      request.files.add(await http.MultipartFile.fromPath('files', p, filename: name));
    }
    final streamed = await request.send().timeout(Duration(seconds: sendMessageTimeoutSeconds));
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode != 200) {
      throw Exception('Upload failed ${response.statusCode}: ${response.body}');
    }
    final map = jsonDecode(response.body) as Map<String, dynamic>?;
    final paths = map?['paths'] as List<dynamic>?;
    return paths?.map((e) => e.toString()).toList() ?? [];
  }

  /// True if Core URL is remote (not localhost). Used to prefer SSE for long requests and avoid "Connection closed while receiving data" from proxy timeouts.
  bool get _isRemoteCore {
    try {
      final uri = Uri.parse(_baseUrl);
      final host = uri.host.toLowerCase();
      return host != 'localhost' && host != '127.0.0.1' && host.isNotEmpty;
    } catch (_) {
      return false;
    }
  }

  /// Send a message to Core and return the reply: { "text": String, "image": String? (data URL) }.
  /// [userId] must be the id of the user in user.yml (the chat owner). Same payload shape as WebChat: text, images, videos, audios, files, location.
  /// [images], [videos], [audios], [files] are paths (e.g. from upload) or data URLs Core can read.
  /// [location]: optional "lat,lng" or address string; Core stores it as latest location (per user) and uses it in system context.
  /// [useStream]: when true and [onProgress] is set, sends stream: true and parses SSE; progress events are reported via [onProgress], final result returned as usual. When false or [onProgress] null, uses single-JSON response (no streaming).
  /// For remote Core: uses async: true so the initial POST returns 202 immediately (no long-held connection for proxies like Cloudflare); then polls GET /inbound/result until done. Use [onProgress] to show "Processing…" while polling.
  /// Throws on network or API error.
  Future<Map<String, dynamic>> sendMessage(
    String text, {
    required String userId,
    String? appId,
    String? location,
    List<String>? images,
    List<String>? videos,
    List<String>? audios,
    List<String>? files,
    bool? useStream,
    void Function(String message)? onProgress,
  }) async {
    final url = Uri.parse('$_baseUrl/inbound');
    final useAsyncForRemote = _isRemoteCore;
    final useStreamPath = !useAsyncForRemote &&
        ((useStream ?? _showProgressDuringLongTasks) && onProgress != null);

    final body = <String, dynamic>{
      'user_id': userId,
      'text': text,
      'action': 'respond',
      'channel_name': 'companion',
    };
    if (appId != null && appId.isNotEmpty) body['app_id'] = appId;
    if (location != null && location.trim().isNotEmpty) body['location'] = location.trim();
    if (images != null && images.isNotEmpty) body['images'] = images;
    if (videos != null && videos.isNotEmpty) body['videos'] = videos;
    if (audios != null && audios.isNotEmpty) body['audios'] = audios;
    if (files != null && files.isNotEmpty) body['files'] = files;
    if (useAsyncForRemote) body['async'] = true;
    if (useStreamPath) body['stream'] = true;

    if (useAsyncForRemote) {
      return _sendMessageAsync(url, body, onProgress ?? (_) {});
    }
    if (useStreamPath) {
      return _sendMessageStream(url, body, onProgress!);
    }

    final headers = <String, String>{
      'Content-Type': 'application/json',
      ..._authHeaders(),
    };
    final response = await http
        .post(url, headers: headers, body: jsonEncode(body))
        .timeout(Duration(seconds: sendMessageTimeoutSeconds));
    if (response.statusCode != 200) {
      final err = response.body;
      throw Exception('Core returned ${response.statusCode}: $err');
    }
    final map = jsonDecode(response.body) as Map<String, dynamic>?;
    final responseImages = map?['images'] as List<dynamic>?;
    final responseImage = map?['image'];
    return {
      'text': (map?['text'] as String?) ?? '',
      'images': responseImages != null
          ? responseImages.map((e) => e as String).toList()
          : (responseImage != null ? [responseImage as String] : null),
    };
  }

  /// Ensure WebSocket to Core /ws is connected (for push). When connected, Core sends {"event": "connected", "session_id": "..."}; we send {"event": "register", "user_id": userId} so Core can push proactive messages (cron, reminders) to this connection. [userId] from the message being sent (e.g. body['user_id']).
  Future<void> _ensureCoreWsConnected([String? userId]) async {
    if (!_isRemoteCore) return;
    if (_coreWsChannel != null && _coreWsSessionId != null && _coreWsBaseUrl == _baseUrl) return;
    _coreWsChannel?.sink.close();
    _coreWsSubscription?.cancel();
    _coreWsChannel = null;
    _coreWsSessionId = null;
    _coreWsBaseUrl = null;
    try {
      _coreWsBaseUrl = _baseUrl;
      var wsUrl = _baseUrl.replaceFirst(RegExp(r'^http'), 'ws').replaceFirst(RegExp(r'/$'), '');
      if (_apiKey != null && _apiKey!.isNotEmpty) {
        wsUrl += (wsUrl.contains('?') ? '&' : '?') + 'api_key=${Uri.encodeComponent(_apiKey!)}';
      }
      final uri = Uri.parse('$wsUrl/ws');
      _coreWsChannel = WebSocketChannel.connect(uri);
      final completer = Completer<void>();
      final registerUserId = userId?.trim().isEmpty != true ? userId!.trim() : 'companion';
      _coreWsSubscription = _coreWsChannel!.stream.listen(
        (data) {
          if (!completer.isCompleted) {
            try {
              final msg = jsonDecode(data as String) as Map<String, dynamic>?;
              if (msg != null && msg['event'] == 'connected') {
                _coreWsSessionId = msg['session_id'] as String?;
                if (!completer.isCompleted) completer.complete();
                _coreWsChannel?.sink.add(jsonEncode({'event': 'register', 'user_id': registerUserId}));
              }
            } catch (_) {}
          }
          _onCoreWsMessage(data);
        },
        onError: (_) => _coreWsSessionId = null,
        onDone: () => _coreWsSessionId = null,
        cancelOnError: false,
      );
      await completer.future.timeout(Duration(seconds: 10), onTimeout: () {
        _coreWsSessionId = null;
        _coreWsBaseUrl = null;
      });
    } catch (_) {
      _coreWsSessionId = null;
      _coreWsBaseUrl = null;
    }
  }

  void _onCoreWsMessage(dynamic data) {
    Map<String, dynamic>? msg;
    try {
      msg = jsonDecode(data as String) as Map<String, dynamic>?;
    } catch (_) {
      return;
    }
    if (msg == null) return;
    if (msg['event'] == 'push') {
      final text = msg['text'] as String? ?? '';
      final source = msg['source'] as String? ?? 'push';
      final responseImages = msg['images'];
      final responseImage = msg['image'];
      final imageList = responseImages is List
          ? (responseImages as List<dynamic>).whereType<String>().toList()
          : (responseImage is String ? <String>[responseImage as String] : null);
      try {
        _pushMessageController.add({
          'text': text,
          'source': source,
          'images': imageList != null && imageList.isNotEmpty ? imageList : null,
        });
      } catch (_) {}
      return;
    }
    if (msg['event'] != 'inbound_result') return;
    final requestId = msg['request_id'] as String?;
    if (requestId == null || requestId.isEmpty) return;
    final completer = _pendingInboundResult.remove(requestId);
    if (completer == null || completer.isCompleted) return;
    final ok = msg['ok'] as bool? ?? true;
    final text = (msg['text'] as String?) ?? '';
    final err = msg['error'] as String?;
    final responseImages = msg['images'];
    final responseImage = msg['image'];
    final imageList = responseImages is List
        ? (responseImages as List<dynamic>).whereType<String>().toList()
        : (responseImage is String ? <String>[responseImage as String] : null);
    completer.complete({
      'text': ok ? text : (err ?? text),
      'images': imageList != null && imageList.isNotEmpty ? imageList : null,
    });
  }

  /// POST /inbound with async: true; get 202 + request_id. If we have a WebSocket session (push_ws_session_id), Core will push the result to us; else we poll. Used for remote Core so proxies do not close the connection.
  Future<Map<String, dynamic>> _sendMessageAsync(
    Uri inboundUrl,
    Map<String, dynamic> body,
    void Function(String message) onProgress,
  ) async {
    final userId = body['user_id'] as String?;
    await _ensureCoreWsConnected(userId);
    if (_coreWsSessionId != null && _coreWsSessionId!.isNotEmpty) {
      body['push_ws_session_id'] = _coreWsSessionId;
    }
    final headers = <String, String>{
      'Content-Type': 'application/json',
      ..._authHeaders(),
    };
    final response = await http
        .post(inboundUrl, headers: headers, body: jsonEncode(body))
        .timeout(Duration(seconds: 30));
    if (response.statusCode != 202) {
      final err = response.body;
      throw Exception('Core returned ${response.statusCode}: $err');
    }
    final map = jsonDecode(response.body) as Map<String, dynamic>?;
    final requestId = map?['request_id'] as String?;
    if (requestId == null || requestId.isEmpty) {
      throw Exception('Core 202 response missing request_id');
    }
    onProgress('Processing your request…');
    if (_coreWsSessionId != null) {
      final completer = Completer<Map<String, dynamic>>();
      _pendingInboundResult[requestId] = completer;
      try {
        final result = await completer.future.timeout(
          Duration(seconds: sendMessageTimeoutSeconds),
          onTimeout: () {
            _pendingInboundResult.remove(requestId);
            throw TimeoutException('Inbound result push timed out', Duration(seconds: sendMessageTimeoutSeconds));
          },
        );
        if (result != null) return result;
      } catch (_) {
        _pendingInboundResult.remove(requestId);
      }
    }
    return _pollInboundResult(requestId, onProgress);
  }

  /// Poll GET /inbound/result?request_id=... until status is "done" or error. Same auth as /inbound.
  Future<Map<String, dynamic>> _pollInboundResult(
    String requestId,
    void Function(String message) onProgress,
  ) async {
    final resultUrl = Uri.parse('$_baseUrl/inbound/result').replace(queryParameters: {'request_id': requestId});
    final headers = _authHeaders();
    final deadline = DateTime.now().add(Duration(seconds: sendMessageTimeoutSeconds));
    while (DateTime.now().isBefore(deadline)) {
      final response = await http.get(resultUrl, headers: headers).timeout(Duration(seconds: 15));
      if (response.statusCode == 404) {
        throw Exception('Request expired or not found (request_id=$requestId)');
      }
      final map = jsonDecode(response.body) as Map<String, dynamic>?;
      final status = map?['status'] as String?;
      if (response.statusCode == 202 && status == 'pending') {
        onProgress('Still working…');
        await Future<void>.delayed(Duration(seconds: 2));
        continue;
      }
      if (response.statusCode == 200 && status == 'done') {
        final ok = map?['ok'] as bool? ?? true;
        final text = (map?['text'] as String?) ?? '';
        final err = map?['error'] as String?;
        final responseImages = map?['images'];
        final responseImage = map?['image'];
        final imageList = responseImages is List
            ? (responseImages as List<dynamic>).whereType<String>().toList()
            : (responseImage is String ? <String>[responseImage as String] : null);
        return {
          'text': ok ? text : (err ?? text),
          'images': imageList != null && imageList.isNotEmpty ? imageList : null,
        };
      }
      await Future<void>.delayed(Duration(seconds: 2));
    }
    throw TimeoutException('Inbound async result timed out');
  }

  /// POST /inbound with stream: true; parses SSE and calls [onProgress] for progress events, returns final result from "done" event.
  Future<Map<String, dynamic>> _sendMessageStream(
    Uri url,
    Map<String, dynamic> body,
    void Function(String message) onProgress,
  ) async {
    final client = http.Client();
    try {
      final request = http.Request('POST', url);
      request.body = jsonEncode(body);
      request.headers['Content-Type'] = 'application/json';
      request.headers.addAll(_authHeaders());
      final streamedResponse = await client.send(request).timeout(
        Duration(seconds: sendMessageTimeoutSeconds),
        onTimeout: () => throw TimeoutException('Inbound stream timed out'),
      );
      if (streamedResponse.statusCode != 200) {
        final err = await streamedResponse.stream.bytesToString();
        throw Exception('Core returned ${streamedResponse.statusCode}: $err');
      }
      final buffer = StringBuffer();
      await for (final chunk in streamedResponse.stream.transform(utf8.decoder)) {
        buffer.write(chunk);
        final text = buffer.toString();
        final parts = text.split('\n\n');
        buffer.clear();
        if (parts.length > 1) {
          for (var i = 0; i < parts.length - 1; i++) {
            final eventText = parts[i].trim();
            for (final line in eventText.split('\n')) {
              if (line.startsWith('data: ')) {
                try {
                  final json = jsonDecode(line.substring(6)) as Map<String, dynamic>?;
                  if (json == null) continue;
                  final event = json['event'] as String?;
                  if (event == 'progress') {
                    final message = json['message'] as String?;
                    if (message != null && message.isNotEmpty) onProgress(message);
                  } else if (event == 'done') {
                    final ok = json['ok'] as bool? ?? false;
                    final outText = (json['text'] as String?) ?? '';
                    final err = json['error'] as String?;
                    final responseImages = json['images'];
                    final responseImage = json['image'];
                    final imageList = responseImages is List
                        ? (responseImages as List<dynamic>).whereType<String>().toList()
                        : (responseImage is String ? <String>[responseImage as String] : null);
                    return {
                      'text': ok ? outText : (err ?? outText),
                      'images': imageList != null && imageList.isNotEmpty ? imageList : null,
                    };
                  }
                } catch (_) {}
              }
            }
          }
          buffer.write(parts.last);
        } else {
          buffer.write(text);
        }
      }
      final remainder = buffer.toString();
      if (remainder.trim().isNotEmpty) {
        for (final line in remainder.split('\n')) {
          if (line.startsWith('data: ')) {
            try {
              final json = jsonDecode(line.substring(6)) as Map<String, dynamic>?;
              if (json != null && json['event'] == 'done') {
                final ok = json['ok'] as bool? ?? false;
                final outText = (json['text'] as String?) ?? '';
                final err = json['error'] as String?;
                final responseImages = json['images'];
                final responseImage = json['image'];
                final imageList = responseImages is List
                    ? (responseImages as List<dynamic>).whereType<String>().toList()
                    : (responseImage is String ? <String>[responseImage as String] : null);
                return {
                  'text': ok ? outText : (err ?? outText),
                  'images': imageList != null && imageList.isNotEmpty ? imageList : null,
                };
              }
            } catch (_) {}
          }
        }
      }
      throw Exception('Stream ended without done event');
    } finally {
      client.close();
    }
  }

  /// GET /api/config/core — current core config (whitelisted keys). Throws on error.
  Future<Map<String, dynamic>> getConfigCore() async {
    final url = Uri.parse('$_baseUrl/api/config/core');
    final response = await http
        .get(url, headers: _authHeaders())
        .timeout(const Duration(seconds: 30));
    if (response.statusCode != 200) {
      throw Exception('Core config: ${response.statusCode} ${response.body}');
    }
    final map = jsonDecode(response.body) as Map<String, dynamic>?;
    return map ?? {};
  }

  /// PATCH /api/config/core — update whitelisted keys. Throws on error.
  Future<void> patchConfigCore(Map<String, dynamic> body) async {
    final url = Uri.parse('$_baseUrl/api/config/core');
    final headers = <String, String>{
      'Content-Type': 'application/json',
      ..._authHeaders(),
    };
    final response = await http
        .patch(url, headers: headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 30));
    if (response.statusCode != 200) {
      throw Exception('Core config patch: ${response.statusCode} ${response.body}');
    }
  }

  /// GET /api/config/users — list users from Core (user.yml). Use for chat list: one chat per user, send user id with every message. Throws on error.
  Future<List<Map<String, dynamic>>> getConfigUsers() async {
    final url = Uri.parse('$_baseUrl/api/config/users');
    final response = await http
        .get(url, headers: _authHeaders())
        .timeout(const Duration(seconds: 30));
    if (response.statusCode != 200) {
      throw Exception('Config users: ${response.statusCode} ${response.body}');
    }
    final map = jsonDecode(response.body) as Map<String, dynamic>?;
    final list = map?['users'] as List<dynamic>?;
    return list?.map((e) => Map<String, dynamic>.from(e as Map)).toList() ?? [];
  }

  /// POST /api/config/users — add user. Throws on error.
  Future<void> addConfigUser(Map<String, dynamic> user) async {
    final url = Uri.parse('$_baseUrl/api/config/users');
    final headers = <String, String>{
      'Content-Type': 'application/json',
      ..._authHeaders(),
    };
    final response = await http
        .post(url, headers: headers, body: jsonEncode(user))
        .timeout(const Duration(seconds: 30));
    if (response.statusCode != 200) {
      throw Exception('Add user: ${response.statusCode} ${response.body}');
    }
  }

  /// PATCH /api/config/users/{name} — update user. Body: name, id, email, im, phone, permissions. Throws on error.
  Future<void> patchConfigUser(String name, Map<String, dynamic> body) async {
    final url = Uri.parse('$_baseUrl/api/config/users/${Uri.encodeComponent(name)}');
    final headers = <String, String>{
      'Content-Type': 'application/json',
      ..._authHeaders(),
    };
    final response = await http
        .patch(url, headers: headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 30));
    if (response.statusCode != 200) {
      throw Exception('Update user: ${response.statusCode} ${response.body}');
    }
  }

  /// DELETE /api/config/users/{name} — remove user. Throws on error.
  Future<void> removeConfigUser(String name) async {
    final url = Uri.parse('$_baseUrl/api/config/users/${Uri.encodeComponent(name)}');
    final response = await http
        .delete(url, headers: _authHeaders())
        .timeout(const Duration(seconds: 30));
    if (response.statusCode != 200 && response.statusCode != 404) {
      throw Exception('Remove user: ${response.statusCode} ${response.body}');
    }
  }

  /// POST /memory/reset — clear RAG memory, AGENT_MEMORY, daily memory. For testing.
  Future<void> postMemoryReset() async {
    final url = Uri.parse('$_baseUrl/memory/reset');
    final response = await http
        .post(url, headers: _authHeaders())
        .timeout(const Duration(seconds: 30));
    if (response.statusCode != 200) {
      throw Exception('Memory reset: ${response.statusCode} ${response.body}');
    }
  }

  /// POST /knowledge_base/reset — clear knowledge base (all users). For testing.
  Future<void> postKnowledgeBaseReset() async {
    final url = Uri.parse('$_baseUrl/knowledge_base/reset');
    final response = await http
        .post(url, headers: _authHeaders())
        .timeout(const Duration(seconds: 30));
    if (response.statusCode != 200) {
      throw Exception('Knowledge base reset: ${response.statusCode} ${response.body}');
    }
  }

  /// GET or POST /knowledge_base/sync_folder — trigger manual sync of user's knowledgebase folder. Returns {ok, message, added, removed, errors}.
  Future<Map<String, dynamic>> syncKnowledgeBaseFolder(String userId) async {
    final url = Uri.parse('$_baseUrl/knowledge_base/sync_folder').replace(queryParameters: {'user_id': userId});
    final response = await http
        .get(url, headers: _authHeaders())
        .timeout(const Duration(seconds: 60));
    final body = jsonDecode(response.body is String ? response.body as String : '{}') as Map<String, dynamic>? ?? {};
    if (response.statusCode != 200) {
      throw Exception(body['detail']?.toString() ?? 'Sync failed: ${response.statusCode}');
    }
    return body;
  }

  /// POST /api/testing/clear-all — unregister external plugins and clear skills vector store. For testing.
  Future<void> postTestingClearAll() async {
    final url = Uri.parse('$_baseUrl/api/testing/clear-all');
    final response = await http
        .post(url, headers: _authHeaders())
        .timeout(const Duration(seconds: 30));
    if (response.statusCode != 200) {
      throw Exception('Clear all: ${response.statusCode} ${response.body}');
    }
  }
}
