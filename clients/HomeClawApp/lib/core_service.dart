import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:homeclaw_native/homeclaw_native.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'chat_history_store.dart';
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
  static const String _keyCompanionToken = 'companion_session_token';
  static const String _keyCompanionUserId = 'companion_session_user_id';
  static const String _keyCompanionSavedUsername = 'companion_saved_username';
  static const String _keyCompanionSavedPassword = 'companion_saved_password';
  static const String _keyCompanionDeviceId = 'companion_device_id';
  static const String _defaultBaseUrl = 'http://127.0.0.1:9000';

  String _baseUrl = _defaultBaseUrl;
  String? _apiKey;
  String? _sessionToken;
  String? _sessionUserId;
  List<String> _execAllowlist = [];
  String? _canvasUrl;
  String? _nodesUrl;
  bool _showProgressDuringLongTasks = true;

  String get baseUrl => _baseUrl;
  bool get showProgressDuringLongTasks => _showProgressDuringLongTasks;
  String? get apiKey => _apiKey;
  String? get sessionToken => _sessionToken;
  String? get sessionUserId => _sessionUserId;
  bool get isLoggedIn => _sessionToken != null && _sessionToken!.isNotEmpty && _sessionUserId != null && _sessionUserId!.isNotEmpty;
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
  String? _coreWsRegisteredUserId; // user_id we last sent in register; re-register when current message's userId differs
  Timer? _coreWsPingTimer; // keepalive: send ping so proxies don't close the connection
  static const Duration _coreWsPingInterval = Duration(seconds: 30);
  final Map<String, Completer<Map<String, dynamic>>> _pendingInboundResult = {};
  /// request_id -> (userId, friendId) so when inbound_result arrives we can route to the correct chat.
  final Map<String, ({String userId, String friendId})> _pendingRequestMeta = {};
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
    _sessionToken = prefs.getString(_keyCompanionToken)?.trim();
    if (_sessionToken != null && _sessionToken!.isEmpty) _sessionToken = null;
    _sessionUserId = prefs.getString(_keyCompanionUserId)?.trim();
    if (_sessionUserId != null && _sessionUserId!.isEmpty) _sessionUserId = null;
  }

  /// Persist Core URL and API key (same as Settings). Call after editing on login screen.
  Future<void> saveBaseUrlAndApiKey({required String baseUrl, String? apiKey}) async {
    await saveSettings(baseUrl: baseUrl, apiKey: apiKey);
  }

  /// Save session after login. Persists token and user_id.
  Future<void> saveSession({required String token, required String userId}) async {
    _sessionToken = token.trim();
    _sessionUserId = userId.trim();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyCompanionToken, _sessionToken!);
    await prefs.setString(_keyCompanionUserId, _sessionUserId!);
  }

  /// Clear session and saved credentials (logout). Removes username and password from device.
  Future<void> clearSession() async {
    _sessionToken = null;
    _sessionUserId = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_keyCompanionToken);
    await prefs.remove(_keyCompanionUserId);
    await prefs.remove(_keyCompanionSavedUsername);
    await prefs.remove(_keyCompanionSavedPassword);
  }

  /// Save username and password for auto-login next time. Call after successful login.
  Future<void> saveCredentials({required String username, required String password}) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyCompanionSavedUsername, username.trim());
    await prefs.setString(_keyCompanionSavedPassword, password);
  }

  /// Load saved username and password (for auto-login). Returns null if either is missing.
  Future<({String username, String password})?> getSavedCredentials() async {
    final prefs = await SharedPreferences.getInstance();
    final username = prefs.getString(_keyCompanionSavedUsername)?.trim();
    final password = prefs.getString(_keyCompanionSavedPassword);
    if (username == null || username.isEmpty || password == null) return null;
    return (username: username, password: password);
  }

  /// Remove saved username and password from device.
  Future<void> clearCredentials() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_keyCompanionSavedUsername);
    await prefs.remove(_keyCompanionSavedPassword);
  }

  /// POST /api/auth/login with username and password. Returns {user_id, token, name, friends}. Throws on failure.
  Future<Map<String, dynamic>> login({required String username, required String password}) async {
    final url = Uri.parse('$_baseUrl/api/auth/login');
    final response = await http
        .post(
          url,
          headers: {'Content-Type': 'application/json', ..._authHeaders()},
          body: jsonEncode({'username': username.trim(), 'password': password}),
        )
        .timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      final body = response.body;
      throw Exception(response.statusCode == 401 ? 'Invalid username or password' : 'Login failed: $body');
    }
    final map = jsonDecode(response.body) as Map<String, dynamic>?;
    final userId = (map?['user_id'] as String?)?.trim() ?? '';
    final token = (map?['token'] as String?)?.trim() ?? '';
    if (userId.isEmpty || token.isEmpty) throw Exception('Login response missing user_id or token');
    await saveSession(token: token, userId: userId);
    await saveCredentials(username: username.trim(), password: password);
    return map ?? {};
  }

  /// GET /api/me with Bearer token. Returns {user_id, name, friends}. 401 if token invalid.
  Future<Map<String, dynamic>> getMe() async {
    final url = Uri.parse('$_baseUrl/api/me');
    final response = await http
        .get(url, headers: _authHeaders(forCompanionApi: true))
        .timeout(const Duration(seconds: 10));
    if (response.statusCode == 401) throw Exception('Session expired; please log in again');
    if (response.statusCode != 200) throw Exception('GET /api/me failed: ${response.body}');
    return jsonDecode(response.body) as Map<String, dynamic>? ?? {};
  }

  /// GET /api/me/friends with Bearer token. Returns {friends: [...]}. 401 if token invalid.
  Future<List<Map<String, dynamic>>> getFriends() async {
    final url = Uri.parse('$_baseUrl/api/me/friends');
    final response = await http
        .get(url, headers: _authHeaders(forCompanionApi: true))
        .timeout(const Duration(seconds: 10));
    if (response.statusCode == 401) throw Exception('Session expired; please log in again');
    if (response.statusCode != 200) throw Exception('GET /api/me/friends failed: ${response.body}');
    final map = jsonDecode(response.body) as Map<String, dynamic>?;
    final list = map?['friends'];
    if (list is! List<dynamic>) return [];
    final out = <Map<String, dynamic>>[];
    for (final e in list) {
      if (e is Map<String, dynamic>) out.add(e);
      else if (e is Map) out.add(Map<String, dynamic>.from(e));
    }
    return out;
  }

  Future<void> saveShowProgressDuringLongTasks(bool value) async {
    _showProgressDuringLongTasks = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyShowProgress, value);
  }

  Future<void> saveSettings({required String baseUrl, String? apiKey}) async {
    final trimmed = baseUrl.trim().replaceFirst(RegExp(r'/$'), '');
    _baseUrl = trimmed.isEmpty ? _defaultBaseUrl : trimmed;
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

  /// Auth headers for requests. Use [forCompanionApi: true] only for /api/me and /api/me/friends (they require Bearer session token).
  /// All other routes (/inbound, /api/config/*, /ws, etc.) use Core's verify_inbound_auth which expects the API key, so we pass API key when [forCompanionApi] is false.
  Map<String, String> _authHeaders({bool forCompanionApi = false}) {
    final headers = <String, String>{};
    if (forCompanionApi && _sessionToken != null && _sessionToken!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $_sessionToken';
      return headers;
    }
    if (_apiKey != null && _apiKey!.isNotEmpty) {
      headers['X-API-Key'] = _apiKey!;
      headers['Authorization'] = 'Bearer $_apiKey';
      return headers;
    }
    if (_sessionToken != null && _sessionToken!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $_sessionToken';
    }
    return headers;
  }

  /// Persistent device ID for push registration (one per install; iOS, macOS, Android). Stored in SharedPreferences.
  Future<String> getOrCreateDeviceId() async {
    final prefs = await SharedPreferences.getInstance();
    var id = prefs.getString(_keyCompanionDeviceId)?.trim();
    if (id == null || id.isEmpty) {
      id = const Uuid().v4();
      await prefs.setString(_keyCompanionDeviceId, id);
    }
    return id;
  }

  /// Register push token with Core so Core can send reminders when app is killed/background. iOS/macOS: native APNs only (no Firebase). Android: FCM. No-op on Windows/Linux or if unavailable. Uses a unique device_id per install so re-registering updates the token for that device instead of adding duplicates.
  Future<void> registerPushTokenWithCore(String userId) async {
    if (!Platform.isAndroid && !Platform.isIOS && !Platform.isMacOS) return;
    try {
      String? token;
      final String platform;
      if (Platform.isIOS || Platform.isMacOS) {
        token = await HomeclawNative().getApnsToken();
        platform = Platform.isMacOS ? 'macos' : 'ios';
      } else {
        final settings = await FirebaseMessaging.instance.requestPermission(alert: true, badge: true, sound: true);
        if (settings.authorizationStatus != AuthorizationStatus.authorized && settings.authorizationStatus != AuthorizationStatus.provisional) return;
        token = await FirebaseMessaging.instance.getToken();
        platform = 'android';
      }
      if (token == null || token.isEmpty) return;
      final deviceId = await getOrCreateDeviceId();
      final url = Uri.parse('$_baseUrl/api/companion/push-token');
      final body = jsonEncode({
        'user_id': userId.trim().isEmpty ? 'companion' : userId.trim(),
        'token': token,
        'platform': platform,
        'device_id': deviceId,
      });
      await http.post(url, headers: {'Content-Type': 'application/json', ..._authHeaders()}, body: body).timeout(const Duration(seconds: 10));
    } catch (_) {}
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
  /// [friendId] optional: which friend this conversation is with (e.g. "HomeClaw", "Sabrina"). Omitted or empty → Core uses "HomeClaw". Send when chat is per-friend so Core scopes memory/session correctly.
  /// [images], [videos], [audios], [files] are paths (e.g. from upload) or data URLs Core can read.
  /// [location]: optional "lat,lng" or address string; Core stores it as latest location (per user) and uses it in system context.
  /// [useStream]: when true and [onProgress] is set, sends stream: true and parses SSE; progress events are reported via [onProgress], final result returned as usual. When false or [onProgress] null, uses single-JSON response (no streaming).
  /// For remote Core: uses async: true so the initial POST returns 202 immediately (no long-held connection for proxies like Cloudflare); then polls GET /inbound/result until done. Use [onProgress] to show "Processing…" while polling.
  /// Throws on network or API error.
  Future<Map<String, dynamic>> sendMessage(
    String text, {
    required String userId,
    String? appId,
    String? friendId,
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
    if (friendId != null && friendId.trim().isNotEmpty) body['friend_id'] = friendId.trim();
    if (location != null && location.trim().isNotEmpty) body['location'] = location.trim();
    if (images != null && images.isNotEmpty) body['images'] = images;
    if (videos != null && videos.isNotEmpty) body['videos'] = videos;
    if (audios != null && audios.isNotEmpty) body['audios'] = audios;
    if (files != null && files.isNotEmpty) body['files'] = files;
    if (useAsyncForRemote) body['async'] = true;
    if (useStreamPath) body['stream'] = true;

    // Establish WebSocket for push (reminders, cron) for both local and remote Core.
    await _ensureCoreWsConnected(userId);
    // Register FCM token with Core so reminders can be sent when app is killed/background (iOS/Android only).
    registerPushTokenWithCore(userId);

    if (useAsyncForRemote) {
      return _sendMessageAsync(url, body, onProgress ?? (_) {});
    }
    if (useStreamPath) {
      final result = await _sendMessageStream(url, body, onProgress!);
      _persistInboundResultToStore(userId, friendId, result);
      return result;
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
    final result = {
      'text': (map?['text'] as String?) ?? '',
      'images': responseImages != null
          ? responseImages.map((e) => e as String).toList()
          : (responseImage != null ? [responseImage as String] : null),
    };
    _persistInboundResultToStore(userId, friendId, result);
    return result;
  }

  /// Persist an inbound reply to the correct chat so it is not lost when the user has navigated away.
  void _persistInboundResultToStore(String userId, String? friendId, Map<String, dynamic> result) {
    try {
      final text = (result['text'] as String?) ?? '';
      if (text.isEmpty) return;
      final images = result['images'];
      final imageList = images is List<dynamic>
          ? images.whereType<String>().toList()
          : (images is List<String> ? images : null);
      final effectiveFriendId = (friendId?.trim().isEmpty != false) ? 'HomeClaw' : friendId!.trim();
      ChatHistoryStore().appendMessage(userId, effectiveFriendId, text, false, imageList);
    } catch (_) {}
  }

  /// Ensure WebSocket to Core /ws is connected (for push). When connected, Core sends {"event": "connected", "session_id": "..."}; we send {"event": "register", "user_id": userId} so Core can push proactive messages (cron, reminders) to this connection. [userId] from the message being sent (e.g. body['user_id']). Open WS for both local and remote Core so reminders/cron are delivered. Re-registers when userId changes so reminders for the current chat user are delivered.
  Future<void> _ensureCoreWsConnected([String? userId]) async {
    final trimmed = userId?.trim() ?? '';
    final registerUserId = trimmed.isNotEmpty ? trimmed : 'companion';
    if (_coreWsChannel != null && _coreWsSessionId != null && _coreWsBaseUrl == _baseUrl) {
      if (_coreWsRegisteredUserId == registerUserId) return;
      _coreWsRegisteredUserId = registerUserId;
      try {
        _coreWsChannel?.sink.add(jsonEncode({'event': 'register', 'user_id': registerUserId}));
      } catch (_) {}
      return;
    }
    _coreWsPingTimer?.cancel();
    _coreWsPingTimer = null;
    _coreWsChannel?.sink.close();
    _coreWsSubscription?.cancel();
    _coreWsChannel = null;
    _coreWsSessionId = null;
    _coreWsBaseUrl = null;
    _coreWsRegisteredUserId = null;
    try {
      _coreWsBaseUrl = _baseUrl;
      final baseWs = _baseUrl.replaceFirst(RegExp(r'^http'), 'ws').replaceFirst(RegExp(r'/$'), '');
      // Path must be /ws; query ?api_key=... separate (was: base?api_key=.../ws → path became ?api_key=.../ws → 403)
      final pathAndQuery = (_apiKey != null && _apiKey!.isNotEmpty)
          ? '/ws?api_key=${Uri.encodeComponent(_apiKey!)}'
          : '/ws';
      final uri = Uri.parse('$baseWs$pathAndQuery');
      _coreWsChannel = WebSocketChannel.connect(uri);
      final completer = Completer<void>();
      _coreWsSubscription = _coreWsChannel!.stream.listen(
        (data) {
          if (!completer.isCompleted) {
            try {
              final msg = jsonDecode(data as String) as Map<String, dynamic>?;
              if (msg != null && msg['event'] == 'connected') {
                _coreWsSessionId = msg['session_id'] as String?;
                if (!completer.isCompleted) completer.complete();
                _coreWsRegisteredUserId = registerUserId;
                _coreWsChannel?.sink.add(jsonEncode({'event': 'register', 'user_id': registerUserId}));
                _startCoreWsPingTimer();
              }
            } catch (_) {}
          }
          _onCoreWsMessage(data);
        },
        onError: (_) {
          _coreWsPingTimer?.cancel();
          _coreWsPingTimer = null;
          _coreWsSessionId = null;
          _coreWsRegisteredUserId = null;
        },
        onDone: () {
          _coreWsPingTimer?.cancel();
          _coreWsPingTimer = null;
          _coreWsSessionId = null;
          _coreWsRegisteredUserId = null;
        },
        cancelOnError: false,
      );
      await completer.future.timeout(Duration(seconds: 10), onTimeout: () {
        _coreWsPingTimer?.cancel();
        _coreWsPingTimer = null;
        _coreWsSessionId = null;
        _coreWsBaseUrl = null;
        _coreWsRegisteredUserId = null;
      });
    } catch (_) {
      _coreWsPingTimer?.cancel();
      _coreWsPingTimer = null;
      _coreWsSessionId = null;
      _coreWsBaseUrl = null;
      _coreWsRegisteredUserId = null;
    }
  }

  void _startCoreWsPingTimer() {
    _coreWsPingTimer?.cancel();
    _coreWsPingTimer = Timer.periodic(_coreWsPingInterval, (_) {
      if (_coreWsChannel == null || _coreWsSessionId == null) return;
      try {
        _coreWsChannel?.sink.add(jsonEncode({'event': 'ping'}));
      } catch (_) {}
    });
  }

  void _onCoreWsMessage(dynamic data) {
    Map<String, dynamic>? msg;
    try {
      msg = jsonDecode(data as String) as Map<String, dynamic>?;
    } catch (_) {
      return;
    }
    if (msg == null) return;
    if (msg['event'] == 'pong') return; // keepalive response; no-op
    if (msg['event'] == 'push') {
      final text = msg['text'] as String? ?? '';
      final source = msg['source'] as String? ?? 'push';
      final fromFriend = msg['from_friend'] as String?;
      final responseImages = msg['images'];
      final responseImage = msg['image'];
      final imageList = responseImages is List
          ? (responseImages as List<dynamic>).whereType<String>().toList()
          : (responseImage is String ? <String>[responseImage as String] : null);
      try {
        final map = <String, dynamic>{
          'text': text,
          'source': source,
          'images': imageList != null && imageList.isNotEmpty ? imageList : null,
        };
        if (fromFriend != null && fromFriend.toString().trim().isNotEmpty) {
          map['from_friend'] = fromFriend.toString().trim();
        }
        if (_sessionUserId != null && _sessionUserId!.isNotEmpty) {
          map['user_id'] = _sessionUserId!;
        }
        _pushMessageController.add(map);
      } catch (_) {}
      return;
    }
    if (msg['event'] != 'inbound_result') return;
    final requestId = msg['request_id'] as String?;
    if (requestId == null || requestId.isEmpty) return;
    final meta = _pendingRequestMeta.remove(requestId);
    final completer = _pendingInboundResult.remove(requestId);
    final ok = msg['ok'] as bool? ?? true;
    final text = (msg['text'] as String?) ?? '';
    final err = msg['error'] as String?;
    final responseImages = msg['images'];
    final responseImage = msg['image'];
    final imageList = responseImages is List
        ? (responseImages as List<dynamic>).whereType<String>().toList()
        : (responseImage is String ? <String>[responseImage as String] : null);
    final resultMap = {
      'text': ok ? text : (err ?? text),
      'images': imageList != null && imageList.isNotEmpty ? imageList : null,
    };
    if (meta != null) {
      try {
        _pushMessageController.add({
          'event': 'inbound_result',
          'user_id': meta.userId,
          'friend_id': meta.friendId,
          'text': resultMap['text'],
          'images': resultMap['images'],
        });
      } catch (_) {}
    }
    if (completer != null && !completer.isCompleted) {
      completer.complete(resultMap);
    }
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
    final friendId = (body['friend_id'] as String?)?.trim() ?? '';
    final meta = (userId: userId ?? 'companion', friendId: friendId.isEmpty ? 'HomeClaw' : friendId);
    _pendingRequestMeta[requestId] = meta;
    if (_coreWsSessionId != null) {
      final completer = Completer<Map<String, dynamic>>();
      _pendingInboundResult[requestId] = completer;
      try {
        final result = await completer.future.timeout(
          Duration(seconds: sendMessageTimeoutSeconds),
          onTimeout: () {
            _pendingInboundResult.remove(requestId);
            _pendingRequestMeta.remove(requestId);
            throw TimeoutException('Inbound result push timed out', Duration(seconds: sendMessageTimeoutSeconds));
          },
        );
        return result;
      } catch (_) {
        _pendingInboundResult.remove(requestId);
        _pendingRequestMeta.remove(requestId);
        rethrow;
      }
    }
    return _pollInboundResult(requestId, meta, onProgress);
  }

  /// Poll GET /inbound/result?request_id=... until status is "done" or error. Same auth as /inbound.
  /// [meta] is used to emit result to push stream so the global listener persists to the correct chat when user has navigated away.
  Future<Map<String, dynamic>> _pollInboundResult(
    String requestId,
    ({String userId, String friendId}) meta,
    void Function(String message) onProgress,
  ) async {
    final resultUrl = Uri.parse('$_baseUrl/inbound/result').replace(queryParameters: {'request_id': requestId});
    final headers = _authHeaders();
    final deadline = DateTime.now().add(Duration(seconds: sendMessageTimeoutSeconds));
    while (DateTime.now().isBefore(deadline)) {
      final response = await http.get(resultUrl, headers: headers).timeout(Duration(seconds: 15));
      if (response.statusCode == 404) {
        _pendingRequestMeta.remove(requestId);
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
        _pendingRequestMeta.remove(requestId);
        final ok = map?['ok'] as bool? ?? true;
        final text = (map?['text'] as String?) ?? '';
        final err = map?['error'] as String?;
        final responseImages = map?['images'];
        final responseImage = map?['image'];
        final imageList = responseImages is List
            ? (responseImages as List<dynamic>).whereType<String>().toList()
            : (responseImage is String ? <String>[responseImage as String] : null);
        final result = {
          'text': ok ? text : (err ?? text),
          'images': imageList != null && imageList.isNotEmpty ? imageList : null,
        };
        try {
          _pushMessageController.add({
            'event': 'inbound_result',
            'user_id': meta.userId,
            'friend_id': meta.friendId,
            'text': result['text'],
            'images': result['images'],
          });
        } catch (_) {}
        return result;
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
    final list = map?['users'];
    if (list is! List<dynamic>) return [];
    final out = <Map<String, dynamic>>[];
    for (final e in list) {
      if (e is Map<String, dynamic>) out.add(e);
      else if (e is Map) out.add(Map<String, dynamic>.from(e));
    }
    return out;
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
