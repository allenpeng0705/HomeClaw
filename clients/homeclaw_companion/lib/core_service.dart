import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';

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
  static const String _defaultBaseUrl = 'http://127.0.0.1:9000';

  String _baseUrl = _defaultBaseUrl;
  String? _apiKey;
  List<String> _execAllowlist = [];
  String? _canvasUrl;
  String? _nodesUrl;

  String get baseUrl => _baseUrl;
  String? get apiKey => _apiKey;
  List<String> get execAllowlist => List.unmodifiable(_execAllowlist);
  String? get canvasUrl => _canvasUrl;
  String? get nodesUrl => _nodesUrl;

  NodeService? _nodeService;
  NodeService? get nodeService => _nodeService;

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

  /// Send a message to Core and return the reply: { "text": String, "image": String? (data URL) }.
  /// [userId] must be the id of the user in user.yml (the chat owner). Same payload shape as WebChat: text, images, videos, audios, files, location.
  /// [images], [videos], [audios], [files] are paths (e.g. from upload) or data URLs Core can read.
  /// [location]: optional "lat,lng" or address string; Core stores it as latest location (per user) and uses it in system context.
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
  }) async {
    final url = Uri.parse('$_baseUrl/inbound');
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
