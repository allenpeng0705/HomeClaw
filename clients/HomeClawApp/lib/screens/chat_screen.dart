import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:path/path.dart' as path;
import 'package:flutter_tts/flutter_tts.dart';
import 'package:homeclaw_native/homeclaw_native.dart';
import 'package:homeclaw_voice/homeclaw_voice.dart';
import 'package:file_picker/file_picker.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:record/record.dart';
import 'package:video_player/video_player.dart';
import '../chat_history_store.dart';
import '../core_service.dart';
import '../federation_e2e_crypto.dart';
import '../widgets/homeclaw_snackbars.dart';
import 'canvas_screen.dart';
import 'settings_screen.dart';

class ChatScreen extends StatefulWidget {
  final CoreService coreService;
  final String userId;
  final String userName;
  /// Which friend this chat is with (e.g. "HomeClaw", "Sabrina"). Used for store key and to route incoming push/result to this chat.
  final String? friendId;
  final String? initialMessage;
  /// True when chatting with a real person (user-to-user). Send via POST /api/user-message; show push-to-talk. No AI reply.
  final bool isUserFriend;
  /// When [isUserFriend], the other user's id (for sendUserMessage and filtering inbox).
  final String? toUserId;
  /// When set, user chat is with someone on another Core (show in app bar).
  final String? remotePeerInstanceId;

  const ChatScreen({
    super.key,
    required this.coreService,
    required this.userId,
    required this.userName,
    this.friendId,
    this.initialMessage,
    this.isUserFriend = false,
    this.toUserId,
    this.remotePeerInstanceId,
  });

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with WidgetsBindingObserver {
  final List<MapEntry<String, bool>> _messages = [];
  /// Optional image data URLs per message (same index as _messages; null or empty when no images).
  final List<List<String>?> _messageImages = [];
  /// Optional audio data URLs per message (same index as _messages; for user-to-user voice).
  final List<List<String>?> _messageAudios = [];
  /// Optional video data URLs per message (same index as _messages; for user-to-user short video).
  final List<List<String>?> _messageVideos = [];
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  bool _loading = false;

  /// Pagination: number of messages fetched per page from Core.
  static const int _pageSize = 50;
  /// Current offset into Core chat history (for scroll-up pagination).
  int _chatHistoryOffset = 0;
  /// True while fetching an older page of messages.
  bool _loadingMoreMessages = false;
  /// False once Core returns fewer messages than _pageSize (no more older messages).
  bool _hasMoreMessages = true;
  /// When streaming is on, latest progress message from Core (e.g. "Generating your presentation…"); shown under the loading bar.
  String? _loadingMessage;
  bool _voiceListening = false;
  String _voiceTranscript = '';
  StreamSubscription<Map<String, dynamic>>? _voiceSubscription;
  /// Set true when user taps Cancel so a late "final" event does not trigger _send().
  bool _voiceInputCancelled = false;
  final _native = HomeclawNative();
  final _voice = HomeclawVoice();
  final _tts = FlutterTts();
  final _imagePicker = ImagePicker();
  String? _lastReply;
  final List<String> _pendingImagePaths = [];
  final List<String> _pendingVideoPaths = [];
  final List<String> _pendingFilePaths = [];
  static const String _keyTtsAutoSpeak = 'tts_auto_speak';
  bool _ttsAutoSpeak = false;
  static const String _keyVoiceInputLocale = 'voice_input_locale';
  String? _voiceInputLocale;
  bool _ttsSpeaking = false;
  bool? _coreConnected;
  bool _connectionChecking = false;
  Timer? _connectionCheckTimer;
  /// When chatting with a user friend, poll inbox so new messages appear without leaving the screen.
  Timer? _userInboxPollTimer;
  StreamSubscription<Map<String, dynamic>>? _pushMessageSubscription;
  /// Push-to-talk (user friends only): true while recording.
  bool _recordingPushToTalk = false;
  final AudioRecorder _voiceRecorder = AudioRecorder();

  /// Rotating status messages when waiting for reply (when no progress from Core).
  static const List<String> _loadingStatusMessages = [
    'Still working…',
    'Thinking…',
    'Almost there…',
  ];
  int _loadingStatusIndex = 0;
  Timer? _loadingStatusTimer;
  bool _wasRouteCurrent = false;
  Uint8List? _chatPartnerAvatar;
  String _cursorActiveCwd = '';
  /// Dev bridge: stored Cursor/Claude session exists for active project (from GET /api/cursor-bridge/status).
  bool _devBridgeStoredSessionActive = false;
  String? _interactiveSessionId;
  int _interactiveLastSeq = 1;
  final TextEditingController _interactiveInputController = TextEditingController();
  String _interactiveOutput = '';

  /// Cursor friend only: when true, POST /inbound includes `cursor_agent_yolo` so Core passes `yolo` to the bridge for that `run_agent` (CLI --yolo).
  static const String _keyCursorAgentYolo = 'chat_cursor_agent_yolo';
  bool _cursorAgentYolo = false;

  /// Claude Code friend only: when true, POST /inbound includes `claude_skip_permissions` → bridge adds --dangerously-skip-permissions for that run_agent.
  static const String _keyClaudeSkipPermissions = 'chat_claude_skip_permissions';
  bool _claudeSkipPermissions = false;

  bool get _isDevBridgeFriend {
    final fid = (widget.friendId ?? '').trim().toLowerCase();
    return fid == 'cursor' || fid == 'claudecode' || fid == 'trae';
  }

  Future<void> _loadCursorAgentYoloPref() async {
    if ((widget.friendId ?? '').trim().toLowerCase() != 'cursor') return;
    try {
      final p = await SharedPreferences.getInstance();
      if (!mounted) return;
      setState(() => _cursorAgentYolo = p.getBool(_keyCursorAgentYolo) ?? false);
    } catch (_) {}
  }

  Future<void> _setCursorAgentYolo(bool value) async {
    if (!mounted) return;
    setState(() => _cursorAgentYolo = value);
    try {
      final p = await SharedPreferences.getInstance();
      await p.setBool(_keyCursorAgentYolo, value);
    } catch (_) {}
  }

  Future<void> _loadClaudeSkipPermissionsPref() async {
    if ((widget.friendId ?? '').trim().toLowerCase() != 'claudecode') return;
    try {
      final p = await SharedPreferences.getInstance();
      if (!mounted) return;
      setState(() => _claudeSkipPermissions = p.getBool(_keyClaudeSkipPermissions) ?? false);
    } catch (_) {}
  }

  Future<void> _setClaudeSkipPermissions(bool value) async {
    if (!mounted) return;
    setState(() => _claudeSkipPermissions = value);
    try {
      final p = await SharedPreferences.getInstance();
      await p.setBool(_keyClaudeSkipPermissions, value);
    } catch (_) {}
  }

  Future<void> _refreshCursorActiveProject() async {
    if (!_isDevBridgeFriend) return;
    try {
      final fid = (widget.friendId ?? '').trim().toLowerCase();
      final backend = fid == 'trae' ? 'trae' : (fid == 'claudecode' ? 'claude' : 'cursor');
      final map = await widget.coreService.getCursorBridgeStatus(backend: backend);
      final cwd = (map['active_cwd'] as String?)?.trim() ?? '';
      var linked = false;
      if (fid == 'cursor') {
        linked = map['cursor_stored_session_active'] == true;
      } else if (fid == 'claudecode') {
        linked = map['claude_stored_session_active'] == true;
      }
      if (!mounted) return;
      setState(() {
        _cursorActiveCwd = cwd;
        _devBridgeStoredSessionActive = linked;
      });
    } catch (_) {
      // Keep previous value on failure.
    }
  }

  Future<void> _startInteractiveSessionIfNeeded() async {
    if (!_isDevBridgeFriend || _interactiveSessionId != null) return;
    try {
      final cwd = _cursorActiveCwd.trim().isNotEmpty ? _cursorActiveCwd.trim() : null;
      final fid = (widget.friendId ?? '').trim().toLowerCase();
      final bridgePlugin = fid == 'trae' ? 'trae-bridge' : (fid == 'claudecode' ? 'claude-code-bridge' : 'cursor-bridge');
      final result = await widget.coreService.interactiveStart(
        bridgePlugin: bridgePlugin,
        cwd: cwd,
      );
      final sid = (result['session_id'] as String?)?.trim();
      final initial = (result['initial_output'] as String?) ?? '';
      if (!mounted || sid == null || sid.isEmpty) return;
      setState(() {
        _interactiveSessionId = sid;
        _interactiveLastSeq = 1;
        _interactiveOutput = initial;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _interactiveOutput = 'Failed to start interactive agent: ${e.toString().replaceFirst(RegExp(r'^Exception:?\s*'), '')}. '
            'Ensure the bridge is running and Core can reach it.';
      });
    }
  }

  Future<void> _sendInteractiveInput() async {
    final sid = _interactiveSessionId;
    if (sid == null) return;
    final text = _interactiveInputController.text;
    if (text.trim().isEmpty) return;
    _interactiveInputController.clear();
    try {
      await widget.coreService.interactiveWrite(sessionId: sid, data: '$text\n');
      await _refreshInteractiveOutput();
    } catch (_) {}
  }

  Future<void> _refreshInteractiveOutput() async {
    final sid = _interactiveSessionId;
    if (sid == null) return;
    try {
      final map = await widget.coreService.interactiveRead(sessionId: sid, fromSeq: _interactiveLastSeq);
      final chunks = map['chunks'] as List<dynamic>? ?? const [];
      if (chunks.isEmpty) return;
      final buffer = StringBuffer(_interactiveOutput);
      var maxSeq = _interactiveLastSeq;
      for (final raw in chunks) {
        if (raw is Map<String, dynamic>) {
          final text = (raw['text'] as String?) ?? '';
          final seq = (raw['seq'] as int?) ?? maxSeq;
          buffer.write(text);
          if (seq > maxSeq) maxSeq = seq;
        }
      }
      if (!mounted) return;
      setState(() {
        _interactiveOutput = buffer.toString();
        _interactiveLastSeq = maxSeq + 1;
      });
    } catch (_) {}
  }

  Future<void> _stopInteractiveSession() async {
    final sid = _interactiveSessionId;
    if (sid == null) return;
    try {
      await widget.coreService.interactiveStop(sessionId: sid);
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _interactiveSessionId = null;
      _interactiveLastSeq = 1;
      _interactiveOutput = '';
    });
  }

  Future<void> _loadChatPartnerAvatar() async {
    final url = widget.isUserFriend && (widget.toUserId ?? '').trim().isNotEmpty
        ? widget.coreService.userAvatarUrl(widget.toUserId!.trim())
        : widget.coreService.friendAvatarUrl((widget.friendId ?? 'HomeClaw').trim());
    final bytes = await widget.coreService.fetchAvatarWithAuth(url);
    if (mounted && bytes != null && bytes.isNotEmpty) {
      setState(() => _chatPartnerAvatar = bytes);
    }
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadTtsAutoSpeak();
    _loadVoiceInputLocale();
    _loadChatPartnerAvatar();
    _refreshCursorActiveProject();
    _loadCursorAgentYoloPref();
    _loadClaudeSkipPermissionsPref();
    _scrollController.addListener(_onScrollForPagination);
    if (widget.isUserFriend && widget.toUserId != null && widget.toUserId!.trim().isNotEmpty) {
      if ((widget.remotePeerInstanceId?.trim().isNotEmpty ?? false) && widget.coreService.federationE2eEnabled) {
        unawaited(widget.coreService.ensureFederationE2eKeysRegistered());
      }
      _loadUserInbox();
      _userInboxPollTimer = Timer.periodic(const Duration(seconds: 5), (_) {
        if (mounted && widget.isUserFriend && widget.toUserId != null) _loadUserInbox();
      });
    } else {
      _loadChatHistory();
      _syncChatHistoryFromCore();
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        await _checkPendingInboundAndRefresh();
      });
    }
    _checkCoreConnection();
    _connectionCheckTimer = Timer.periodic(const Duration(seconds: 30), (_) => _checkCoreConnection());
    _pushMessageSubscription = widget.coreService.pushMessageStream.listen(_onPushMessage);
    widget.coreService.registerPushTokenWithCore(widget.userId);
    if (widget.initialMessage != null && widget.initialMessage!.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _inputController.text = widget.initialMessage!;
      });
    }
  }

  void _onScrollForPagination() {
    if (widget.isUserFriend) return;
    if (_loadingMoreMessages || !_hasMoreMessages) return;
    if (!_scrollController.hasClients) return;
    if (_scrollController.position.pixels <= _scrollController.position.minScrollExtent + 50) {
      _loadOlderMessages();
    }
  }

  Future<void> _loadOlderMessages() async {
    if (_loadingMoreMessages || !_hasMoreMessages || widget.isUserFriend) return;
    setState(() => _loadingMoreMessages = true);
    try {
      final friendId = (widget.friendId != null && widget.friendId!.trim().isNotEmpty) ? widget.friendId!.trim() : 'HomeClaw';
      final list = await widget.coreService.getChatHistory(
        userId: widget.userId,
        friendId: friendId,
        limit: _pageSize,
        offset: _chatHistoryOffset + _messages.length,
      );
      if (!mounted) return;
      if (list.isEmpty || list.length < _pageSize) {
        setState(() => _hasMoreMessages = false);
      }
      if (list.isEmpty) {
        setState(() => _loadingMoreMessages = false);
        return;
      }
      final older = <MapEntry<String, bool>>[];
      final olderImages = <List<String>?>[];
      final olderAudios = <List<String>?>[];
      final olderVideos = <List<String>?>[];
      for (final m in list) {
        final role = ((m['role']?.toString()) ?? '').trim().toLowerCase();
        final content = ((m['content']?.toString()) ?? '').trim();
        older.add(MapEntry(content.isEmpty ? '(empty)' : content, role == 'user'));
        olderImages.add(null);
        olderAudios.add(null);
        olderVideos.add(null);
      }
      final prevMax = _scrollController.position.maxScrollExtent;
      setState(() {
        _messages.insertAll(0, older);
        _messageImages.insertAll(0, olderImages);
        _messageAudios.insertAll(0, olderAudios);
        _messageVideos.insertAll(0, olderVideos);
        _loadingMoreMessages = false;
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || !_scrollController.hasClients) return;
        final newMax = _scrollController.position.maxScrollExtent;
        _scrollController.jumpTo(_scrollController.offset + (newMax - prevMax));
      });
    } catch (_) {
      if (mounted) setState(() => _loadingMoreMessages = false);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    if (state != AppLifecycleState.resumed || !mounted) return;
    _refreshCursorActiveProject();
    if (widget.isUserFriend && widget.toUserId != null && widget.toUserId!.trim().isNotEmpty) {
      _loadUserInbox();
    } else {
      _checkPendingInboundAndRefresh();
      _syncChatHistoryFromCore();
    }
  }

  void _loadChatHistory() {
    try {
      final loaded = ChatHistoryStore().load(widget.userId, widget.friendId);
      if (loaded.isEmpty) return;
      _messages.clear();
      _messageImages.clear();
      _messageAudios.clear();
      _messageVideos.clear();
      for (final e in loaded) {
        _messages.add(e.key);
        _messageImages.add(e.value);
        _messageAudios.add(null);
        _messageVideos.add(null);
      }
      if (mounted) {
        setState(() {});
        _scrollToBottom();
      }
    } catch (_) {
      // Store load failed; keep empty chat.
    }
  }

  /// If a pending async request (e.g. Cursor/ClaudeCode) completed while user was away or app was in background, fetch result, persist, and refresh chat so the reply is not missed.
  Future<void> _checkPendingInboundAndRefresh() async {
    if (widget.isUserFriend) return;
    try {
      final result = await widget.coreService.checkPendingInboundResult(widget.userId, widget.friendId);
      if (result != null && mounted) {
        _loadChatHistory();
        setState(() {});
      }
    } catch (_) {}
  }

  /// Load user-to-user messages from GET /api/user-inbox and show only thread with [widget.toUserId].
  /// Load Core↔user (AI) chat history from Core so replies that arrived while the app was offline appear in the list.
  Future<void> _syncChatHistoryFromCore() async {
    if (widget.isUserFriend) return;
    final friendId = (widget.friendId != null && widget.friendId!.trim().isNotEmpty) ? widget.friendId!.trim() : 'HomeClaw';
    try {
      final list = await widget.coreService.getChatHistory(userId: widget.userId, friendId: friendId, limit: _pageSize, offset: 0);
      if (list.isEmpty || !mounted) return;
      final messages = <MapEntry<String, bool>>[];
      final images = <List<String>?>[];
      final audios = <List<String>?>[];
      final videos = <List<String>?>[];
      for (final m in list) {
        final role = ((m['role']?.toString()) ?? '').trim().toLowerCase();
        final content = ((m['content']?.toString()) ?? '').trim();
        final isUser = role == 'user';
        messages.add(MapEntry(content.isEmpty ? '(empty)' : content, isUser));
        images.add(null);
        audios.add(null);
        videos.add(null);
      }
      if (!mounted) return;
      setState(() {
        _messages.clear();
        _messageImages.clear();
        _messageAudios.clear();
        _messageVideos.clear();
        _messages.addAll(messages);
        _messageImages.addAll(images);
        _messageAudios.addAll(audios);
        _messageVideos.addAll(videos);
        _chatHistoryOffset = 0;
        _hasMoreMessages = list.length >= _pageSize;
      });
      _scrollToBottom();
    } catch (_) {
      // Keep local history on failure (e.g. offline)
    }
  }

  /// Load full thread (both directions) from GET /api/user-inbox/thread so sent messages do not disappear on poll.
  Future<void> _loadUserInbox() async {
    if (widget.toUserId == null || widget.toUserId!.trim().isEmpty) return;
    try {
      final data = await widget.coreService.getUserInboxThread(
        userId: widget.userId,
        otherUserId: widget.toUserId!,
        limit: 100,
      );
      final list = data['messages'] as List<dynamic>?;
      if (list == null) return;
      if (list.isEmpty) {
        // Valid empty thread: clear UI and mark read so friend list does not show a stale red dot.
        widget.coreService.setUserInboxLastRead(widget.userId, widget.toUserId!, DateTime.now().millisecondsSinceEpoch / 1000.0);
        if (mounted) {
          setState(() {
            _messages.clear();
            _messageImages.clear();
            _messageAudios.clear();
            _messageVideos.clear();
          });
        }
        return;
      }
      final myId = widget.userId.trim();
      _messages.clear();
      _messageImages.clear();
      _messageAudios.clear();
      _messageVideos.clear();
      for (final m in list) {
        if (m is! Map) continue;
        final mmap = m is Map<String, dynamic> ? m : Map<String, dynamic>.from(m);
        var text = (mmap['text'] as String?)?.trim() ?? '';
        final from = (mmap['from_user_id'] as String?)?.trim() ?? '';
        final isUser = from == myId;
        final e2eRaw = mmap['e2e'];
        Map<String, dynamic>? e2eMap;
        if (e2eRaw is Map<String, dynamic>) {
          e2eMap = e2eRaw;
        } else if (e2eRaw is Map) {
          e2eMap = Map<String, dynamic>.from(e2eRaw);
        }
        if (e2eMap != null && e2eMap.isNotEmpty) {
          final decrypted = await widget.coreService.decryptFederatedE2eIfPresent(e2eMap);
          if (decrypted != null && decrypted.isNotEmpty) {
            text = decrypted;
          } else {
            text = '[Encrypted message]';
          }
        }
        if (!isUser && (mmap['source'] as String?)?.trim() == 'federation' && text.isNotEmpty) {
          text = '◇ $text';
        }
        _messages.add(MapEntry(text.isEmpty ? '(attachment)' : text, isUser));
        final imgList = mmap['images'] as List<dynamic>?;
        final images = imgList != null ? imgList.whereType<String>().toList() : null;
        _messageImages.add(images != null && images.isNotEmpty ? images : null);
        final audList = mmap['audios'] as List<dynamic>?;
        final audios = audList != null ? audList.whereType<String>().toList() : null;
        _messageAudios.add(audios != null && audios.isNotEmpty ? audios : null);
        final vidList = mmap['videos'] as List<dynamic>?;
        final videos = vidList != null ? vidList.whereType<String>().toList() : null;
        _messageVideos.add(videos != null && videos.isNotEmpty ? videos : null);
      }
      // Mark thread as read up to latest message so friend list unread dot clears.
      double latestTs = DateTime.now().millisecondsSinceEpoch / 1000.0;
      for (final m in list) {
        if (m is! Map) continue;
        final at = (m['created_at'] as num?)?.toDouble();
        if (at != null && at > latestTs) latestTs = at;
      }
      widget.coreService.setUserInboxLastRead(widget.userId, widget.toUserId!, latestTs);
      if (mounted) {
        setState(() {});
        _scrollToBottom();
      }
    } catch (_) {
      if (mounted) setState(() {});
    }
  }

  Future<void> _persistChatHistory() async {
    final list = <MapEntry<MapEntry<String, bool>, List<String>?>>[];
    for (var i = 0; i < _messages.length; i++) {
      list.add(MapEntry(_messages[i], i < _messageImages.length ? _messageImages[i] : null));
    }
    await ChatHistoryStore().save(widget.userId, list, widget.friendId);
  }

  /// Get current position as "lat,lng" for Core. Returns null if unavailable or on error.
  Future<String?> _getCurrentLocationString() async {
    try {
      final enabled = await Geolocator.isLocationServiceEnabled();
      if (!enabled) return null;
      final perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        final requested = await Geolocator.requestPermission();
        if (requested != LocationPermission.whileInUse && requested != LocationPermission.always) return null;
      }
      if (perm == LocationPermission.deniedForever) return null;
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.medium),
      ).timeout(const Duration(seconds: 5));
      return '${pos.latitude},${pos.longitude}';
    } catch (_) {
      return null;
    }
  }

  Future<void> _clearChatHistory() async {
    await ChatHistoryStore().clear(widget.userId, widget.friendId);
    if (!mounted) return;
    setState(() {
      _messages.clear();
      _messageImages.clear();
      _messageAudios.clear();
      _messageVideos.clear();
      _lastReply = null;
      _chatHistoryOffset = 0;
      _hasMoreMessages = true;
    });
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Chat history cleared')),
      );
    }
  }

  Future<void> _syncKnowledgeBase() async {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Syncing knowledge base…')),
    );
    try {
      final result = await widget.coreService.syncKnowledgeBaseFolder(widget.userId);
      if (!mounted) return;
      final ok = result['ok'] == true;
      final msg = result['message']?.toString() ?? '';
      final added = result['added'] is int ? result['added'] as int : 0;
      final removed = result['removed'] is int ? result['removed'] as int : 0;
      final summary = ok
          ? 'KB sync: $msg (added: $added, removed: $removed)'
          : 'Sync failed: $msg';
      if (ok) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(summary)));
      } else {
        ScaffoldMessenger.of(context).showSnackBar(homeClawErrorSnackBar(context, summary));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        homeClawErrorSnackBar(context, 'Sync failed: $e'),
      );
    }
  }

  Future<void> _checkCoreConnection() async {
    if (_connectionChecking || !mounted) return;
    setState(() => _connectionChecking = true);
    final connected = await widget.coreService.checkConnection();
    if (mounted) setState(() {
      _coreConnected = connected;
      _connectionChecking = false;
    });
  }

  void _onPushMessage(Map<String, dynamic> push) {
    final text = push['text'] as String? ?? '';
    final source = (push['source'] as String?)?.trim() ?? 'push';
    final e2eEncrypted = push['e2e_encrypted'] == true;
    // User-to-user: refresh inbox so the new message appears; match by from_user_id or from_friend.
    if (widget.isUserFriend && widget.toUserId != null && source == 'user_message') {
      final fromUserId = (push['from_user_id'] as String?)?.trim();
      final pushFriendId = (push['friend_id'] ?? push['from_friend']) as String?;
      final pushFriend = (pushFriendId?.toString().trim() ?? '').isEmpty ? '' : pushFriendId!.trim();
      final thisFriend = (widget.friendId?.trim() ?? '').isEmpty ? '' : widget.friendId!.trim();
      final match = (fromUserId != null && fromUserId == widget.toUserId!.trim()) || (pushFriend.isNotEmpty && pushFriend == thisFriend);
      if (match) {
        _loadUserInbox();
        return;
      }
    }
    if (text.isEmpty && !e2eEncrypted) return;
    final pushFriendId = (push['friend_id'] ?? push['from_friend']) as String?;
    final pushFriend = (pushFriendId?.toString().trim() ?? '').isEmpty ? 'HomeClaw' : pushFriendId!.trim();
    final thisFriend = (widget.friendId?.trim() ?? '').isEmpty ? 'HomeClaw' : widget.friendId!.trim();
    if (pushFriend != thisFriend) return;
    if (push['event'] == 'inbound_result') return;
    final imageList = push['images'] as List<dynamic>?;
    final images = imageList != null
        ? imageList.whereType<String>().toList()
        : (push['image'] is String ? <String>[push['image'] as String] : null);
    if (!mounted) return;
    final audioList = push['audios'] as List<dynamic>?;
    final audios = audioList != null
        ? audioList.whereType<String>().toList()
        : (push['audio'] is String ? <String>[push['audio'] as String] : null);
    final videoList = push['videos'] as List<dynamic>?;
    final videos = videoList != null
        ? videoList.whereType<String>().toList()
        : (push['video'] is String ? <String>[push['video'] as String] : null);
    if (!mounted) return;
    setState(() {
      _messages.add(MapEntry(text, false));
      _messageImages.add(images != null && images.isNotEmpty ? images : null);
      _messageAudios.add(audios != null && audios.isNotEmpty ? audios : null);
      _messageVideos.add(videos != null && videos.isNotEmpty ? videos : null);
    });
    _scrollToBottom();
    _persistChatHistory();
    if (!mounted) return;
    final title = push['source'] == 'reminder' ? 'Reminder' : thisFriend;
    final preview = text.length > 80 ? '${text.substring(0, 80)}…' : text;
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(
      SnackBar(content: Text('$title: $preview')),
    );
    // System notification is shown by global listener in main.dart
  }

  Future<void> _loadTtsAutoSpeak() async {
    final prefs = await SharedPreferences.getInstance();
    if (mounted) setState(() => _ttsAutoSpeak = prefs.getBool(_keyTtsAutoSpeak) ?? false);
  }

  Future<void> _loadVoiceInputLocale() async {
    final prefs = await SharedPreferences.getInstance();
    if (mounted) setState(() => _voiceInputLocale = prefs.getString(_keyVoiceInputLocale));
  }

  Future<void> _setVoiceInputLocale(String? localeId) async {
    setState(() => _voiceInputLocale = localeId?.isEmpty == true ? null : localeId);
    final prefs = await SharedPreferences.getInstance();
    if (localeId == null || localeId.isEmpty) {
      await prefs.remove(_keyVoiceInputLocale);
    } else {
      await prefs.setString(_keyVoiceInputLocale, localeId);
    }
  }

  Future<void> _setTtsAutoSpeak(bool value) async {
    setState(() => _ttsAutoSpeak = value);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyTtsAutoSpeak, value);
  }

  Future<void> _send() async {
    // When voice is active, use transcript and then stop voice so the stream doesn't repopulate the field.
    final String text = _voiceListening
        ? (_voiceTranscript.trim().isNotEmpty ? _voiceTranscript.trim() : _inputController.text.trim())
        : _inputController.text.trim();
    final hasAttachments = _pendingImagePaths.isNotEmpty || _pendingVideoPaths.isNotEmpty || _pendingFilePaths.isNotEmpty;
    if ((text.isEmpty && !hasAttachments) || _loading) return;
    if (!mounted) return;
    // Claim sending immediately so a concurrent "final" voice event or double tap cannot trigger a second send.
    setState(() {
      _loading = true;
      _loadingMessage = null;
      _loadingStatusIndex = 0;
    });
    _startLoadingStatusTimer();
    if (_voiceListening) {
      // Cancel subscription first so no more "final" events can trigger _send() and cause double send.
      _voiceSubscription?.cancel();
      _voiceSubscription = null;
      await _voice.stopVoiceListening();
      if (!mounted) {
        _stopLoadingStatusTimer();
        setState(() => _loading = false);
        return;
      }
      setState(() {
        _voiceListening = false;
        _voiceTranscript = '';
        _inputController.clear();
      });
    } else {
      _inputController.clear();
    }
    final imagesToSend = List<String>.from(_pendingImagePaths);
    final videosToSend = List<String>.from(_pendingVideoPaths);
    final filesToSend = List<String>.from(_pendingFilePaths);
    // Build display URLs for attached images so they show in the user's message bubble
    final userImageDataUrls = imagesToSend.isNotEmpty
        ? await _filePathsToImageDataUrls(imagesToSend)
        : <String>[];
    // One short video for user-to-user (max 15MB, ~10s)
    final userVideoDataUrls = videosToSend.isNotEmpty
        ? await _filePathsToVideoDataUrls([videosToSend.first])
        : <String>[];
    if (videosToSend.isNotEmpty && userVideoDataUrls.isEmpty && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Video not sent: keep under 15MB (e.g. ~10 seconds) for user messages.')),
      );
    }
    if (!mounted) {
      _stopLoadingStatusTimer();
      setState(() => _loading = false);
      return;
    }
    setState(() {
      _pendingImagePaths.clear();
      _pendingVideoPaths.clear();
      _pendingFilePaths.clear();
      _messages.add(MapEntry(text.isEmpty ? '(attachment)' : text, true));
      _messageImages.add(userImageDataUrls.isEmpty ? null : userImageDataUrls);
      _messageAudios.add(null);
      _messageVideos.add(userVideoDataUrls.isEmpty ? null : userVideoDataUrls);
      _loading = true;
      _loadingStatusIndex = 0;
    });
    _startLoadingStatusTimer();
    _scrollToBottom();
    _persistChatHistory();
    // User-to-user: send via POST /api/user-message; no AI reply.
    if (widget.isUserFriend && widget.toUserId != null && widget.toUserId!.trim().isNotEmpty) {
      try {
        Map<String, dynamic>? e2eEnvelope;
        final rid = widget.remotePeerInstanceId?.trim();
        final fedE2e = widget.coreService.federationE2eEnabled;
        final requireE2e = widget.coreService.federationE2eRequireEncrypted;
        final textOnly = text.isNotEmpty && imagesToSend.isEmpty && videosToSend.isEmpty && filesToSend.isEmpty;
        if (rid != null && rid.isNotEmpty && fedE2e) {
          if (requireE2e && !textOnly) {
            throw Exception('This chat requires encrypted text-only messages (no images, video, or files).');
          }
          if (textOnly) {
            await widget.coreService.ensureFederationE2eKeysRegistered();
            final peerPk = await widget.coreService.getFederationPeerE2ePublicKey(
              peerInstanceId: rid,
              remoteUserId: widget.toUserId!.trim(),
            );
            if (requireE2e && (peerPk == null || peerPk.isEmpty)) {
              throw Exception('Encrypted messaging is required but the other user has not registered a key on their Core yet.');
            }
            if (peerPk != null && peerPk.isNotEmpty) {
              try {
                final raw = Uint8List.fromList(base64Decode(peerPk));
                if (raw.length != 32) {
                  if (requireE2e) {
                    throw Exception('Peer public key from server is not a valid 32-byte X25519 key.');
                  }
                } else {
                  final env = await FederationE2eCrypto.encryptEnvelopeUtf8(
                    plaintext: text.isEmpty ? '(attachment)' : text,
                    recipientPublicKey32: raw,
                  );
                  e2eEnvelope = Map<String, dynamic>.from(env);
                }
              } catch (_) {
                if (requireE2e) rethrow;
              }
            }
          }
        }
        await widget.coreService.sendUserMessage(
          fromUserId: widget.userId,
          toUserId: widget.toUserId!.trim(),
          text: e2eEnvelope != null ? '' : (text.isEmpty ? '(attachment)' : text),
          images: userImageDataUrls.isEmpty ? null : userImageDataUrls,
          videos: userVideoDataUrls.isEmpty ? null : userVideoDataUrls,
          e2e: e2eEnvelope,
        );
        if (mounted) {
          _stopLoadingStatusTimer();
          setState(() {
            _loading = false;
            _loadingMessage = null;
          });
          _scrollToBottom();
        }
      } catch (e) {
        if (mounted) {
          _stopLoadingStatusTimer();
          setState(() {
            _messages.add(MapEntry('Error: $e', false));
            _messageImages.add(null);
            _messageAudios.add(null);
            _messageVideos.add(null);
            _loading = false;
            _loadingMessage = null;
          });
          _scrollToBottom();
        }
      }
      return;
    }
    try {
      List<String> imagePaths = [];
      List<String> videoPaths = [];
      List<String> filePaths = [];
      final allToUpload = [...imagesToSend, ...videosToSend, ...filesToSend];
      if (allToUpload.isNotEmpty) {
        try {
          final uploaded = await widget.coreService.uploadFiles(allToUpload);
          final nI = imagesToSend.length;
          final nV = videosToSend.length;
          imagePaths = uploaded.take(nI).toList();
          videoPaths = uploaded.skip(nI).take(nV).toList();
          filePaths = uploaded.skip(nI + nV).toList();
        } catch (_) {
          // Same fallback as web chat: if upload fails, send images as data URLs so message still goes through.
          final dataUrls = await _filePathsToImageDataUrls(imagesToSend);
          if (dataUrls.isNotEmpty) {
            imagePaths = dataUrls;
          }
          // Videos and documents not sent on upload failure to avoid huge payloads.
        }
      }
      String? locationStr;
      try {
        locationStr = await _getCurrentLocationString();
      } catch (_) {}
      final result = await widget.coreService.sendMessage(
        text.isEmpty ? 'See attached.' : text,
        userId: widget.userId,
        friendId: (widget.friendId?.trim().isEmpty != false) ? null : widget.friendId,
        location: locationStr,
        images: imagePaths.isEmpty ? null : imagePaths,
        videos: videoPaths.isEmpty ? null : videoPaths,
        files: filePaths.isEmpty ? null : filePaths,
        cursorAgentYolo: (widget.friendId ?? '').trim().toLowerCase() == 'cursor' ? _cursorAgentYolo : null,
        claudeSkipPermissions:
            (widget.friendId ?? '').trim().toLowerCase() == 'claudecode' ? _claudeSkipPermissions : null,
        onProgress: widget.coreService.showProgressDuringLongTasks
            ? (String message) {
                if (mounted) setState(() => _loadingMessage = message);
              }
            : null,
      );
      if (mounted) {
        final cancelled = result['cancelled'] == true;
        final reply = (result['text'] as String?) ?? '';
        _stopLoadingStatusTimer();
        setState(() {
          _loading = false;
          _loadingMessage = null;
        });
        if (cancelled) {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Request cancelled')),
            );
          }
          return;
        }
        final imageList = result['images'] as List<dynamic>?;
        final imageDataUrls = imageList != null
            ? imageList.whereType<String>().where((s) => s.startsWith('data:image/')).toList()
            : <String>[];
        _lastReply = reply;
        setState(() {
          _messages.add(MapEntry(reply.isEmpty ? '(no reply)' : reply, false));
          _messageImages.add(imageDataUrls.isEmpty ? null : imageDataUrls);
          _messageAudios.add(null);
          _messageVideos.add(null);
        });
        _scrollToBottom();
        await _persistChatHistory();
        final preview = reply.isEmpty ? 'No reply' : (reply.length > 80 ? '${reply.substring(0, 80)}…' : reply);
        await _native.showNotification(title: 'HomeClaw', body: preview);
        if (_ttsAutoSpeak && reply.isNotEmpty) _speakReplyText(reply);
      }
    } catch (e) {
      if (mounted) {
        _stopLoadingStatusTimer();
        setState(() {
          _messages.add(MapEntry('Error: $e', false));
          _messageImages.add(null);
          _messageAudios.add(null);
          _messageVideos.add(null);
          _loading = false;
          _loadingMessage = null;
        });
        _scrollToBottom();
        _persistChatHistory();
      }
    }
  }

  /// Show delete confirmation for the message at [index]; on confirm, remove it from the list.
  void _showDeleteMessageConfirmation(BuildContext context, int index) {
    if (index < 0 || index >= _messages.length) return;
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete message?'),
        content: const Text('This message will be removed from the chat. This only affects this device; it does not change Core\'s session.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
              onPressed: () {
              Navigator.of(ctx).pop();
              setState(() {
                _messages.removeAt(index);
                if (index < _messageImages.length) _messageImages.removeAt(index);
                if (index < _messageAudios.length) _messageAudios.removeAt(index);
                if (index < _messageVideos.length) _messageVideos.removeAt(index);
              });
              _persistChatHistory();
              if (mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Message deleted')),
                );
              }
            },
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(ctx).colorScheme.error,
            ),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
  }

  static const Map<String, String> _imageMime = {
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'webp': 'image/webp',
  };

  /// Build data URL for one short video (e.g. 10s). Max one video, max 15MB. Returns empty list if none or too large.
  static const int _maxVideoBytes = 15 * 1024 * 1024;

  Future<List<String>> _filePathsToVideoDataUrls(List<String> filePaths) async {
    if (filePaths.isEmpty) return [];
    final file = File(filePaths.first);
    if (!await file.exists()) return [];
    final length = await file.length();
    if (length > _maxVideoBytes) return [];
    try {
      final bytes = await file.readAsBytes();
      final b64 = base64Encode(bytes);
      final ext = path.extension(filePaths.first).toLowerCase().replaceFirst('.', '');
      final mime = ext == 'webm' ? 'video/webm' : 'video/mp4';
      return ['data:$mime;base64,$b64'];
    } catch (_) {
      return [];
    }
  }

  /// Build data URLs for image files (same fallback as web chat when upload fails).
  Future<List<String>> _filePathsToImageDataUrls(List<String> filePaths) async {
    final out = <String>[];
    for (final p in filePaths) {
      final ext = path.extension(p).toLowerCase().replaceFirst('.', '');
      if (!_imageMime.containsKey(ext)) continue;
      final file = File(p);
      if (!await file.exists()) continue;
      final bytes = await file.readAsBytes();
      final b64 = base64Encode(bytes);
      out.add('data:${_imageMime[ext]};base64,$b64');
    }
    return out;
  }

  /// Stop voice listening and send the current transcript.
  Future<void> _stopVoiceAndSend() async {
    if (!_voiceListening) return;
    await _voice.stopVoiceListening();
    _voiceSubscription?.cancel();
    _voiceSubscription = null;
    final textToSend = _voiceTranscript.trim();
    setState(() {
      _voiceListening = false;
      if (textToSend.isNotEmpty) {
        _inputController.text = textToSend;
        _voiceTranscript = '';
      }
    });
    if (textToSend.isNotEmpty) _send();
  }

  /// Start push-to-talk recording (user friends only). Call _stopPushToTalkAndSend when user releases.
  Future<void> _startPushToTalk() async {
    if (widget.toUserId == null || widget.toUserId!.trim().isEmpty) return;
    final hasPermission = await _voiceRecorder.hasPermission();
    if (!hasPermission) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Microphone permission is needed for voice messages.')),
        );
      }
      return;
    }
    try {
      final dir = await getTemporaryDirectory();
      final recordPath = path.join(dir.path, 'push_voice_${DateTime.now().millisecondsSinceEpoch}.m4a');
      await _voiceRecorder.start(const RecordConfig(), path: recordPath);
      if (mounted) setState(() => _recordingPushToTalk = true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Voice record start failed: $e')));
      }
    }
  }

  /// Stop push-to-talk, read file, send as user message with audios, and add to chat.
  Future<void> _stopPushToTalkAndSend() async {
    if (!_recordingPushToTalk) return;
    try {
      final filePath = await _voiceRecorder.stop();
      if (!mounted) return;
      setState(() => _recordingPushToTalk = false);
      if (filePath == null || filePath.isEmpty) return;
      final file = File(filePath);
      if (!await file.exists()) return;
      if (widget.coreService.federationE2eRequireEncrypted && (widget.remotePeerInstanceId?.trim().isNotEmpty ?? false)) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Voice messages are not available when this Core requires encrypted federation chat.')),
          );
        }
        return;
      }
      final bytes = await file.readAsBytes();
      final b64 = base64Encode(bytes);
      final dataUrl = 'data:audio/mp4;base64,$b64';
      try {
        await widget.coreService.sendUserMessage(
          fromUserId: widget.userId,
          toUserId: widget.toUserId!.trim(),
          text: '',
          audios: [dataUrl],
        );
        if (!mounted) return;
        setState(() {
          _messages.add(MapEntry('(voice)', true));
          _messageImages.add(null);
          _messageAudios.add([dataUrl]);
        });
        _scrollToBottom();
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Send voice failed: $e')));
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() => _recordingPushToTalk = false);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Voice record stop failed: $e')));
      }
    }
  }

  /// Stop voice listening and discard the transcript (do not send).
  Future<void> _cancelVoiceInput() async {
    if (!_voiceListening) return;
    _voiceInputCancelled = true;
    _voiceSubscription?.cancel();
    _voiceSubscription = null;
    await _voice.stopVoiceListening();
    if (mounted) {
      setState(() {
        _voiceListening = false;
        _voiceTranscript = '';
        _inputController.text = '';
      });
    }
  }

  Future<void> _toggleVoice() async {
    if (_voiceListening) {
      await _stopVoiceAndSend();
      return;
    }
    _voiceInputCancelled = false;
    setState(() {
      _voiceTranscript = '';
      _inputController.clear();
    });
    _voiceSubscription = _voice.voiceEventStream.listen(
        (event) {
        if (!mounted) return;
        final partial = event['partial'] as String?;
        final finalText = event['final'] as String?;
        if (finalText != null && finalText.isNotEmpty) {
          setState(() {
            _voiceTranscript = finalText;
            _inputController.text = finalText;
            _inputController.selection = TextSelection.collapsed(offset: finalText.length);
          });
          // Only auto-send from "final" if not cancelled and not already sending.
          if (!_voiceInputCancelled && !_loading) {
            _send().then((_) {
              if (mounted) setState(() => _voiceTranscript = '');
            });
          }
        } else if (partial != null && partial.isNotEmpty) {
          setState(() {
            _voiceTranscript = partial;
            _inputController.text = partial;
            _inputController.selection = TextSelection.collapsed(offset: partial.length);
          });
        }
      },
      onError: (e) {
        if (mounted) {
          setState(() => _voiceListening = false);
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Voice error: $e')),
          );
        }
      },
    );
    try {
      await _voice.startVoiceListening(locale: _voiceInputLocale);
      if (mounted) setState(() => _voiceListening = true);
    } catch (e) {
      if (mounted) {
        setState(() => _voiceListening = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Voice failed: $e. On macOS, allow Microphone in System Settings > Privacy.')),
        );
      }
    }
  }

  /// Copy a picked file (e.g. from Photos app) to a persistent temp file so preview and upload work.
  /// On macOS, the path from image_picker can be short-lived or security-scoped; we try path first, then readAsBytes.
  /// Returns (path, null) on success, (null, errorMessage) on failure.
  static Future<({String? path, String? error})> _copyPickedFileToTemp(XFile xFile, {String defaultExt = '.jpg'}) async {
    final dir = await getTemporaryDirectory();
    // Ensure subdir exists (macOS sandbox Caches path may not exist on first use).
    final picksDir = Directory('${dir.path}/homeclaw_picks');
    await picksDir.create(recursive: true);
    final ext = path.extension(xFile.name).isEmpty ? defaultExt : path.extension(xFile.name);
    final dest = File('${picksDir.path}/pick_${DateTime.now().millisecondsSinceEpoch}$ext');

    // 1) Try copy via path (works if path is still valid, e.g. camera or some galleries).
    final rawPath = xFile.path;
    if (rawPath != null && rawPath.isNotEmpty) {
      try {
        final srcPath = rawPath.startsWith('file://') ? Uri.parse(rawPath).path : rawPath;
        final src = File(srcPath);
        if (await src.exists()) {
          await src.copy(dest.path);
          if (await dest.exists()) return (path: dest.absolute.path, error: null);
        }
      } catch (_) {}
    }

    // 2) Read bytes from XFile (handles security-scoped / in-memory on macOS).
    try {
      final bytes = await xFile.readAsBytes();
      await dest.writeAsBytes(bytes);
      if (await dest.exists()) return (path: dest.absolute.path, error: null);
      return (path: null, error: 'File was written but not found at ${dest.path}');
    } catch (e) {
      return (path: null, error: e.toString());
    }
  }

  Future<void> _takePhoto() async {
    await Future<void>.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;
    final source = await showDialog<ImageSource>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Take photo'),
        content: const Text('Use camera to take a new photo, or choose an existing image from your device.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(ImageSource.camera), child: const Text('Use camera')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(ImageSource.gallery), child: const Text('Choose from device')),
        ],
      ),
    );
    if (source == null || !mounted) return;
    try {
      if (mounted) {
        showDialog(
          context: context,
          barrierDismissible: false,
          builder: (_) => AlertDialog(
            content: Row(
              children: [
                const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)),
                const SizedBox(width: 16),
                Expanded(child: Text(source == ImageSource.camera ? 'Opening camera…' : 'Choosing photo…', textAlign: TextAlign.start)),
              ],
            ),
          ),
        );
      }
      final xFile = await _imagePicker.pickImage(source: source);
      if (mounted) Navigator.of(context).pop();
      if (xFile == null || !mounted) return;
      // Copy to app temp so preview/upload work (macOS Photos returns short-lived paths).
      final result = await _copyPickedFileToTemp(xFile);
      if (result.path == null || !mounted) {
        setState(() {
          _messages.add(MapEntry('Photo error: ${result.error ?? "could not read or copy the image."}', false));
          _messageImages.add(null);
          _messageAudios.add(null);
          _messageVideos.add(null);
        });
        return;
      }
      final filePath = result.path!;
      final added = await _showMediaPreview(context, type: 'photo', filePath: filePath, label: 'Add this photo to your message?');
      if (added && mounted) {
        setState(() => _pendingImagePaths.add(filePath));
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Photo attached. Type a message and Send to include it.')));
      }
    } catch (e) {
      if (mounted) {
        try { Navigator.of(context).pop(); } catch (_) {}
        setState(() {
          _messages.add(MapEntry('Photo error: $e', false));
          _messageImages.add(null);
          _messageAudios.add(null);
          _messageVideos.add(null);
        });
      }
    }
  }

  Future<void> _recordVideo() async {
    await Future<void>.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;
    final source = await showDialog<ImageSource>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Record video'),
        content: const Text('Use camera to record a new video, or choose an existing video from your device.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(ImageSource.camera), child: const Text('Use camera')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(ImageSource.gallery), child: const Text('Choose from device')),
        ],
      ),
    );
    if (source == null || !mounted) return;
    try {
      if (mounted) {
        showDialog(
          context: context,
          barrierDismissible: false,
          builder: (_) => AlertDialog(
            content: Row(
              children: [
                const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)),
                const SizedBox(width: 16),
                Expanded(child: Text(source == ImageSource.camera ? 'Recording video…' : 'Choosing video…', textAlign: TextAlign.start)),
              ],
            ),
          ),
        );
      }
      final xFile = await _imagePicker.pickVideo(source: source, maxDuration: const Duration(seconds: 30));
      if (mounted) Navigator.of(context).pop();
      if (xFile == null || !mounted) return;
      // Copy to app temp when from gallery so path is stable (macOS Photos short-lived path).
      String? filePath;
      if (source == ImageSource.gallery) {
        final result = await _copyPickedFileToTemp(xFile, defaultExt: '.mp4');
        filePath = result.path;
        if (filePath == null || !mounted) {
          setState(() {
            _messages.add(MapEntry('Video error: ${result.error ?? "could not read or copy the video."}', false));
            _messageImages.add(null);
            _messageAudios.add(null);
            _messageVideos.add(null);
          });
          return;
        }
      } else {
        filePath = xFile.path;
      }
      if (filePath == null || !mounted) {
          setState(() {
            _messages.add(MapEntry('Video error: could not read or copy the video.', false));
            _messageImages.add(null);
            _messageAudios.add(null);
            _messageVideos.add(null);
          });
        return;
      }
      final added = await _showMediaPreview(context, type: 'video', filePath: filePath, label: 'Add this video to your message?');
      if (added && mounted) {
        setState(() => _pendingVideoPaths.add(filePath!));
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Video attached. Type a message and Send to include it.')));
      }
    } catch (e) {
      if (mounted) {
        try { Navigator.of(context).pop(); } catch (_) {}
        setState(() {
          _messages.add(MapEntry('Video error: $e', false));
          _messageImages.add(null);
          _messageAudios.add(null);
          _messageVideos.add(null);
        });
      }
    }
  }

  Future<void> _recordScreen() async {
    await Future<void>.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;
    try {
      if (mounted) showDialog(context: context, barrierDismissible: false, builder: (_) => const AlertDialog(content: Column(mainAxisSize: MainAxisSize.min, children: [SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)), SizedBox(height: 12), Text('Recording screen… (about 10 seconds)')])));
      final recordPath = await _native.startScreenRecord(durationSec: 10, includeAudio: false);
      if (mounted) Navigator.of(context).pop();
      if (recordPath == null || recordPath.isEmpty) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                Platform.isMacOS
                    ? 'Screen recording failed. Allow Screen Recording in System Settings → Privacy & Security, then try again.'
                    : 'Screen recording not available on this platform',
              ),
              duration: const Duration(seconds: 5),
            ),
          );
        }
        return;
      }
      final added = await _showMediaPreview(context, type: 'video', filePath: recordPath, label: 'Add this screen recording to your message?');
      if (added && mounted) {
        setState(() => _pendingVideoPaths.add(recordPath));
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Screen recording attached. Send to include it.')));
      }
    } catch (e) {
      if (mounted) {
        try { Navigator.of(context).pop(); } catch (_) {}
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Screen record error: $e')));
      }
    }
  }

  Future<void> _attachDocument() async {
    try {
      final result = await FilePicker.platform.pickFiles(
        allowMultiple: true,
        type: FileType.custom,
        allowedExtensions: ['pdf', 'txt', 'md', 'doc', 'docx', 'rtf', 'csv', 'xls', 'xlsx', 'odt', 'ods'],
      );
      if (result == null || result.files.isEmpty || !mounted) return;
      final paths = result.files.where((f) => f.path != null).map((f) => f.path!).toList();
      if (paths.isEmpty) return;
      setState(() => _pendingFilePaths.addAll(paths));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${paths.length} file(s) attached. Type a message and Send to include them.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Attach file error: $e')));
      }
    }
  }

  Future<bool> _showMediaPreview(BuildContext context, {required String type, required String filePath, required String label}) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(type == 'photo' ? 'Preview photo' : 'Preview video'),
        content: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 220, minWidth: 280, maxWidth: 560, maxHeight: 600),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
              if (type == 'photo')
                SizedBox(
                  height: 200,
                  width: 560,
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: Image.file(
                      File(filePath),
                      fit: BoxFit.contain,
                      height: 200,
                      width: 560,
                      frameBuilder: (_, child, frame, __) {
                        if (frame == null) {
                          return Container(
                            height: 200,
                            width: 560,
                            color: Theme.of(ctx).colorScheme.surfaceContainerHighest,
                            child: const Center(child: SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2))),
                          );
                        }
                        return child;
                      },
                      errorBuilder: (_, __, ___) => Center(
                        child: Icon(Icons.broken_image_outlined, size: 48, color: Theme.of(ctx).colorScheme.outline),
                      ),
                    ),
                  ),
                )
              else
                Row(
                  children: [
                    Icon(Icons.videocam, size: 48, color: Theme.of(ctx).colorScheme.primary),
                    const SizedBox(width: 12),
                    Expanded(child: Text(path.basename(filePath), style: Theme.of(ctx).textTheme.bodySmall, overflow: TextOverflow.ellipsis)),
                  ],
                ),
              const SizedBox(height: 12),
              Text(label, style: Theme.of(ctx).textTheme.bodyMedium),
            ],
          ),
        ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Reject')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text('Confirm')),
        ],
      ),
    );
    return result == true;
  }

  /// For TTS only: strip emoji and punctuation so speech sounds clean. Does not change chat text.
  static String _textForTts(String text) {
    final buffer = StringBuffer();
    for (final rune in text.runes) {
      if (_isEmojiRune(rune)) continue;
      if (_isPunctuationRune(rune)) {
        buffer.write(' ');
        continue;
      }
      buffer.write(String.fromCharCode(rune));
    }
    return buffer.toString().replaceAll(RegExp(r'\s+'), ' ').trim();
  }

  static bool _isEmojiRune(int rune) {
    return (rune >= 0x1F300 && rune <= 0x1F9FF) ||
        (rune >= 0x2600 && rune <= 0x26FF) ||
        (rune >= 0x2700 && rune <= 0x27BF) ||
        (rune >= 0x1F600 && rune <= 0x1F64F) ||
        (rune >= 0x1F1E0 && rune <= 0x1F1FF) ||
        (rune >= 0x1F900 && rune <= 0x1F9FF);
  }

  static bool _isPunctuationRune(int rune) {
    return (rune >= 0x21 && rune <= 0x2F) ||
        (rune >= 0x3A && rune <= 0x40) ||
        (rune >= 0x5B && rune <= 0x60) ||
        (rune >= 0x7B && rune <= 0x7E) ||
        rune == 0x2014 || rune == 0x2013 || rune == 0x2026 || rune == 0x2022;
  }

  /// Speak a reply (filtered for TTS). Used for auto-speak and for "Speak last reply".
  /// Uses the same language as voice input when set (Voice input language in settings).
  Future<void> _speakReplyText(String raw) async {
    final text = _textForTts(raw.trim());
    if (text.isEmpty) return;
    if (mounted) setState(() => _ttsSpeaking = true);
    try {
      if (_voiceInputLocale != null && _voiceInputLocale!.isNotEmpty) {
        // Voice input locale is e.g. "en_US" or "zh_CN"; TTS often accepts "en-US" / "zh-CN".
        final ttsLocale = _voiceInputLocale!.replaceAll('_', '-');
        await _tts.setLanguage(ttsLocale);
      }
      await _tts.speak(text);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('TTS: $e')));
    } finally {
      if (mounted) setState(() => _ttsSpeaking = false);
    }
  }

  Future<void> _stopTts() async {
    try {
      await _tts.stop();
    } catch (_) {}
    if (mounted) setState(() => _ttsSpeaking = false);
  }

  Future<void> _speakLastReply() async {
    final raw = _lastReply?.trim();
    if (raw == null || raw.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No reply to speak')),
      );
      return;
    }
    final text = _textForTts(raw);
    if (text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Nothing to speak after removing emoji and punctuation')),
      );
      return;
    }
    await _speakReplyText(raw);
  }

  Future<void> _showVoiceAndTtsLanguages() async {
    List<String> voiceLocales = [];
    List<String> ttsLanguages = [];
    try {
      voiceLocales = List<String>.from(await _voice.getAvailableLocales());
      final ttsList = await _tts.getLanguages;
      ttsLanguages = ttsList is List
          ? List<String>.from((ttsList as List).map((e) => e.toString()))
          : [];
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not load languages: $e')));
      }
      return;
    }
    if (!mounted) return;
    final voiceOptions = ['System default', ...voiceLocales];
    String currentVoiceDisplay = _voiceInputLocale == null
        ? 'System default'
        : voiceLocales.firstWhere((s) => s.startsWith(_voiceInputLocale!), orElse: () => _voiceInputLocale!);

    await showDialog<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('Voice input & TTS languages'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Voice input language', style: Theme.of(ctx).textTheme.titleSmall),
                const SizedBox(height: 4),
                DropdownButton<String>(
                  value: voiceOptions.contains(currentVoiceDisplay) ? currentVoiceDisplay : voiceOptions.first,
                  isExpanded: true,
                  items: voiceOptions.map((s) => DropdownMenuItem(value: s, child: Text(s))).toList(),
                  onChanged: (s) async {
                    if (s == null) return;
                    final localeId = s == 'System default' ? null : (s.contains(' (') ? s.substring(0, s.indexOf(' (')) : s);
                    await _setVoiceInputLocale(localeId);
                    currentVoiceDisplay = s;
                    setDialogState(() {});
                  },
                ),
                const SizedBox(height: 16),
                Text('Available voice locales (microphone)', style: Theme.of(ctx).textTheme.titleSmall),
                const SizedBox(height: 4),
                Text(
                  voiceLocales.isEmpty ? 'None detected' : voiceLocales.join(', '),
                  style: Theme.of(ctx).textTheme.bodySmall,
                ),
                const SizedBox(height: 16),
                Text('TTS (speak replies)', style: Theme.of(ctx).textTheme.titleSmall),
                const SizedBox(height: 4),
                Text(
                  ttsLanguages.isEmpty ? 'None detected' : ttsLanguages.join(', '),
                  style: Theme.of(ctx).textTheme.bodySmall,
                ),
                const SizedBox(height: 12),
                Text(
                  'Voice input and TTS (speak replies) both use the language selected above. Set it to the language you speak (e.g. 中文 for Chinese). Add more in system settings if needed.',
                  style: Theme.of(ctx).textTheme.bodySmall?.copyWith(color: Theme.of(ctx).colorScheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('OK')),
          ],
        ),
      ),
    );
  }

  /// (category label, example commands). Add these executables in Settings → Exec allowlist first.
  static List<MapEntry<String, List<String>>> _runCommandExamplesByCategory() {
    if (Platform.isMacOS) {
      return [
        const MapEntry('System', ['ls', 'ls -la', 'pwd', 'whoami', 'date', 'say "hello"']),
        const MapEntry('Files & folders', ['open .', 'open ~/Desktop', 'open ~/Downloads']),
        const MapEntry('Browser', ['open https://example.com', 'open -a Safari https://example.com']),
        const MapEntry('Applications', ['open -a Safari', 'open -a Notes', 'open -a "Visual Studio Code"']),
      ];
    }
    if (Platform.isWindows) {
      return [
        const MapEntry('System', ['whoami', 'hostname', 'tasklist', 'where', 'cmd /c dir', 'cmd /c echo hello']),
        const MapEntry('Files & folders', ['explorer .', 'cmd /c start "" "%USERPROFILE%\\Desktop"']),
        const MapEntry('Browser', ['cmd /c start https://example.com']),
        const MapEntry('Applications', ['cmd /c start notepad', 'cmd /c start calc']),
      ];
    }
    if (Platform.isLinux) {
      return [
        const MapEntry('System', ['ls', 'ls -la', 'pwd', 'whoami', 'date', 'uname -a', 'df -h', 'free -h']),
        const MapEntry('Files & folders', ['xdg-open .', 'nautilus .', 'cat /etc/os-release']),
        const MapEntry('Browser', ['xdg-open https://example.com']),
        const MapEntry('Applications', ['xdg-open .']),
      ];
    }
    return [];
  }

  Future<void> _runCommand() async {
    final isDesktop = Platform.isMacOS || Platform.isWindows || Platform.isLinux;
    if (!isDesktop) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Run command is only available on desktop')),
      );
      return;
    }
    if (widget.coreService.execAllowlist.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Add allowed commands in Settings first')),
      );
      return;
    }
    final cmdController = TextEditingController();
    final exampleCategories = _runCommandExamplesByCategory();
    final cmd = await showDialog<String>(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: const Text('Run command'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ExpansionTile(
                  title: Text('How to use', style: Theme.of(ctx).textTheme.titleSmall),
                  initiallyExpanded: true,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(
                        '1. Open Settings → Exec allowlist and add the executable name (e.g. open, ls, cmd) or a regex (e.g. ^/usr/bin/.*).\n'
                        '2. Here, enter the full command and tap Run. Output appears in chat.\n'
                        '3. Tap an example below to fill the field; edit if needed, then Run.',
                        style: Theme.of(ctx).textTheme.bodySmall,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: cmdController,
                  autofocus: true,
                  decoration: InputDecoration(
                    hintText: Platform.isWindows ? 'e.g. cmd /c dir' : 'e.g. ls -la, open .',
                    border: const OutlineInputBorder(),
                  ),
                  onSubmitted: (v) => Navigator.of(ctx).pop(v),
                ),
                ...exampleCategories.expand((entry) => [
                  const SizedBox(height: 10),
                  Text(entry.key, style: Theme.of(ctx).textTheme.labelMedium),
                  const SizedBox(height: 4),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: entry.value.map((ex) => ActionChip(
                      label: Text(ex, style: const TextStyle(fontFamily: 'monospace', fontSize: 11)),
                      onPressed: () => cmdController.text = ex,
                    )).toList(),
                  ),
                ]),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(cmdController.text.trim()),
              child: const Text('Run'),
            ),
          ],
        );
      },
    );
    if (cmd == null || cmd.trim().isEmpty) return;
    if (!widget.coreService.isExecAllowed(cmd)) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Command not in allowlist. Add exact name or regex in Settings.')),
        );
      }
      return;
    }
    final parts = cmd.trim().split(RegExp(r'\s+'));
    final executable = parts.first;
    try {
      final result = await Process.run(
        executable,
        parts.length > 1 ? parts.sublist(1) : [],
        runInShell: false,
      ).timeout(const Duration(seconds: 30));
      final out = (result.stdout is String
          ? (result.stdout as String)
          : utf8.decode(result.stdout as List<int>)).trim();
      final err = (result.stderr is String
          ? (result.stderr as String)
          : utf8.decode(result.stderr as List<int>)).trim();
      final line = 'Exit ${result.exitCode}${out.isNotEmpty ? '\n$out' : ''}${err.isNotEmpty ? '\n$err' : ''}';
      if (mounted) setState(() {
        _messages.add(MapEntry('Run: $cmd\n$line', false));
        _messageImages.add(null);
        _messageAudios.add(null);
        _messageVideos.add(null);
      });
    } catch (e) {
      if (mounted) setState(() {
        _messages.add(MapEntry('Run error: $e', false));
        _messageImages.add(null);
        _messageAudios.add(null);
        _messageVideos.add(null);
      });
    }
  }

  /// Scroll the message list to the bottom so the latest message is visible (and not covered by the keyboard).
  /// Uses jumpTo with a two-frame pass: the first jump triggers lazy item layout which may update
  /// maxScrollExtent, then the second jump lands at the true bottom.
  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;
      _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || !_scrollController.hasClients) return;
        _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
      });
    });
  }

  void _startLoadingStatusTimer() {
    _loadingStatusTimer?.cancel();
    _loadingStatusTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      if (mounted) {
        setState(() => _loadingStatusIndex = (_loadingStatusIndex + 1) % _loadingStatusMessages.length);
      }
    });
  }

  void _stopLoadingStatusTimer() {
    _loadingStatusTimer?.cancel();
    _loadingStatusTimer = null;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _connectionCheckTimer?.cancel();
    _userInboxPollTimer?.cancel();
    _loadingStatusTimer?.cancel();
    _pushMessageSubscription?.cancel();
    _voiceSubscription?.cancel();
    _voice.dispose();
    _voiceRecorder.dispose();
    _inputController.dispose();
    _scrollController.removeListener(_onScrollForPagination);
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isCurrent = ModalRoute.of(context)?.isCurrent ?? false;
    if (isCurrent && !_wasRouteCurrent) {
      _wasRouteCurrent = true;
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        if (mounted && !widget.isUserFriend) await _checkPendingInboundAndRefresh();
        if (mounted) {
          _loadChatHistory();
          setState(() {});
        }
      });
    } else if (!isCurrent) {
      _wasRouteCurrent = false;
    }
    final hasThumbnail = _chatPartnerAvatar != null && _chatPartnerAvatar!.isNotEmpty;
    final hideHomeClawLabel = hasThumbnail && widget.userName.trim().toLowerCase() == 'homeclaw';
    return Scaffold(
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircleAvatar(
              radius: 18,
              backgroundColor: Theme.of(context).colorScheme.primaryContainer,
              backgroundImage: hasThumbnail ? MemoryImage(_chatPartnerAvatar!) : null,
              child: hasThumbnail ? null : Text((widget.userName.isNotEmpty ? widget.userName[0] : '?').toUpperCase(), style: const TextStyle(fontSize: 16)),
            ),
            if (!hideHomeClawLabel) ...[
              const SizedBox(width: 10),
              Flexible(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(widget.userName, overflow: TextOverflow.ellipsis),
                    if (widget.isUserFriend && (widget.remotePeerInstanceId ?? '').trim().isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Chip(
                            avatar: Icon(
                              Icons.cloud_outlined,
                              size: 16,
                              color: Theme.of(context).colorScheme.primary,
                            ),
                            label: Text(
                              'Remote · ${widget.remotePeerInstanceId!.trim()}',
                              style: const TextStyle(fontSize: 11),
                            ),
                            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            visualDensity: VisualDensity.compact,
                            padding: const EdgeInsets.symmetric(horizontal: 6),
                          ),
                        ),
                      ),
                    if (_isDevBridgeFriend && _cursorActiveCwd.trim().isNotEmpty)
                      Text(
                        'Project: ${path.basename(_cursorActiveCwd.trim())}',
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    if (_isDevBridgeFriend &&
                        _devBridgeStoredSessionActive &&
                        (widget.friendId ?? '').trim().toLowerCase() != 'trae')
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Chip(
                            avatar: Icon(
                              Icons.link,
                              size: 16,
                              color: Theme.of(context).colorScheme.primary,
                            ),
                            label: Text(
                              (widget.friendId ?? '').trim().toLowerCase() == 'claudecode'
                                  ? 'Claude session linked'
                                  : 'Cursor session linked',
                              style: const TextStyle(fontSize: 11),
                            ),
                            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            visualDensity: VisualDensity.compact,
                            padding: const EdgeInsets.symmetric(horizontal: 6),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ],
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).pop(),
        ),
        actions: [
          if ((widget.friendId ?? '').trim().toLowerCase() == 'cursor')
            IconButton(
              icon: Icon(_cursorAgentYolo ? Icons.flash_on : Icons.flash_off_outlined),
              tooltip: _cursorAgentYolo
                  ? 'Auto-run Cursor agent (--yolo) ON for this chat'
                  : 'Auto-run OFF (stricter CLI permissions for this chat)',
              color: _cursorAgentYolo ? Theme.of(context).colorScheme.primary : null,
              onPressed: () => _setCursorAgentYolo(!_cursorAgentYolo),
            ),
          if ((widget.friendId ?? '').trim().toLowerCase() == 'claudecode')
            IconButton(
              icon: Icon(_claudeSkipPermissions ? Icons.flash_on : Icons.flash_off_outlined),
              tooltip: _claudeSkipPermissions
                  ? 'Claude Code: --dangerously-skip-permissions ON (full auto-run for this chat)'
                  : 'Claude Code: stricter headless (no skip-permissions for this chat)',
              color: _claudeSkipPermissions ? Theme.of(context).colorScheme.primary : null,
              onPressed: () => _setClaudeSkipPermissions(!_claudeSkipPermissions),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
            child: Center(
              child: Tooltip(
                message: _connectionChecking
                    ? 'Checking connection…'
                    : (_coreConnected == true
                        ? 'Connected to Core (tap to recheck)'
                        : (_coreConnected == false
                            ? 'Not connected to Core. Tap to recheck or open Settings.'
                            : 'Connection unknown')),
                child: Material(
                  type: MaterialType.transparency,
                  child: InkWell(
                    onTap: _checkCoreConnection,
                    borderRadius: BorderRadius.circular(12),
                    child: SizedBox(
                      width: 24,
                      height: 24,
                      child: Center(
                        child: Container(
                          width: 12,
                          height: 12,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: _connectionChecking
                                ? Theme.of(context).colorScheme.outline
                                : (_coreConnected == true
                                    ? Colors.green
                                    : (_coreConnected == false
                                        ? Theme.of(context).colorScheme.error
                                        : Theme.of(context).colorScheme.outline)),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.dashboard_customize),
            tooltip: 'Canvas',
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => CanvasScreen(coreService: widget.coreService),
                ),
              );
            },
          ),
          PopupMenuButton<String>(
            icon: const Icon(Icons.more_vert),
            tooltip: 'More',
            onSelected: (value) async {
              switch (value) {
                case 'photo':
                  await _takePhoto();
                  break;
                case 'video':
                  await _recordVideo();
                  break;
                case 'document':
                  await _attachDocument();
                  break;
                case 'screen':
                  await _recordScreen();
                  break;
                case 'run':
                  await _runCommand();
                  break;
                case 'speak':
                  await _speakLastReply();
                  break;
                case 'stop_tts':
                  await _stopTts();
                  break;
                case 'clear_chat':
                  await _clearChatHistory();
                  break;
                case 'sync_kb':
                  await _syncKnowledgeBase();
                  break;
                default:
                  break;
              }
            },
            itemBuilder: (context) => [
              const PopupMenuItem(value: 'photo', child: Text('Take photo')),
              const PopupMenuItem(value: 'video', child: Text('Record video')),
              const PopupMenuItem(value: 'document', child: Text('Attach file')),
              const PopupMenuItem(value: 'screen', child: Text('Record screen')),
              ...(Platform.isMacOS || Platform.isWindows || Platform.isLinux
                  ? [const PopupMenuItem(value: 'run', child: Text('Run command'))]
                  : []),
              const PopupMenuItem(value: 'speak', child: Text('Speak last reply')),
              const PopupMenuItem(value: 'stop_tts', child: Text('Stop speaking')),
              const PopupMenuItem(value: 'sync_kb', child: Text('Sync knowledge base')),
              const PopupMenuItem(value: 'clear_chat', child: Text('Clear chat history')),
            ],
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => SettingsScreen(coreService: widget.coreService),
                ),
              );
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.all(8),
              itemCount: _messages.length + (_loadingMoreMessages ? 1 : 0),
              itemBuilder: (context, i) {
                if (_loadingMoreMessages && i == 0) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 12),
                    child: Center(child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))),
                  );
                }
                final msgIndex = _loadingMoreMessages ? i - 1 : i;
                final entry = _messages[msgIndex];
                final isUser = entry.value;
                final isErrorBubble = !isUser && entry.key.startsWith('Error:');
                final imageUrls = msgIndex < _messageImages.length ? _messageImages[msgIndex] : null;
                final audioUrls = msgIndex < _messageAudios.length ? _messageAudios[msgIndex] : null;
                final videoUrls = msgIndex < _messageVideos.length ? _messageVideos[msgIndex] : null;
                return Align(
                  alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                  child: GestureDetector(
                    onLongPress: () => _showDeleteMessageConfirmation(context, msgIndex),
                    child: Container(
                      margin: const EdgeInsets.symmetric(vertical: 4),
                      child: ConstrainedBox(
                        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.85),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          decoration: BoxDecoration(
                            color: isUser
                                ? Theme.of(context).colorScheme.primaryContainer
                                : (isErrorBubble
                                    ? Theme.of(context).colorScheme.errorContainer
                                    : Theme.of(context).colorScheme.surfaceContainerHighest),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (imageUrls != null && imageUrls.isNotEmpty)
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 8),
                                  child: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    children: imageUrls
                                        .where((u) => u.startsWith('data:image/'))
                                        .map((imageDataUrl) => Padding(
                                              padding: const EdgeInsets.only(bottom: 6),
                                              child: GestureDetector(
                                                onTap: () {
                                                  Navigator.of(context).push(
                                                    MaterialPageRoute<void>(
                                                      builder: (ctx) => _FullScreenImagePage(imageDataUrl: imageDataUrl),
                                                    ),
                                                  );
                                                },
                                                child: ClipRRect(
                                                  borderRadius: BorderRadius.circular(8),
                                                  child: Image.memory(
                                                    base64Decode(imageDataUrl.contains(',') ? imageDataUrl.split(',').last : ''),
                                                    fit: BoxFit.contain,
                                                    width: 280,
                                                    errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                                                  ),
                                                ),
                                              ),
                                            ))
                                        .toList(),
                                  ),
                                ),
                              if (audioUrls != null && audioUrls.isNotEmpty)
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 8),
                                  child: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: audioUrls
                                        .map((audioDataUrl) => Padding(
                                              padding: const EdgeInsets.only(bottom: 6),
                                              child: _AudioPlayButton(dataUrl: audioDataUrl),
                                            ))
                                        .toList(),
                                  ),
                                ),
                              if (videoUrls != null && videoUrls.isNotEmpty)
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 8),
                                  child: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: videoUrls
                                        .map((videoDataUrl) => Padding(
                                              padding: const EdgeInsets.only(bottom: 6),
                                              child: _VideoPlayChip(dataUrl: videoDataUrl),
                                            ))
                                        .toList(),
                                  ),
                                ),
                              _ChatMessageText(
                                text: entry.key,
                                isUser: isUser,
                                plainText: _isDevBridgeFriend && widget.coreService.cursorChatPlainText,
                                theme: Theme.of(context),
                                isErrorMessage: isErrorBubble,
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
          if (_isDevBridgeFriend && _interactiveSessionId != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceVariant.withOpacity(0.6),
                border: Border(
                  top: BorderSide(color: Theme.of(context).dividerColor),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Interactive console',
                        style: Theme.of(context).textTheme.labelSmall,
                      ),
                      IconButton(
                        icon: const Icon(Icons.refresh, size: 18),
                        tooltip: 'Refresh output',
                        onPressed: _refreshInteractiveOutput,
                      ),
                    ],
                  ),
                  Container(
                    constraints: const BoxConstraints(maxHeight: 160),
                    width: double.infinity,
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: Colors.black,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: SingleChildScrollView(
                      child: Text(
                        _interactiveOutput.isEmpty ? '(no output yet)' : _interactiveOutput,
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 12,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _interactiveInputController,
                          decoration: const InputDecoration(
                            isDense: true,
                            hintText: 'Type command or input…',
                          ),
                          onSubmitted: (_) => _sendInteractiveInput(),
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.send, size: 18),
                        onPressed: _sendInteractiveInput,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          if (_loading)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                  ),
                  const SizedBox(width: 10),
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 200),
                    child: Text(
                      _loadingMessage != null && _loadingMessage!.isNotEmpty
                          ? _loadingMessage!
                          : (_loadingStatusMessages.isEmpty ? '…' : _loadingStatusMessages[_loadingStatusIndex % _loadingStatusMessages.length]),
                      key: ValueKey<String>(
                        _loadingMessage ?? (_loadingStatusMessages.isEmpty ? '…' : _loadingStatusMessages[_loadingStatusIndex % _loadingStatusMessages.length]),
                      ),
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                  if (widget.coreService.ongoingInboundRequestId != null) ...[
                    const SizedBox(width: 12),
                    TextButton(
                      onPressed: () async {
                        await widget.coreService.cancelOngoingRequest();
                      },
                      child: const Text('Cancel'),
                    ),
                  ],
                ],
              ),
            ),
          if (_voiceListening)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              child: Material(
                color: Theme.of(context).colorScheme.primaryContainer.withOpacity(0.5),
                borderRadius: BorderRadius.circular(12),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  child: Row(
                    children: [
                      Icon(
                        Icons.mic,
                        color: Theme.of(context).colorScheme.primary,
                        size: 28,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              _voiceTranscript.isEmpty ? 'Listening...' : 'Speaking',
                              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                                    color: Theme.of(context).colorScheme.primary,
                                  ),
                            ),
                            if (_voiceTranscript.isNotEmpty)
                              Padding(
                                padding: const EdgeInsets.only(top: 4),
                                child: Text(
                                  _voiceTranscript,
                                  style: Theme.of(context).textTheme.bodyMedium,
                                ),
                              ),
                          ],
                        ),
                      ),
                      TextButton.icon(
                        onPressed: _cancelVoiceInput,
                        icon: const Icon(Icons.cancel_outlined),
                        label: const Text('Cancel'),
                      ),
                      TextButton.icon(
                        onPressed: _stopVoiceAndSend,
                        icon: const Icon(Icons.stop_circle),
                        label: const Text('Stop'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          if (_ttsSpeaking)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              child: Material(
                color: Theme.of(context).colorScheme.secondaryContainer.withOpacity(0.5),
                borderRadius: BorderRadius.circular(12),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  child: Row(
                    children: [
                      Icon(
                        Icons.volume_up,
                        color: Theme.of(context).colorScheme.onSecondaryContainer,
                        size: 28,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          'Speaking reply…',
                          style: Theme.of(context).textTheme.labelLarge?.copyWith(
                                color: Theme.of(context).colorScheme.onSecondaryContainer,
                              ),
                        ),
                      ),
                      TextButton.icon(
                        onPressed: _stopTts,
                        icon: const Icon(Icons.stop_circle),
                        label: const Text('Stop'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          if (_pendingImagePaths.isNotEmpty || _pendingVideoPaths.isNotEmpty || _pendingFilePaths.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      Text(
                        'Attached — add a message below (optional), then Send',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Theme.of(context).colorScheme.primary,
                        ),
                      ),
                      const Spacer(),
                      TextButton(
                        onPressed: () => setState(() {
                          _pendingImagePaths.clear();
                          _pendingVideoPaths.clear();
                          _pendingFilePaths.clear();
                        }),
                        child: const Text('Clear all'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        ..._pendingImagePaths.map((p) => Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: Stack(
                            clipBehavior: Clip.none,
                            children: [
                              SizedBox(
                                width: 64,
                                height: 64,
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(8),
                                  child: Image.file(
                                    File(p),
                                    fit: BoxFit.cover,
                                    width: 64,
                                    height: 64,
                                    frameBuilder: (_, child, frame, __) {
                                      if (frame == null) {
                                        return Container(
                                          width: 64,
                                          height: 64,
                                          color: Theme.of(context).colorScheme.surfaceContainerHighest,
                                          child: const Center(child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))),
                                        );
                                      }
                                      return child;
                                    },
                                    errorBuilder: (_, __, ___) => Container(
                                      width: 64,
                                      height: 64,
                                      color: Theme.of(context).colorScheme.surfaceContainerHighest,
                                      child: Icon(Icons.broken_image_outlined, color: Theme.of(context).colorScheme.outline),
                                    ),
                                  ),
                                ),
                              ),
                              Positioned(
                                top: -4,
                                right: -4,
                                child: Material(
                                  color: Theme.of(context).colorScheme.errorContainer,
                                  shape: const CircleBorder(),
                                  child: InkWell(
                                    onTap: () => setState(() => _pendingImagePaths.remove(p)),
                                    customBorder: const CircleBorder(),
                                    child: const SizedBox(width: 22, height: 22, child: Icon(Icons.close, size: 16)),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        )),
                        ..._pendingVideoPaths.map((p) => Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: _AttachmentChip(
                            icon: Icons.videocam,
                            label: path.basename(p),
                            onRemove: () => setState(() => _pendingVideoPaths.remove(p)),
                          ),
                        )),
                        ..._pendingFilePaths.map((p) => Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: _AttachmentChip(
                            icon: Icons.insert_drive_file,
                            label: path.basename(p),
                            onRemove: () => setState(() => _pendingFilePaths.remove(p)),
                          ),
                        )),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8.0, vertical: 4.0),
            child: Row(
              children: [
                Icon(Icons.volume_up, size: 20, color: Theme.of(context).colorScheme.onSurfaceVariant),
                const SizedBox(width: 6),
                Text('Speak replies', style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(width: 8),
                Switch(
                  value: _ttsAutoSpeak,
                  onChanged: (value) => _setTtsAutoSpeak(value),
                ),
                if (_ttsSpeaking)
                  Padding(
                    padding: const EdgeInsets.only(left: 8.0),
                    child: FilledButton.tonalIcon(
                      onPressed: _stopTts,
                      icon: const Icon(Icons.stop_circle, size: 20),
                      label: const Text('Stop speaking'),
                    ),
                  ),
                IconButton(
                  icon: const Icon(Icons.info_outline, size: 20),
                  tooltip: 'Voice input & TTS supported languages',
                  onPressed: _showVoiceAndTtsLanguages,
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Row(
              children: [
                if (widget.isUserFriend)
                  GestureDetector(
                    onLongPressStart: (_) => _startPushToTalk(),
                    onLongPressEnd: (_) => _stopPushToTalkAndSend(),
                    child: IconButton(
                      onPressed: null,
                      icon: Icon(
                        _recordingPushToTalk ? Icons.stop : Icons.keyboard_voice,
                        color: _recordingPushToTalk ? Theme.of(context).colorScheme.error : null,
                      ),
                      tooltip: _recordingPushToTalk ? 'Recording… release to send' : 'Hold to talk',
                    ),
                  ),
                if (widget.isUserFriend) const SizedBox(width: 4),
                IconButton(
                  onPressed: _loading ? null : _toggleVoice,
                  icon: Icon(
                    _voiceListening ? Icons.mic : Icons.mic_none,
                    color: _voiceListening ? Theme.of(context).colorScheme.primary : null,
                  ),
                  tooltip: _voiceListening ? 'Stop voice input' : 'Voice input',
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: TextField(
                    controller: _inputController,
                    decoration: InputDecoration(
                      hintText: (_pendingImagePaths.isNotEmpty || _pendingVideoPaths.isNotEmpty || _pendingFilePaths.isNotEmpty)
                          ? 'Add a message (optional)'
                          : 'Message',
                      border: const OutlineInputBorder(),
                    ),
                    onSubmitted: (_) => _send(),
                  ),
                ),
                if (_ttsSpeaking) ...[
                  const SizedBox(width: 4),
                  IconButton(
                    onPressed: _stopTts,
                    icon: const Icon(Icons.stop_circle),
                    tooltip: 'Stop speaking',
                    style: IconButton.styleFrom(
                      foregroundColor: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ],
                const SizedBox(width: 8),
                IconButton.filled(
                  onPressed: _loading
                      ? null
                      : () => _send(),
                  icon: const Icon(Icons.send),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Chip showing one attached video or document with remove button.
class _AttachmentChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onRemove;

  const _AttachmentChip({required this.icon, required this.label, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SizedBox(
      height: 64,
      child: Material(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          onTap: null,
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: const EdgeInsets.only(left: 10, right: 4, top: 8, bottom: 8),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, size: 28, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 120),
                  child: Text(
                    label,
                    style: theme.textTheme.bodySmall,
                    overflow: TextOverflow.ellipsis,
                    maxLines: 2,
                  ),
                ),
                const SizedBox(width: 4),
                Material(
                  color: theme.colorScheme.errorContainer,
                  shape: const CircleBorder(),
                  child: InkWell(
                    onTap: onRemove,
                    customBorder: const CircleBorder(),
                    child: const SizedBox(width: 22, height: 22, child: Icon(Icons.close, size: 16)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Renders chat message text as Markdown (bold, lists, code, links, etc.) with selectable text and tappable links.
class _ChatMessageText extends StatelessWidget {
  final String text;
  final bool isUser;
  final bool plainText;
  final ThemeData theme;
  /// High-contrast text on [ColorScheme.errorContainer] bubbles (e.g. connection errors).
  final bool isErrorMessage;

  const _ChatMessageText({
    required this.text,
    required this.isUser,
    required this.plainText,
    required this.theme,
    this.isErrorMessage = false,
  });

  /// File extensions that should open with system default app (e.g. PPT, PDF, DOC).
  static const List<String> _fileExtensions = [
    'ppt', 'pptx', 'pdf', 'doc', 'docx', 'xls', 'xlsx',
    'odt', 'ods', 'odp', 'rtf', 'txt', 'csv', 'zip',
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mp3',
  ];

  static bool _isFileLink(String href) {
    final lower = href.toLowerCase().trim();
    if (lower.startsWith('file:')) return true;
    if (lower.startsWith('http:') || lower.startsWith('https:')) {
      final path = Uri.tryParse(href)?.path ?? '';
      final ext = path.contains('.') ? path.split('.').last.toLowerCase() : '';
      return ext.isNotEmpty && _fileExtensions.contains(ext);
    }
    return false;
  }

  Future<void> _onTapLink(String text, String? href, String title) async {
    if (href == null || href.isEmpty) return;
    Uri? uri = Uri.tryParse(href);
    if (uri == null) return;
    try {
      final isFile = _isFileLink(href);
      if (isFile && uri.scheme == 'file') {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
        return;
      }
      if (isFile && (uri.scheme == 'http' || uri.scheme == 'https')) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
        return;
      }
      if (uri.scheme == 'http' || uri.scheme == 'https') {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
        return;
      }
      if (uri.scheme.isEmpty && (RegExp(r'^[A-Za-z]:[/\\]').hasMatch(href) || href.startsWith('/'))) {
        final fileUri = Uri.file(href);
        if (await canLaunchUrl(fileUri)) {
          await launchUrl(fileUri, mode: LaunchMode.externalApplication);
        }
        return;
      }
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      }
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final effectiveText = text.isEmpty ? '\u200B' : text;
    final errorFg = isErrorMessage ? theme.colorScheme.onErrorContainer : null;
    if (plainText) {
      return SelectableText(
        effectiveText,
        style: theme.textTheme.bodyLarge?.copyWith(color: errorFg),
      );
    }
    final bodyLarge = theme.textTheme.bodyLarge;
    final bodyMedium = theme.textTheme.bodyMedium;
    final pStyle = errorFg != null ? bodyLarge?.copyWith(color: errorFg) : bodyLarge;
    final styleSheet = MarkdownStyleSheet.fromTheme(theme).copyWith(
      p: pStyle,
      listBullet: pStyle,
      h1: errorFg != null ? theme.textTheme.headlineSmall?.copyWith(color: errorFg) : theme.textTheme.headlineSmall,
      h2: errorFg != null ? theme.textTheme.titleLarge?.copyWith(color: errorFg) : theme.textTheme.titleLarge,
      h3: errorFg != null ? theme.textTheme.titleMedium?.copyWith(color: errorFg) : theme.textTheme.titleMedium,
      code: bodyMedium?.copyWith(
        fontFamily: 'monospace',
        color: errorFg ?? bodyMedium.color,
        backgroundColor: theme.colorScheme.surfaceContainerHighest,
      ),
      codeblockDecoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
      ),
      blockquote: theme.textTheme.bodyMedium?.copyWith(
        color: errorFg ?? theme.colorScheme.onSurfaceVariant,
      ),
      blockquoteDecoration: BoxDecoration(
        border: Border(
          left: BorderSide(
            color: errorFg ?? theme.colorScheme.primary,
            width: 4,
          ),
        ),
      ),
    );
    return MarkdownBody(
      data: effectiveText,
      selectable: true,
      styleSheet: styleSheet,
      onTapLink: _onTapLink,
      softLineBreak: true,
      shrinkWrap: true,
      fitContent: true,
    );
  }
}

/// Chip that opens full-screen video player for a video data URL (user-to-user short video).
class _VideoPlayChip extends StatelessWidget {
  final String dataUrl;

  const _VideoPlayChip({required this.dataUrl});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        onTap: () {
          Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (ctx) => _FullScreenVideoPage(dataUrl: dataUrl),
            ),
          );
        },
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.videocam, color: Theme.of(context).colorScheme.primary),
              const SizedBox(width: 8),
              Text('Video', style: Theme.of(context).textTheme.labelLarge),
              const SizedBox(width: 4),
              const Icon(Icons.play_circle_fill, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}

/// Full-screen video player for a data URL. Writes to temp file and plays with video_player.
class _FullScreenVideoPage extends StatefulWidget {
  final String dataUrl;

  const _FullScreenVideoPage({required this.dataUrl});

  @override
  State<_FullScreenVideoPage> createState() => _FullScreenVideoPageState();
}

class _FullScreenVideoPageState extends State<_FullScreenVideoPage> {
  VideoPlayerController? _controller;
  String? _error;

  @override
  void initState() {
    super.initState();
    _initPlayer();
  }

  Future<void> _initPlayer() async {
    if (widget.dataUrl.isEmpty || !widget.dataUrl.contains(',')) {
      if (mounted) setState(() => _error = 'Invalid video');
      return;
    }
    try {
      final b64 = widget.dataUrl.split(',').last;
      final bytes = base64Decode(b64);
      final dir = await getTemporaryDirectory();
      final ext = widget.dataUrl.contains('webm') ? 'webm' : 'mp4';
      final file = File(path.join(dir.path, 'video_${DateTime.now().millisecondsSinceEpoch}.$ext'));
      await file.writeAsBytes(bytes);
      if (!mounted) return;
      _controller = VideoPlayerController.file(file);
      await _controller!.initialize();
      if (mounted) setState(() {});
      _controller!.play();
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not play: $e');
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('Video'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: _error != null
          ? Center(child: Text(_error!, style: const TextStyle(color: Colors.white)))
          : _controller == null || !_controller!.value.isInitialized
              ? const Center(child: CircularProgressIndicator(color: Colors.white))
              : Center(
                  child: AspectRatio(
                    aspectRatio: _controller!.value.aspectRatio,
                    child: VideoPlayer(_controller!),
                  ),
                ),
    );
  }
}

/// Play button for a voice message (audio data URL). Writes to temp file and plays with audioplayers.
class _AudioPlayButton extends StatefulWidget {
  final String dataUrl;

  const _AudioPlayButton({required this.dataUrl});

  @override
  State<_AudioPlayButton> createState() => _AudioPlayButtonState();
}

class _AudioPlayButtonState extends State<_AudioPlayButton> {
  final AudioPlayer _player = AudioPlayer();
  bool _playing = false;
  StreamSubscription<void>? _completeSub;

  @override
  void dispose() {
    _completeSub?.cancel();
    _player.dispose();
    super.dispose();
  }

  Future<void> _play() async {
    if (widget.dataUrl.isEmpty || !widget.dataUrl.contains(',')) return;
    try {
      final b64 = widget.dataUrl.split(',').last;
      final bytes = base64Decode(b64);
      final dir = await getTemporaryDirectory();
      final mime = widget.dataUrl.startsWith('data:') ? widget.dataUrl.split(';').first.replaceFirst('data:', '') : 'audio';
      final ext = mime == 'audio/webm' ? 'webm' : (mime == 'audio/ogg' ? 'ogg' : 'webm');
      final file = File(path.join(dir.path, 'voice_${DateTime.now().millisecondsSinceEpoch}.$ext'));
      await file.writeAsBytes(bytes);
      _completeSub?.cancel();
      _completeSub = _player.onPlayerComplete.listen((_) {
        if (mounted) setState(() => _playing = false);
      });
      await _player.play(DeviceFileSource(file.path));
      if (mounted) setState(() => _playing = true);
    } catch (_) {
      if (mounted) ScaffoldMessenger.maybeOf(context)?.showSnackBar(const SnackBar(content: Text('Could not play audio')));
    }
  }

  Future<void> _stop() async {
    await _player.stop();
    if (mounted) setState(() => _playing = false);
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          icon: Icon(_playing ? Icons.stop : Icons.play_arrow),
          onPressed: _playing ? _stop : _play,
          tooltip: _playing ? 'Stop' : 'Play voice message',
        ),
        Text('Voice message', style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}

/// Full-screen image viewer. Tap anywhere to go back.
class _FullScreenImagePage extends StatelessWidget {
  final String imageDataUrl;

  const _FullScreenImagePage({required this.imageDataUrl});

  @override
  Widget build(BuildContext context) {
    final bytes = imageDataUrl.contains(',')
        ? base64Decode(imageDataUrl.split(',').last)
        : <int>[];
    return Scaffold(
      backgroundColor: Colors.black,
      body: GestureDetector(
        onTap: () => Navigator.of(context).pop(),
        behavior: HitTestBehavior.opaque,
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (bytes.isNotEmpty)
              Center(
                child: InteractiveViewer(
                  minScale: 0.5,
                  maxScale: 4.0,
                  child: Image.memory(
                    Uint8List.fromList(bytes),
                    fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => const Center(child: Icon(Icons.broken_image, color: Colors.white54, size: 64)),
                  ),
                ),
              )
            else
              const Center(child: Icon(Icons.broken_image, color: Colors.white54, size: 64)),
            SafeArea(
              child: Align(
                alignment: Alignment.topRight,
                child: IconButton(
                  icon: const Icon(Icons.close, color: Colors.white, size: 28),
                  onPressed: () => Navigator.of(context).pop(),
                  tooltip: 'Close',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
