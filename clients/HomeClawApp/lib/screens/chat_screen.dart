import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' show max;
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:path/path.dart' as path;
import 'package:flutter_tts/flutter_tts.dart';
import 'package:homeclaw_native/homeclaw_native.dart';
import 'package:homeclaw_voice/homeclaw_voice.dart';
import 'package:file_picker/file_picker.dart';
import 'package:image/image.dart' as img;
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
import 'clawcode_screen.dart';
import 'settings_screen.dart';
import 'vmprint_preview_screen.dart';
import '../utils/product_preset_chat.dart';

double? _parseTranscriptTimestampSeconds(Map<String, dynamic> m) {
  final t = m['timestamp'];
  if (t == null) return null;
  if (t is num) return t.toDouble();
  final s = t.toString().trim();
  if (s.isEmpty) return null;
  final asNum = double.tryParse(s);
  if (asNum != null) return asNum;
  try {
    return DateTime.parse(s).millisecondsSinceEpoch / 1000.0;
  } catch (_) {
    return null;
  }
}

Uint8List? _decodeDataUrlToBytes(String dataUrl) {
  final comma = dataUrl.indexOf(',');
  if (comma < 0) return null;
  try {
    final b64 = dataUrl.substring(comma + 1).replaceAll(RegExp(r'\s'), '');
    return base64Decode(b64);
  } catch (_) {
    return null;
  }
}

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
  /// Core preset key for this AI friend (e.g. `cursor`, `claudecode`, `clawcode`) from GET /api/me/friends.
  final String? friendPreset;

  /// Resolved product preset (reminder / finder / knowledge) for quick actions; null if unknown.
  String? get resolvedProductPresetKey =>
      resolveProductPresetKey(preset: friendPreset, friendName: friendId);

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
    this.friendPreset,
  });

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with WidgetsBindingObserver {
  final List<MapEntry<String, bool>> _messages = [];
  /// Optional image data URLs per message (same index as _messages; null or empty when no images).
  final List<List<String>?> _messageImages = [];
  /// Voice / audio refs per message: local path, data:, http(s), or /files/... (same index as _messages).
  final List<List<String>?> _messageAudios = [];
  /// Optional video data URLs per message (same index as _messages; for user-to-user short video).
  final List<List<String>?> _messageVideos = [];
  /// File attachment display names per message (same index as _messages); for outgoing upload UX and thread file_links.
  final List<List<String>?> _messageFileLabels = [];
  /// Parallel to [_messageFileLabels]: paths or URLs to open (local path, http(s), /files/...).
  final List<List<String>?> _messageFileRefs = [];
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  bool _autoFollowBottom = true;
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
  String? _lastUserInboxThreadFingerprint;
  Timer? _userInboxApplyDebounceTimer;
  List<dynamic>? _pendingUserInboxList;
  String? _pendingUserInboxFingerprint;
  double? _userInboxHideBeforeTs;
  /// After "Clear chat" on AI threads: hide Core transcript rows at or before this time until new messages arrive.
  double? _aiChatHideBeforeTs;
  /// Bumps on each inbox fetch so stale async applies cannot overwrite newer UI.
  int _userInboxFetchGeneration = 0;
  StreamSubscription<Map<String, dynamic>>? _pushMessageSubscription;
  /// Push-to-talk (user friends only): true while recording.
  bool _recordingPushToTalk = false;
  final AudioRecorder _voiceRecorder = AudioRecorder();
  int? _activeUserSendBubbleIndex;
  String? _activeUserSendStage;

  String _inboxHidePrefKey() =>
      'companion_inbox_hide_v1_${widget.userId.trim()}_${(widget.toUserId ?? '').trim()}';

  String _aiChatHidePrefKey() =>
      'companion_ai_hide_v1_${widget.userId.trim()}_${(widget.friendId ?? '').trim()}';

  Future<void> _bootstrapUserFriendInbox() async {
    final tid = widget.toUserId?.trim();
    if (tid == null || tid.isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    final ts = prefs.getDouble(_inboxHidePrefKey());
    if (!mounted) return;
    if (ts != null) {
      setState(() => _userInboxHideBeforeTs = ts);
    }
    await _loadUserInbox();
  }

  Future<void> _bootstrapAiChatScreen() async {
    final prefs = await SharedPreferences.getInstance();
    final ts = prefs.getDouble(_aiChatHidePrefKey());
    if (!mounted) return;
    if (ts != null) {
      setState(() => _aiChatHideBeforeTs = ts);
    }
    _loadChatHistory();
    await _syncChatHistoryFromCore();
    if (mounted) await _checkPendingInboundAndRefresh();
  }

  static String _userSendInitialStage({
    required bool hasImages,
    required bool hasVideos,
    required bool hasFiles,
  }) {
    if (hasImages) return 'Preparing image...';
    if (hasVideos) return 'Preparing video...';
    if (hasFiles) return 'Preparing attachment...';
    return 'Sending...';
  }

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

  /// Claw-Code session UUID when chatting with the preset friend `clawcode` (same pattern as Cursor/ClaudeCode: dedicated friend on HomeClaw).
  String? _clawcodeSessionId;

  bool get _isClawcodePresetFriend =>
      !widget.isUserFriend && (widget.friendPreset ?? '').trim().toLowerCase() == 'clawcode';

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

  Future<void> _showActiveProjectPathDialog() async {
    final full = _cursorActiveCwd.trim();
    if (full.isEmpty || !mounted) return;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Active project'),
        content: SingleChildScrollView(
          child: SelectableText(
            full,
            style: const TextStyle(fontSize: 13),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: full));
              if (!ctx.mounted) return;
              Navigator.of(ctx).pop();
              if (!mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Project path copied')),
              );
            },
            child: const Text('Copy'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
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
      unawaited(_bootstrapUserFriendInbox());
      _userInboxPollTimer = Timer.periodic(const Duration(seconds: 5), (_) {
        if (mounted && widget.isUserFriend && widget.toUserId != null) _loadUserInbox(fromPoll: true);
      });
    } else {
      unawaited(_bootstrapAiChatScreen());
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
    unawaited(_loadClawcodeChatBinding());
  }

  String _clawcodePresetSessionPrefKey() => 'companion_clawcode_session_v1_${widget.userId.trim()}';

  Future<void> _loadClawcodeChatBinding() async {
    if (!_isClawcodePresetFriend) return;
    try {
      final p = await SharedPreferences.getInstance();
      final sid = p.getString(_clawcodePresetSessionPrefKey())?.trim();
      if (!mounted) return;
      setState(() => _clawcodeSessionId = (sid != null && sid.isNotEmpty) ? sid : null);
    } catch (_) {}
  }

  Future<void> _setClawcodeChatBinding(String? sessionId) async {
    if (!_isClawcodePresetFriend) return;
    try {
      final p = await SharedPreferences.getInstance();
      final key = _clawcodePresetSessionPrefKey();
      if (sessionId == null || sessionId.trim().isEmpty) {
        await p.remove(key);
        if (mounted) setState(() => _clawcodeSessionId = null);
      } else {
        final t = sessionId.trim();
        await p.setString(key, t);
        if (mounted) setState(() => _clawcodeSessionId = t);
      }
    } catch (_) {}
  }

  String _shortClawcodeId(String sid) {
    final t = sid.trim();
    if (t.length <= 10) return t;
    return '${t.substring(0, 8)}…';
  }

  Future<void> _showClawcodeSessionPicker() async {
    if (!_isClawcodePresetFriend) return;
    final owner = (widget.coreService.sessionUserId?.trim().isNotEmpty ?? false)
        ? widget.coreService.sessionUserId!.trim()
        : widget.userId.trim();
    List<Map<String, dynamic>> sessions = [];
    String? loadErr;
    try {
      sessions = await widget.coreService.fetchClawcodeSessions(owner);
    } catch (e) {
      loadErr = e.toString().replaceFirst(RegExp(r'^Exception:?\s*'), '');
    }
    if (!mounted) return;
    final bound = _clawcodeSessionId;
    final sheetH = MediaQuery.sizeOf(context).height * 0.55;
    await showModalBottomSheet<void>(
      context: context,
      builder: (ctx) {
        return SafeArea(
          child: SizedBox(
            height: sheetH,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(8, 12, 8, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('Claw-Code', style: Theme.of(ctx).textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Text(
                    'Clawcode friend: pick a workspace session for POST /inbound (clawcode_session_id). Core only.',
                    style: Theme.of(ctx).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 12),
                  if (loadErr != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(loadErr, style: TextStyle(color: Theme.of(ctx).colorScheme.error, fontSize: 13)),
                    ),
                  Expanded(
                    child: ListView(
                      children: [
                        RadioListTile<String?>(
                          title: const Text('Off — normal chat'),
                          value: null,
                          groupValue: bound,
                          onChanged: (_) async {
                            await _setClawcodeChatBinding(null);
                            if (ctx.mounted) Navigator.pop(ctx);
                          },
                        ),
                        if (sessions.isEmpty && loadErr == null)
                          const Padding(
                            padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                            child: Text(
                              'No sessions yet. Create one on the server (e.g. python3 -m main clawcode session new), then pick it here. For approvals, workspace files, or optional browser UI, use the button below.',
                              style: TextStyle(fontSize: 13),
                            ),
                          ),
                        ...sessions.map((s) {
                          final sid = (s['clawcode_session_id'] ?? '').toString();
                          if (sid.isEmpty) return const SizedBox.shrink();
                          final cwd = (s['cwd'] ?? '').toString();
                          return RadioListTile<String>(
                            title: Text(_shortClawcodeId(sid)),
                            subtitle: cwd.isNotEmpty
                                ? Text(cwd, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12))
                                : null,
                            value: sid,
                            groupValue: bound,
                            onChanged: (_) async {
                              await _setClawcodeChatBinding(sid);
                              if (ctx.mounted) Navigator.pop(ctx);
                            },
                          );
                        }),
                      ],
                    ),
                  ),
                  TextButton.icon(
                    onPressed: () {
                      Navigator.pop(ctx);
                      final fid = widget.friendId?.trim();
                      Navigator.push<void>(
                        context,
                        MaterialPageRoute<void>(
                          builder: (c) => ClawcodeScreen(
                            coreService: widget.coreService,
                            chatFriendId: (fid != null && fid.isNotEmpty) ? fid : null,
                          ),
                        ),
                      );
                    },
                    icon: const Icon(Icons.open_in_new, size: 18),
                    label: const Text('Approvals, workspace, browser…'),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  void _onScrollForPagination() {
    if (_scrollController.hasClients) {
      final pos = _scrollController.position;
      _autoFollowBottom = (pos.maxScrollExtent - pos.pixels) <= 140;
    }
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
      var list = await widget.coreService.getChatHistory(
        userId: widget.userId,
        friendId: friendId,
        limit: _pageSize,
        offset: _chatHistoryOffset + _messages.length,
      );
      if (!mounted) return;
      if (_aiChatHideBeforeTs != null) {
        list = list.where((m) {
          final ts = _parseTranscriptTimestampSeconds(m);
          return ts == null || ts > _aiChatHideBeforeTs!;
        }).toList();
      }
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
      final olderFileLabels = <List<String>?>[];
      final olderFileRefs = <List<String>?>[];
      for (final m in list) {
        final role = ((m['role']?.toString()) ?? '').trim().toLowerCase();
        final content = ((m['content']?.toString()) ?? '').trim();
        older.add(MapEntry(content.isEmpty ? '(empty)' : content, role == 'user'));
        olderImages.add(null);
        olderAudios.add(null);
        olderVideos.add(null);
        olderFileLabels.add(null);
        olderFileRefs.add(null);
      }
      final prevMax = _scrollController.position.maxScrollExtent;
      setState(() {
        _messages.insertAll(0, older);
        _messageImages.insertAll(0, olderImages);
        _messageAudios.insertAll(0, olderAudios);
        _messageVideos.insertAll(0, olderVideos);
        _messageFileLabels.insertAll(0, olderFileLabels);
        _messageFileRefs.insertAll(0, olderFileRefs);
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
      _messageFileLabels.clear();
      _messageFileRefs.clear();
      for (final e in loaded) {
        _messages.add(e.key);
        _messageImages.add(e.value);
        _messageAudios.add(null);
        _messageVideos.add(null);
        _messageFileLabels.add(null);
        _messageFileRefs.add(null);
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
      var filtered = list;
      if (_aiChatHideBeforeTs != null) {
        filtered = list.where((m) {
          final ts = _parseTranscriptTimestampSeconds(m);
          return ts == null || ts > _aiChatHideBeforeTs!;
        }).toList();
      }
      if (filtered.isEmpty) {
        if (!mounted) return;
        setState(() {
          _messages.clear();
          _messageImages.clear();
          _messageAudios.clear();
          _messageVideos.clear();
          _messageFileLabels.clear();
          _messageFileRefs.clear();
          _chatHistoryOffset = 0;
          _hasMoreMessages = list.length >= _pageSize;
        });
        return;
      }
      final messages = <MapEntry<String, bool>>[];
      final images = <List<String>?>[];
      final audios = <List<String>?>[];
      final videos = <List<String>?>[];
      for (final m in filtered) {
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
        _messageFileLabels.clear();
        _messageFileRefs.clear();
        _messages.addAll(messages);
        _messageImages.addAll(images);
        _messageAudios.addAll(audios);
        _messageVideos.addAll(videos);
        _messageFileLabels.addAll(List<List<String>?>.filled(messages.length, null));
        _messageFileRefs.addAll(List<List<String>?>.filled(messages.length, null));
        _chatHistoryOffset = 0;
        _hasMoreMessages = list.length >= _pageSize;
      });
      _scrollToBottom();
    } catch (_) {
      // Keep local history on failure (e.g. offline)
    }
  }

  /// Load full thread (both directions) from GET /api/user-inbox/thread so sent messages do not disappear on poll.
  Future<void> _loadUserInbox({bool fromPoll = false}) async {
    if (widget.toUserId == null || widget.toUserId!.trim().isEmpty) return;
    // Only polled loads use [generation]: a timer tick must not cancel bootstrap / resume fetches.
    final pollGen = fromPoll ? ++_userInboxFetchGeneration : -1;
    try {
      final data = await widget.coreService.getUserInboxThread(
        userId: widget.userId,
        otherUserId: widget.toUserId!,
        limit: 100,
      );
      if (!mounted) return;
      if (pollGen >= 0 && pollGen != _userInboxFetchGeneration) return;
      final list = data['messages'] as List<dynamic>?;
      if (list == null) return;
      final fingerprint = _fingerprintUserInboxThread(list);
      if (fingerprint == _lastUserInboxThreadFingerprint) {
        return; // No data change: avoid rebuild/scroll flash on polling.
      }
      if (fromPoll) {
        _pendingUserInboxList = List<dynamic>.from(list);
        _pendingUserInboxFingerprint = fingerprint;
        _userInboxApplyDebounceTimer?.cancel();
        _userInboxApplyDebounceTimer = Timer(const Duration(milliseconds: 200), () {
          if (!mounted || pollGen != _userInboxFetchGeneration) return;
          final pendingList = _pendingUserInboxList;
          final pendingFingerprint = _pendingUserInboxFingerprint;
          _pendingUserInboxList = null;
          _pendingUserInboxFingerprint = null;
          if (pendingList == null || pendingFingerprint == null) return;
          _lastUserInboxThreadFingerprint = pendingFingerprint;
          unawaited(_applyUserInboxList(pendingList, pollGeneration: pollGen));
        });
        return;
      }
      _lastUserInboxThreadFingerprint = fingerprint;
      await _applyUserInboxList(list);
    } catch (e) {
      if (mounted) setState(() {});
      if (mounted && !fromPoll) {
        final msg = e.toString();
        final short = msg.length > 200 ? '${msg.substring(0, 200)}…' : msg;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not load chat: $short')),
        );
      }
    }
  }

  /// [pollGeneration] when >= 0: abandon apply if a newer poll started. Omit for direct loads (bootstrap, resume).
  Future<void> _applyUserInboxList(List<dynamic> list, {int pollGeneration = -1}) async {
    if (!mounted) return;
    if (pollGeneration >= 0 && pollGeneration != _userInboxFetchGeneration) return;
    var effectiveList = _userInboxHideBeforeTs == null
        ? list
        : list.where((m) {
            if (m is! Map) return false;
            final raw = m['created_at'];
            final at = raw is num
                ? raw.toDouble()
                : (raw is String ? double.tryParse(raw) ?? 0.0 : 0.0);
            return at > _userInboxHideBeforeTs!;
          }).toList();
    // If some rows should pass the hide filter (max created_at > cutoff) but none did, timestamps
    // or parsing failed — show full thread and drop stale hide so the chat is not blank.
    if (effectiveList.isEmpty && list.isNotEmpty && _userInboxHideBeforeTs != null) {
      var maxAt = 0.0;
      for (final m in list) {
        if (m is! Map) continue;
        final raw = m['created_at'];
        final at = raw is num
            ? raw.toDouble()
            : (raw is String ? double.tryParse(raw) ?? 0.0 : 0.0);
        if (at > maxAt) maxAt = at;
      }
      if (maxAt > _userInboxHideBeforeTs!) {
        effectiveList = List<dynamic>.from(list);
        _userInboxHideBeforeTs = null;
        unawaited(SharedPreferences.getInstance().then((p) => p.remove(_inboxHidePrefKey())));
      }
    }
    if (pollGeneration >= 0 && pollGeneration != _userInboxFetchGeneration) return;
    if (effectiveList.isEmpty) {
      // Valid empty thread: clear UI and mark read so friend list does not show a stale red dot.
      widget.coreService.setUserInboxLastRead(widget.userId, widget.toUserId!, DateTime.now().millisecondsSinceEpoch / 1000.0);
      if (mounted && (pollGeneration < 0 || pollGeneration == _userInboxFetchGeneration)) {
        setState(() {
          _messages.clear();
          _messageImages.clear();
          _messageAudios.clear();
          _messageVideos.clear();
          _messageFileLabels.clear();
          _messageFileRefs.clear();
        });
      }
      return;
    }
    final myId = widget.userId.trim();
    _messages.clear();
    _messageImages.clear();
    _messageAudios.clear();
    _messageVideos.clear();
    _messageFileLabels.clear();
    _messageFileRefs.clear();
    for (final m in effectiveList) {
      if (!mounted) return;
      if (pollGeneration >= 0 && pollGeneration != _userInboxFetchGeneration) return;
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
        if (!mounted) return;
        if (pollGeneration >= 0 && pollGeneration != _userInboxFetchGeneration) return;
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
      final flRaw = mmap['file_links'] as List<dynamic>?;
      List<String>? fileLabels;
      List<String>? fileRefs;
      if (flRaw != null && flRaw.isNotEmpty) {
        fileRefs = flRaw.map((e) => e.toString().trim()).where((s) => s.isNotEmpty).toList();
        fileLabels = fileRefs.map((e) => path.basename(e)).toList();
      }
      _messageFileLabels.add(fileLabels != null && fileLabels.isNotEmpty ? fileLabels : null);
      _messageFileRefs.add(fileRefs != null && fileRefs.isNotEmpty ? fileRefs : null);
    }
    // Mark thread as read up to latest message so friend list unread dot clears.
    double latestTs = DateTime.now().millisecondsSinceEpoch / 1000.0;
    for (final m in effectiveList) {
      if (m is! Map) continue;
      final at = (m['created_at'] as num?)?.toDouble();
      if (at != null && at > latestTs) latestTs = at;
    }
    widget.coreService.setUserInboxLastRead(widget.userId, widget.toUserId!, latestTs);
    if (mounted && (pollGeneration < 0 || pollGeneration == _userInboxFetchGeneration)) {
      setState(() {});
      _scrollToBottom();
    }
  }

  String _fingerprintUserInboxThread(List<dynamic> list) {
    final parts = <String>[];
    for (final m in list) {
      if (m is! Map) continue;
      final mm = m is Map<String, dynamic> ? m : Map<String, dynamic>.from(m);
      final id = (mm['id']?.toString() ?? '').trim();
      final from = (mm['from_user_id']?.toString() ?? '').trim();
      final t = mm['created_at'];
      final textLen = (mm['text']?.toString() ?? '').length;
      final ni = (mm['images'] as List?)?.length ?? 0;
      final na = (mm['audios'] as List?)?.length ?? 0;
      final nv = (mm['videos'] as List?)?.length ?? 0;
      final nf = (mm['file_links'] as List?)?.length ?? 0;
      final e2eId = (mm['e2e'] is Map) ? ((mm['e2e'] as Map)['id']?.toString() ?? '') : '';
      parts.add('$id|$from|$t|$textLen|$ni|$na|$nv|$nf|$e2eId');
    }
    return parts.join('\n');
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
    final prefs = await SharedPreferences.getInstance();
    final nowTs = DateTime.now().millisecondsSinceEpoch / 1000.0;
    // For user threads, do NOT set hide-before until we know server DELETE failed — otherwise
    // client clock vs Core clock skew can drop all new messages (receiver sees an empty thread).
    if (widget.isUserFriend && widget.toUserId != null && widget.toUserId!.trim().isNotEmpty) {
      _lastUserInboxThreadFingerprint = null;
    } else {
      _aiChatHideBeforeTs = nowTs;
      await prefs.setDouble(_aiChatHidePrefKey(), nowTs);
    }
    await ChatHistoryStore().clear(widget.userId, widget.friendId);
    if (!mounted) return;
    setState(() {
      _messages.clear();
      _messageImages.clear();
      _messageAudios.clear();
      _messageVideos.clear();
      _messageFileLabels.clear();
      _messageFileRefs.clear();
      _lastReply = null;
      _chatHistoryOffset = 0;
      _hasMoreMessages = true;
    });
    if (widget.isUserFriend && widget.toUserId != null && widget.toUserId!.trim().isNotEmpty) {
      try {
        final del = await widget.coreService.clearUserInboxThread(
          userId: widget.userId,
          otherUserId: widget.toUserId!.trim(),
        );
        _lastUserInboxThreadFingerprint = null;
        await prefs.remove(_inboxHidePrefKey());
        if (mounted) {
          setState(() => _userInboxHideBeforeTs = null);
          _userInboxFetchGeneration++;
          unawaited(_loadUserInbox());
        }
        if (mounted) {
          final hasPeer = del.containsKey('peer_cleared');
          final peerOk = del['peer_cleared'];
          final peerErr = del['peer_error']?.toString() ?? '';
          if (hasPeer && peerOk == false) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(
                  peerErr.isNotEmpty
                      ? 'Cleared on this HomeClaw. Remote peer could not clear: $peerErr'
                      : 'Cleared on this HomeClaw. The other instance may still show old messages — check peer URL and federation_trusted_instances.',
                ),
              ),
            );
          } else {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(
                  hasPeer
                      ? 'Chat history cleared on this Core and the remote HomeClaw.'
                      : 'Chat history cleared',
                ),
              ),
            );
          }
        }
      } catch (e) {
        // Server still has rows: use hide cutoff only as fallback (skew can hide new mail briefly).
        _userInboxHideBeforeTs = nowTs;
        await prefs.setDouble(_inboxHidePrefKey(), nowTs);
        if (mounted) {
          setState(() {});
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Cleared on this device. Server clear pending: $e')),
          );
        }
      }
    } else if (mounted) {
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
    // Async inbound finished (or Hive just wrote the reply): reload from store so the thread updates even if the user left and came back.
    final ev = push['event'] as String?;
    if (!widget.isUserFriend && (ev == 'chat_history_updated' || ev == 'inbound_result')) {
      final uid = (push['user_id'] as String?)?.trim();
      final fidRaw = (push['friend_id'] as String?)?.trim();
      final fid = (fidRaw == null || fidRaw.isEmpty) ? 'HomeClaw' : fidRaw;
      if (uid != null && uid.isNotEmpty && uid == widget.userId.trim()) {
        final thisFriend = (widget.friendId?.trim().isEmpty != false) ? 'HomeClaw' : widget.friendId!.trim();
        if (fid == thisFriend && mounted) {
          _loadChatHistory();
          setState(() {});
        }
      }
      return;
    }
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
    final pushFileRaw = push['file_links'] as List<dynamic>?;
    List<String>? pushFileRefs;
    List<String>? pushFileLabels;
    if (pushFileRaw != null && pushFileRaw.isNotEmpty) {
      pushFileRefs = pushFileRaw.map((e) => e.toString().trim()).where((s) => s.isNotEmpty).toList();
      pushFileLabels = pushFileRefs.map((e) => path.basename(e)).toList();
    }
    setState(() {
      _messages.add(MapEntry(text, false));
      _messageImages.add(images != null && images.isNotEmpty ? images : null);
      _messageAudios.add(audios != null && audios.isNotEmpty ? audios : null);
      _messageVideos.add(videos != null && videos.isNotEmpty ? videos : null);
      _messageFileLabels.add(pushFileLabels != null && pushFileLabels.isNotEmpty ? pushFileLabels : null);
      _messageFileRefs.add(pushFileRefs != null && pushFileRefs.isNotEmpty ? pushFileRefs : null);
    });
    _scrollToBottom(force: true);
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
    try {
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
    final isUserToUserSend = widget.isUserFriend && widget.toUserId != null && widget.toUserId!.trim().isNotEmpty;
    if (isUserToUserSend && mounted) {
      setState(() {
        _activeUserSendStage = _userSendInitialStage(
          hasImages: imagesToSend.isNotEmpty,
          hasVideos: videosToSend.isNotEmpty,
          hasFiles: filesToSend.isNotEmpty,
        );
      });
    }
    final federatedUserChat =
        widget.isUserFriend && (widget.remotePeerInstanceId?.trim().isNotEmpty ?? false);
    if (isUserToUserSend && videosToSend.isNotEmpty && mounted) {
      setState(() => _activeUserSendStage = 'Preparing video...');
    }
    if (isUserToUserSend && imagesToSend.isNotEmpty && mounted) {
      setState(() => _activeUserSendStage = 'Compressing image...');
    }
    // User-to-user: show local file paths until upload+send completes (Core uses paths/URLs, not base64).
    // Other chats: data URLs for preview in the bubble.
    final userImageRefs = imagesToSend.isNotEmpty
        ? (isUserToUserSend
            ? List<String>.from(imagesToSend)
            : (widget.isUserFriend
                ? await _filePathsToUserMessageImageDataUrls(
                    imagesToSend,
                    strictForFederation: federatedUserChat,
                  )
                : await _filePathsToImageDataUrls(imagesToSend)))
        : <String>[];
    // Keep send path independent from preview generation (media is uploaded directly for user-to-user below).
    // One short video for user-to-user (max 15MB, ~10s), keep local ref for optimistic bubble.
    final userVideoRefs = videosToSend.isNotEmpty ? <String>[videosToSend.first] : <String>[];
    if (videosToSend.isNotEmpty && userVideoRefs.isEmpty && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Video not sent: keep under 15MB (e.g. ~10 seconds) for user messages.')),
      );
    }
    if (!mounted) {
      _stopLoadingStatusTimer();
      setState(() => _loading = false);
      return;
    }
    final outgoingFileNames = filesToSend.map((p) => path.basename(p)).toList();
    int? optimisticIndex;
    setState(() {
      optimisticIndex = _messages.length;
      _pendingImagePaths.clear();
      _pendingVideoPaths.clear();
      _pendingFilePaths.clear();
      _messages.add(MapEntry(text.isEmpty ? '(attachment)' : text, true));
      _messageImages.add(userImageRefs.isEmpty ? null : userImageRefs);
      _messageAudios.add(null);
      _messageVideos.add(userVideoRefs.isEmpty ? null : userVideoRefs);
      _messageFileLabels.add(outgoingFileNames.isEmpty ? null : outgoingFileNames);
      _messageFileRefs.add(filesToSend.isEmpty ? null : List<String>.from(filesToSend));
      if (isUserToUserSend) {
        _activeUserSendBubbleIndex = optimisticIndex;
      }
      _loading = true;
      _loadingStatusIndex = 0;
    });
    _startLoadingStatusTimer();
    _scrollToBottom();
    // Persist the optimistic user bubble before any outbound request so Hive matches Core append order
    // (assistant is appended after inbound returns) and reloads cannot race an incomplete save.
    await _persistChatHistory();
    if (!mounted) {
      _stopLoadingStatusTimer();
      return;
    }
    // User-to-user: send via POST /api/user-message; no AI reply.
    if (isUserToUserSend) {
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
        List<String>? imagesToSendRefs;
        List<String>? videosToSendRefs;
        List<String>? fileLinksToSend;
        final allToUpload = <String>[...imagesToSend, ...videosToSend, ...filesToSend];
        if (allToUpload.isNotEmpty) {
          if (mounted) {
            setState(() {
              _activeUserSendStage = allToUpload.length <= 1
                  ? 'Uploading attachment...'
                  : 'Uploading ${allToUpload.length} attachments...';
            });
          }
          final uploaded = await widget.coreService.uploadFiles(allToUpload);
          final nI = imagesToSend.length;
          final nV = videosToSend.length;
          final nF = filesToSend.length;
          if (uploaded.length < allToUpload.length) {
            throw Exception('Upload incomplete: expected ${allToUpload.length}, got ${uploaded.length}.');
          }
          imagesToSendRefs = nI > 0 ? uploaded.take(nI).toList() : null;
          videosToSendRefs = nV > 0 ? uploaded.skip(nI).take(nV).toList() : null;
          fileLinksToSend = nF > 0 ? uploaded.skip(nI + nV).take(nF).toList() : null;
        }
        if (mounted) {
          setState(() => _activeUserSendStage = 'Sending to friend...');
        }
        await widget.coreService.sendUserMessage(
          fromUserId: widget.userId,
          toUserId: widget.toUserId!.trim(),
          text: e2eEnvelope != null ? '' : text,
          images: imagesToSendRefs,
          videos: videosToSendRefs,
          fileLinks: fileLinksToSend,
          e2e: e2eEnvelope,
        );
        if (mounted) {
          _stopLoadingStatusTimer();
          setState(() {
            _loading = false;
            _loadingMessage = null;
            _activeUserSendBubbleIndex = null;
            _activeUserSendStage = null;
          });
          _scrollToBottom(force: true);
        }
      } catch (e) {
        if (mounted) {
          _stopLoadingStatusTimer();
          final errText = e.toString();
          final likelyPayloadOrTimeout = errText.contains('413') ||
              errText.toLowerCase().contains('payload') ||
              errText.contains('502') ||
              errText.toLowerCase().contains('timed out');
          setState(() {
            if (optimisticIndex != null && optimisticIndex! >= 0 && optimisticIndex! < _messages.length) {
              _messages.removeAt(optimisticIndex!);
              if (optimisticIndex! < _messageImages.length) _messageImages.removeAt(optimisticIndex!);
              if (optimisticIndex! < _messageAudios.length) _messageAudios.removeAt(optimisticIndex!);
              if (optimisticIndex! < _messageVideos.length) _messageVideos.removeAt(optimisticIndex!);
              if (optimisticIndex! < _messageFileLabels.length) _messageFileLabels.removeAt(optimisticIndex!);
              if (optimisticIndex! < _messageFileRefs.length) _messageFileRefs.removeAt(optimisticIndex!);
            }
            _pendingImagePaths
              ..clear()
              ..addAll(imagesToSend);
            _pendingVideoPaths
              ..clear()
              ..addAll(videosToSend);
            _pendingFilePaths
              ..clear()
              ..addAll(filesToSend);
            _messages.add(MapEntry('Error: $e', false));
            _messageImages.add(null);
            _messageAudios.add(null);
            _messageVideos.add(null);
            _messageFileLabels.add(null);
            _messageFileRefs.add(null);
            _loading = false;
            _loadingMessage = null;
            _activeUserSendBubbleIndex = null;
            _activeUserSendStage = null;
          });
          if (likelyPayloadOrTimeout) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text(
                  'Send failed (network or payload limit). Your attachment is still shown above — tap Send again, or try a smaller file.',
                ),
              ),
            );
          } else {
            var hint = errText;
            if (hint.contains('401') || hint.toLowerCase().contains('api key')) {
              hint =
                  "$hint\nIf this is a remote friend: set api_key (or use_same_auth_api_key_as_local_core) in peers.yml on the sender Core to match the peer's auth_api_key.";
            }
            if (hint.contains('502') || hint.toLowerCase().contains('federation')) {
              hint =
                  "$hint\nFederation: check peer base_url, peer Core logs, nginx client_max_body_size, and that both instances trust the sender.";
            }
            final shown = hint.length > 360 ? '${hint.substring(0, 360)}…' : hint;
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(shown)));
          }
          _scrollToBottom(force: true);
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
          // Require successful upload; no base64 fallback (keeps assistant path path/URL-based).
        }
      }
      String? locationStr;
      try {
        locationStr = await _getCurrentLocationString();
      } catch (_) {}
      final ccSid = (_clawcodeSessionId ?? '').trim();
      final clawOn = _isClawcodePresetFriend && ccSid.isNotEmpty;
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
        clawcodeSessionId: clawOn ? ccSid : null,
        useStream: clawOn ? true : null,
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
          _activeUserSendBubbleIndex = null;
          _activeUserSendStage = null;
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
        // [core_service] already persisted the reply and emitted chat_history_updated; that can run
        // _loadChatHistory() before we return. Do not append the assistant again or the same reply shows twice.
        _loadChatHistory();
        final rtext = reply.isEmpty ? '(no reply)' : reply;
        if (mounted && _messages.isNotEmpty && _messages.last.value) {
          setState(() {
            _messages.add(MapEntry(rtext, false));
            _messageImages.add(imageDataUrls.isEmpty ? null : imageDataUrls);
            _messageAudios.add(null);
            _messageVideos.add(null);
            _messageFileLabels.add(null);
            _messageFileRefs.add(null);
          });
        }
        _scrollToBottom(force: true);
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
          _messageFileLabels.add(null);
          _messageFileRefs.add(null);
          _loading = false;
          _loadingMessage = null;
          _activeUserSendBubbleIndex = null;
          _activeUserSendStage = null;
        });
        _scrollToBottom();
        _persistChatHistory();
      }
    }
    } finally {
      _stopLoadingStatusTimer();
      if (mounted) {
        setState(() {
          if (_loading) {
            _loading = false;
            _loadingMessage = null;
            _activeUserSendBubbleIndex = null;
            _activeUserSendStage = null;
          }
        });
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
                if (index < _messageFileLabels.length) _messageFileLabels.removeAt(index);
                if (index < _messageFileRefs.length) _messageFileRefs.removeAt(index);
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

  /// User-to-user on one Core: keep JSON modest (still data URLs for Companion bubbles).
  static const int _userMsgImageMaxJpegBytes = 768 * 1024;
  static const double _userMsgImageMaxLongEdge = 1600;

  /// Cross-instance: stricter — tunnel/proxy body limits; never send an oversized blob.
  static const int _userMsgFedImageMaxJpegBytes = 384 * 1024;
  static const double _userMsgFedImageMaxLongEdge = 1280;

  /// Encode [source] as JPEG data URL. Returns null if it cannot get under [maxJpegBytes] (caller skips image).
  String? _imageToUserMessageJpegDataUrl(
    img.Image source, {
    required int maxJpegBytes,
    required double maxLongEdgeStart,
  }) {
    var maxLong = maxLongEdgeStart;
    Uint8List? smallest;
    for (var shrinkRound = 0; shrinkRound < 36; shrinkRound++) {
      final w = source.width;
      final h = source.height;
      final long = w > h ? w : h;
      final img.Image frame;
      if (long > maxLong) {
        int tw;
        int th;
        if (w >= h) {
          tw = maxLong.round();
          th = max((h * maxLong / w).round(), 1);
        } else {
          th = maxLong.round();
          tw = max((w * maxLong / h).round(), 1);
        }
        frame = img.copyResize(source, width: tw, height: th, interpolation: img.Interpolation.linear);
      } else {
        frame = source;
      }
      for (var q = 88; q >= 10; q -= 5) {
        final jpg = Uint8List.fromList(img.encodeJpg(frame, quality: q));
        if (smallest == null || jpg.length < smallest.length) {
          smallest = jpg;
        }
        if (jpg.length <= maxJpegBytes) {
          return 'data:image/jpeg;base64,${base64Encode(jpg)}';
        }
      }
      maxLong *= 0.72;
      if (maxLong < 140) {
        break;
      }
    }
    if (smallest != null && smallest.length <= maxJpegBytes) {
      return 'data:image/jpeg;base64,${base64Encode(smallest)}';
    }
    return null;
  }

  /// Downscale images before sending to another user (local or federated). Falls back to raw small files if decode fails.
  Future<List<String>> _filePathsToUserMessageImageDataUrls(
    List<String> filePaths, {
    bool strictForFederation = false,
  }) async {
    final maxJpeg = strictForFederation ? _userMsgFedImageMaxJpegBytes : _userMsgImageMaxJpegBytes;
    final maxLong = strictForFederation ? _userMsgFedImageMaxLongEdge : _userMsgImageMaxLongEdge;
    final out = <String>[];
    var skippedUndecodableLarge = false;
    var failedToCompress = false;
    var attempted = 0;
    for (final p in filePaths) {
      final ext = path.extension(p).toLowerCase().replaceFirst('.', '');
      if (!_imageMime.containsKey(ext)) continue;
      final file = File(p);
      if (!await file.exists()) continue;
      attempted++;
      final bytes = await file.readAsBytes();
      final decoded = img.decodeImage(bytes);
      if (decoded == null) {
        if (bytes.length <= maxJpeg) {
          out.add('data:${_imageMime[ext]};base64,${base64Encode(bytes)}');
        } else {
          skippedUndecodableLarge = true;
        }
        continue;
      }
      final url = _imageToUserMessageJpegDataUrl(
        decoded,
        maxJpegBytes: maxJpeg,
        maxLongEdgeStart: maxLong,
      );
      if (url != null) {
        out.add(url);
      } else {
        failedToCompress = true;
      }
    }
    if (failedToCompress && mounted) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              strictForFederation
                  ? 'Could not shrink a photo under ${(maxJpeg / 1024).round()}KB for remote send. Try another image.'
                  : 'Could not shrink a photo enough to send. Try another image.',
            ),
          ),
        );
      });
    }
    if (skippedUndecodableLarge && mounted) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'An image could not be resized (format not supported). Use JPEG or PNG, or pick a smaller file.',
            ),
          ),
        );
      });
    }
    if (attempted > 0 &&
        out.length < attempted &&
        mounted &&
        !failedToCompress &&
        !skippedUndecodableLarge) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Some images were not included (could not resize or unsupported format).'),
          ),
        );
      });
    }
    return out;
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
    if (_voiceListening) {
      await _cancelVoiceInput();
    }
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

  /// Stop push-to-talk, upload audio, send by reference, and add to chat.
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
      try {
        final uploaded = await widget.coreService.uploadFiles([filePath]);
        final audioRef = uploaded.isNotEmpty ? uploaded.first : filePath;
        await widget.coreService.sendUserMessage(
          fromUserId: widget.userId,
          toUserId: widget.toUserId!.trim(),
          text: '',
          audios: [audioRef],
        );
        if (!mounted) return;
        setState(() {
          _messages.add(MapEntry('(voice)', true));
          _messageImages.add(null);
          _messageAudios.add([audioRef]);
          _messageVideos.add(null);
          _messageFileLabels.add(null);
          _messageFileRefs.add(null);
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
    try {
      await _voiceSubscription?.cancel();
      _voiceSubscription = null;
      if (mounted) {
        setState(() {
          _voiceTranscript = '';
          _inputController.clear();
        });
      }
      _voiceSubscription = _voice.voiceEventStream.listen(
        (event) {
          try {
            if (!mounted) return;
            final partialRaw = event['partial'];
            final finalRaw = event['final'];
            final partial = partialRaw is String
                ? partialRaw
                : (partialRaw != null ? partialRaw.toString() : null);
            final finalText = finalRaw is String
                ? finalRaw
                : (finalRaw != null ? finalRaw.toString() : null);
            if (finalText != null && finalText.isNotEmpty) {
              if (!mounted) return;
              setState(() {
                _voiceTranscript = finalText;
                _inputController.text = finalText;
                final len = finalText.length;
                _inputController.selection = TextSelection.collapsed(
                  offset: len.clamp(0, _inputController.text.length),
                );
              });
              if (!_voiceInputCancelled && !_loading) {
                _send().then((_) {
                  if (mounted) setState(() => _voiceTranscript = '');
                });
              }
            } else if (partial != null && partial.isNotEmpty) {
              if (!mounted) return;
              setState(() {
                _voiceTranscript = partial;
                _inputController.text = partial;
                final len = partial.length;
                _inputController.selection = TextSelection.collapsed(
                  offset: len.clamp(0, _inputController.text.length),
                );
              });
            }
          } catch (e, st) {
            FlutterError.reportError(FlutterErrorDetails(exception: e, stack: st));
            if (mounted) {
              setState(() => _voiceListening = false);
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('Voice handler error: $e')),
              );
            }
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
      await _voice.startVoiceListening(locale: _voiceInputLocale);
      if (mounted) setState(() => _voiceListening = true);
    } catch (e, st) {
      await _voiceSubscription?.cancel();
      _voiceSubscription = null;
      try {
        await _voice.stopVoiceListening();
      } catch (_) {}
      FlutterError.reportError(FlutterErrorDetails(exception: e, stack: st));
      if (mounted) {
        setState(() => _voiceListening = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Voice failed: $e. On macOS/iOS allow Microphone + Speech Recognition; on macOS see homeclaw_voice README if the app crashes in the speech plugin.',
            ),
          ),
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

  /// Federated E2E text-only mode: no images, video, files, or voice clips.
  bool get _federatedE2eAttachmentsDisabled =>
      widget.isUserFriend &&
      widget.coreService.federationE2eRequireEncrypted &&
      (widget.remotePeerInstanceId?.trim().isNotEmpty ?? false);

  void _snackFedE2eMediaBlocked() {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(
          'Photos, video, and files are not available when this Core requires encrypted federation chat.',
        ),
      ),
    );
  }

  /// Pick or capture a photo. [presetSource] skips the source chooser (composer shortcuts).
  Future<void> _attachPhoto({ImageSource? presetSource}) async {
    if (_federatedE2eAttachmentsDisabled) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Photos are not available when this Core requires encrypted federation chat.'),
          ),
        );
      }
      return;
    }
    await Future<void>.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;
    ImageSource? source = presetSource;
    if (source == null) {
      source = await showDialog<ImageSource>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Add photo'),
          content: const Text('Use camera to take a new photo, or choose an existing image from your device.'),
          actions: [
            TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.of(ctx).pop(ImageSource.camera), child: const Text('Use camera')),
            FilledButton(onPressed: () => Navigator.of(ctx).pop(ImageSource.gallery), child: const Text('Choose from device')),
          ],
        ),
      );
    }
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
                Expanded(
                  child: Text(
                    source == ImageSource.camera ? 'Opening camera…' : 'Choosing photo…',
                    textAlign: TextAlign.start,
                  ),
                ),
              ],
            ),
          ),
        );
      }
      final xFile = await _imagePicker.pickImage(
        source: source,
        maxWidth: 2048,
        imageQuality: 85,
      );
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
          _messageFileLabels.add(null);
          _messageFileRefs.add(null);
        });
        return;
      }
      final filePath = result.path!;
      if (mounted) {
        setState(() => _pendingImagePaths.add(filePath));
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Photo attached. Type a message and Send to include it.')));
      }
    } catch (e) {
      if (mounted) {
        try {
          Navigator.of(context).pop();
        } catch (_) {}
        setState(() {
          _messages.add(MapEntry('Photo error: $e', false));
          _messageImages.add(null);
          _messageAudios.add(null);
          _messageVideos.add(null);
          _messageFileLabels.add(null);
          _messageFileRefs.add(null);
        });
      }
    }
  }

  Future<void> _takePhoto() async {
    await _attachPhoto();
  }

  Future<void> _recordVideo() async {
    if (_federatedE2eAttachmentsDisabled) {
      _snackFedE2eMediaBlocked();
      return;
    }
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
            _messageFileLabels.add(null);
            _messageFileRefs.add(null);
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
            _messageFileLabels.add(null);
            _messageFileRefs.add(null);
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
          _messageFileLabels.add(null);
          _messageFileRefs.add(null);
        });
      }
    }
  }

  Future<void> _recordScreen() async {
    if (_federatedE2eAttachmentsDisabled) {
      _snackFedE2eMediaBlocked();
      return;
    }
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
    if (_federatedE2eAttachmentsDisabled) {
      _snackFedE2eMediaBlocked();
      return;
    }
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
        _messageFileLabels.add(null);
        _messageFileRefs.add(null);
      });
    } catch (e) {
      if (mounted) setState(() {
        _messages.add(MapEntry('Run error: $e', false));
        _messageImages.add(null);
        _messageAudios.add(null);
        _messageVideos.add(null);
        _messageFileLabels.add(null);
        _messageFileRefs.add(null);
      });
    }
  }

  bool _isLocalThreadImageFilePath(String ref) {
    final t = ref.trim();
    if (t.isEmpty ||
        t.startsWith('data:') ||
        t.startsWith('http://') ||
        t.startsWith('https://') ||
        t.startsWith('/files/') ||
        t.startsWith('/files/out')) {
      return false;
    }
    final e = path.extension(t).toLowerCase();
    if (!const ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.bmp'].contains(e)) {
      return false;
    }
    try {
      return File(t).existsSync();
    } catch (_) {
      return false;
    }
  }

  bool _isDisplayableThreadImage(String ref) {
    final t = ref.trim();
    if (t.startsWith('data:image/')) return true;
    if (_isLocalThreadImageFilePath(t)) return true;
    final u = Uri.tryParse(t);
    if (u != null && u.hasScheme && (u.scheme == 'http' || u.scheme == 'https')) return true;
    // Only treat Core file routes as network-loadable relative paths.
    if (t.startsWith('/files/')) return true;
    if (t.startsWith('/files/out')) return true;
    return false;
  }

  /// Resolve image/audio/video/file refs for network fetch (http(s) or Core-relative `/files/...`).
  String? _resolveThreadMediaNetworkUrl(String ref) {
    final t = ref.trim();
    final u = Uri.tryParse(t);
    if (u != null && u.hasScheme && (u.scheme == 'http' || u.scheme == 'https')) {
      return t;
    }
    if (t.startsWith('/files/') || t.startsWith('/files/out')) {
      final base = widget.coreService.baseUrl.replaceFirst(RegExp(r'/$'), '');
      return '$base$t';
    }
    return null;
  }

  Future<void> _openUserMessageFileRef(String ref) async {
    final t = ref.trim();
    if (t.isEmpty) return;
    try {
      if (t.startsWith('data:')) return;
      final local = File(t);
      if (await local.exists()) {
        final ok = await launchUrl(Uri.file(local.absolute.path), mode: LaunchMode.externalApplication);
        if (!ok && mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open file')));
        }
        return;
      }
      final resolved = _resolveThreadMediaNetworkUrl(t);
      if (resolved == null) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No link for this attachment')));
        }
        return;
      }
      final uri = Uri.tryParse(resolved);
      if (uri == null || !uri.hasScheme) return;
      final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!ok && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open link')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Open failed: $e')));
      }
    }
  }

  Widget _threadImagePreview(String imageRef) {
    const w = 280.0;
    final cs = Theme.of(context).colorScheme;
    final trimmed = imageRef.trim();
    if (_isLocalThreadImageFilePath(trimmed)) {
      return RepaintBoundary(
        child: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: Image.file(
            File(trimmed),
            width: w,
            fit: BoxFit.contain,
            gaplessPlayback: true,
            errorBuilder: (_, __, ___) => Icon(Icons.broken_image_outlined, color: cs.outline, size: 40),
          ),
        ),
      );
    }
    if (trimmed.startsWith('data:image/')) {
      final bytes = _decodeDataUrlToBytes(trimmed);
      if (bytes == null || bytes.isEmpty) {
        return Icon(Icons.broken_image_outlined, color: cs.outline, size: 40);
      }
      return RepaintBoundary(
        child: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: Image.memory(
            bytes,
            width: w,
            fit: BoxFit.contain,
            gaplessPlayback: true,
            errorBuilder: (_, __, ___) => Icon(Icons.broken_image_outlined, color: cs.outline, size: 40),
          ),
        ),
      );
    }
    final resolved = _resolveThreadMediaNetworkUrl(imageRef);
    if (resolved == null) {
      return Icon(Icons.insert_photo_outlined, color: cs.outline, size: 40);
    }
    final sameCorePath = trimmed.startsWith('/');
    return RepaintBoundary(
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Image.network(
          resolved,
          width: w,
          fit: BoxFit.contain,
          headers: sameCorePath ? widget.coreService.coreMediaFetchHeaders : null,
          loadingBuilder: (c, child, prog) {
            if (prog == null) return child;
            return SizedBox(
              width: w,
              height: 140,
              child: Center(
                child: SizedBox(
                  width: 28,
                  height: 28,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    value: prog.expectedTotalBytes != null && prog.expectedTotalBytes! > 0
                        ? prog.cumulativeBytesLoaded / prog.expectedTotalBytes!
                        : null,
                  ),
                ),
              ),
            );
          },
          errorBuilder: (_, __, ___) => Icon(Icons.broken_image_outlined, color: cs.outline, size: 40),
        ),
      ),
    );
  }

  /// Scroll the message list to the bottom so the latest message is visible.
  /// Media widgets (images/videos) can expand asynchronously after decode, so we do
  /// a short follow pass (multi-tick jumpTo) to keep the latest bubble in view.
  void _scrollToBottom({bool force = false}) {
    if (!force && !_autoFollowBottom) return;
    void jumpBottom() {
      if (!mounted || !_scrollController.hasClients) return;
      try {
        _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
      } catch (_) {}
    }

    WidgetsBinding.instance.addPostFrameCallback((_) => jumpBottom());
    for (final ms in const [40, 120, 260, 520, 900]) {
      Future<void>.delayed(Duration(milliseconds: ms), jumpBottom);
    }
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

  String _inputHintText() {
    if (_pendingImagePaths.isNotEmpty || _pendingVideoPaths.isNotEmpty || _pendingFilePaths.isNotEmpty) {
      return 'Add a message (optional)';
    }
    final k = widget.resolvedProductPresetKey;
    if (k == null) return 'Message';
    switch (k) {
      case 'reminder':
        return 'e.g. Remind me in 1 hour to…';
      case 'finder':
        return 'e.g. Find report.pdf in documents';
      case 'knowledge':
        return 'e.g. Search my KB for…';
      default:
        return 'Message';
    }
  }

  Widget _buildProductPresetBar() {
    final k = widget.resolvedProductPresetKey;
    if (k == null || widget.isUserFriend) return const SizedBox.shrink();
    final actions = presetQuickActionsFor(k);
    final hint = _messages.isEmpty ? productPresetEmptyHint(k) : null;
    if (actions.isEmpty && (hint == null || hint.isEmpty)) {
      return const SizedBox.shrink();
    }
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.55),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 6, 8, 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (hint != null && hint.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  hint,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                ),
              ),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  for (final a in actions)
                    Padding(
                      padding: const EdgeInsets.only(right: 6),
                      child: ActionChip(
                        label: Text(a.label),
                        onPressed: _loading
                            ? null
                            : () {
                                setState(() {
                                  _inputController.text = a.text;
                                  _inputController.selection = TextSelection.collapsed(offset: a.text.length);
                                });
                              },
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _connectionCheckTimer?.cancel();
    _userInboxPollTimer?.cancel();
    _userInboxApplyDebounceTimer?.cancel();
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
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Tooltip(
                          message: _cursorActiveCwd.trim(),
                          child: GestureDetector(
                            onTap: () async {
                              await _showActiveProjectPathDialog();
                            },
                            child: Chip(
                              avatar: Icon(
                                Icons.folder_outlined,
                                size: 16,
                                color: Theme.of(context).colorScheme.primary,
                              ),
                              label: Text(
                                path.basename(_cursorActiveCwd.trim()),
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 11),
                              ),
                              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              visualDensity: VisualDensity.compact,
                              padding: const EdgeInsets.symmetric(horizontal: 6),
                            ),
                          ),
                        ),
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
                    if (_isClawcodePresetFriend && (_clawcodeSessionId ?? '').trim().isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Material(
                            color: Colors.transparent,
                            child: InkWell(
                              onTap: _showClawcodeSessionPicker,
                              borderRadius: BorderRadius.circular(16),
                              child: Chip(
                                avatar: Icon(
                                  Icons.terminal,
                                  size: 16,
                                  color: Theme.of(context).colorScheme.primary,
                                ),
                                label: Text(
                                  'Claw-Code · ${_shortClawcodeId(_clawcodeSessionId!)}',
                                  style: const TextStyle(fontSize: 11),
                                ),
                                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                visualDensity: VisualDensity.compact,
                                padding: const EdgeInsets.symmetric(horizontal: 6),
                              ),
                            ),
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
          if (_isClawcodePresetFriend)
            IconButton(
              icon: Icon(
                (_clawcodeSessionId ?? '').trim().isNotEmpty ? Icons.terminal : Icons.terminal_outlined,
              ),
              tooltip: (_clawcodeSessionId ?? '').trim().isNotEmpty
                  ? 'Claw-Code session on — tap to change'
                  : 'Claw-Code — pick workspace session',
              color: (_clawcodeSessionId ?? '').trim().isNotEmpty ? Theme.of(context).colorScheme.primary : null,
              onPressed: _showClawcodeSessionPicker,
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
                case 'clawcode_bind':
                  await _showClawcodeSessionPicker();
                  break;
                default:
                  break;
              }
            },
            itemBuilder: (context) => [
              const PopupMenuItem(value: 'photo', child: Text('Add photo…')),
              const PopupMenuItem(value: 'video', child: Text('Record video')),
              const PopupMenuItem(value: 'document', child: Text('Attach file')),
              const PopupMenuItem(value: 'screen', child: Text('Record screen')),
              ...(Platform.isMacOS || Platform.isWindows || Platform.isLinux
                  ? [const PopupMenuItem(value: 'run', child: Text('Run command'))]
                  : []),
              if (_isClawcodePresetFriend) ...[
                const PopupMenuDivider(),
                PopupMenuItem(
                  value: 'clawcode_bind',
                  child: Text(
                    (_clawcodeSessionId ?? '').trim().isEmpty ? 'Claw-Code: bind session…' : 'Claw-Code: change session…',
                  ),
                ),
              ],
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
          _buildProductPresetBar(),
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
                final isUploadingUserBubble =
                    isUser && _loading && _activeUserSendBubbleIndex != null && _activeUserSendBubbleIndex == msgIndex;
                final imageUrls = msgIndex < _messageImages.length ? _messageImages[msgIndex] : null;
                final audioUrls = msgIndex < _messageAudios.length ? _messageAudios[msgIndex] : null;
                final videoUrls = msgIndex < _messageVideos.length ? _messageVideos[msgIndex] : null;
                final fileLabels = msgIndex < _messageFileLabels.length ? _messageFileLabels[msgIndex] : null;
                final fileRefs = msgIndex < _messageFileRefs.length ? _messageFileRefs[msgIndex] : null;
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
                                        .where((u) => _isDisplayableThreadImage(u))
                                        .map((imageRef) => Padding(
                                              padding: const EdgeInsets.only(bottom: 6),
                                              child: GestureDetector(
                                                onTap: () {
                                                  final t = imageRef.trim();
                                                  Navigator.of(context).push(
                                                    MaterialPageRoute<void>(
                                                      builder: (ctx) => _FullScreenImagePage(
                                                        imageRef: imageRef,
                                                        coreBaseUrl: widget.coreService.baseUrl,
                                                        fetchHeaders:
                                                            t.startsWith('/') ? widget.coreService.coreMediaFetchHeaders : null,
                                                      ),
                                                    ),
                                                  );
                                                },
                                                child: _threadImagePreview(imageRef),
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
                                              child: _AudioPlayButton(
                                                audioRef: audioDataUrl,
                                                coreBaseUrl: widget.coreService.baseUrl,
                                                coreMediaHeaders: widget.coreService.coreMediaFetchHeaders,
                                              ),
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
                                              child: _VideoPlayChip(
                                                videoRef: videoDataUrl,
                                                coreBaseUrl: widget.coreService.baseUrl,
                                                httpHeaders: widget.coreService.coreMediaFetchHeaders,
                                              ),
                                            ))
                                        .toList(),
                                  ),
                                ),
                              if (fileLabels != null && fileLabels.isNotEmpty)
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 8),
                                  child: Wrap(
                                    spacing: 6,
                                    runSpacing: 6,
                                    children: List<Widget>.generate(fileLabels.length, (fi) {
                                      final name = fileLabels[fi];
                                      final ref = (fileRefs != null && fi < fileRefs.length) ? fileRefs[fi] : '';
                                      return Material(
                                        color: Theme.of(context).colorScheme.surfaceContainerHighest,
                                        borderRadius: BorderRadius.circular(8),
                                        child: InkWell(
                                          onTap: ref.isEmpty ? null : () => _openUserMessageFileRef(ref),
                                          borderRadius: BorderRadius.circular(8),
                                          child: Chip(
                                            avatar: Icon(
                                              Icons.insert_drive_file_outlined,
                                              size: 18,
                                              color: Theme.of(context).colorScheme.primary,
                                            ),
                                            label: ConstrainedBox(
                                              constraints: const BoxConstraints(maxWidth: 220),
                                              child: Text(
                                                name,
                                                overflow: TextOverflow.ellipsis,
                                                maxLines: 2,
                                                style: Theme.of(context).textTheme.bodySmall,
                                              ),
                                            ),
                                            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                            visualDensity: VisualDensity.compact,
                                            side: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
                                          ),
                                        ),
                                      );
                                    }),
                                  ),
                                ),
                              _ChatMessageText(
                                text: entry.key,
                                isUser: isUser,
                                plainText: _isDevBridgeFriend && widget.coreService.cursorChatPlainText,
                                theme: Theme.of(context),
                                isErrorMessage: isErrorBubble,
                              ),
                              if (isUploadingUserBubble)
                                Padding(
                                  padding: const EdgeInsets.only(top: 8),
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
                                      const SizedBox(width: 8),
                                      Flexible(
                                        child: Text(
                                          _activeUserSendStage?.trim().isNotEmpty == true
                                              ? _activeUserSendStage!
                                              : 'Sending...',
                                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                                color: Theme.of(context).colorScheme.onSurfaceVariant,
                                              ),
                                        ),
                                      ),
                                    ],
                                  ),
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
          if (_loading && !widget.isUserFriend)
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
                GestureDetector(
                  onLongPressStart: widget.isUserFriend && !_loading ? (_) => _startPushToTalk() : null,
                  onLongPressEnd: widget.isUserFriend && !_loading ? (_) => _stopPushToTalkAndSend() : null,
                  child: IconButton(
                    onPressed: _loading ? null : _toggleVoice,
                    icon: Icon(
                      _recordingPushToTalk
                          ? Icons.stop
                          : (_voiceListening ? Icons.mic : Icons.mic_none),
                      color: (_recordingPushToTalk || _voiceListening)
                          ? Theme.of(context).colorScheme.primary
                          : null,
                    ),
                    tooltip: widget.isUserFriend
                        ? (_recordingPushToTalk
                            ? 'Recording… release to send voice message'
                            : (_voiceListening
                                ? 'Stop voice input (long press for voice message)'
                                : 'Voice input (long press for voice message)'))
                        : (_voiceListening ? 'Stop voice input' : 'Voice input'),
                  ),
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: TextField(
                    controller: _inputController,
                    decoration: InputDecoration(
                      hintText: _inputHintText(),
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
                if (!_federatedE2eAttachmentsDisabled)
                  PopupMenuButton<String>(
                    enabled: !_loading,
                    tooltip: 'Photo',
                    icon: const Icon(Icons.add_a_photo_outlined),
                    onSelected: (value) async {
                      switch (value) {
                        case 'camera':
                          await _attachPhoto(presetSource: ImageSource.camera);
                          break;
                        case 'gallery':
                          await _attachPhoto(presetSource: ImageSource.gallery);
                          break;
                        default:
                          break;
                      }
                    },
                    itemBuilder: (context) => const [
                      PopupMenuItem(value: 'camera', child: Text('Take photo')),
                      PopupMenuItem(value: 'gallery', child: Text('Choose image')),
                    ],
                  ),
                const SizedBox(width: 4),
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

  static bool _isVmprintPreviewLink(String href) {
    final u = Uri.tryParse(href);
    if (u == null) return false;
    final p = (u.queryParameters['path'] ?? u.path).toLowerCase();
    return p.contains('preview.html') || p.endsWith('.preview.html') || p.endsWith('.ast.json');
  }

  Future<String> _fetchVmprintUiHint(Uri uri) async {
    try {
      final resp = await http.get(uri).timeout(const Duration(seconds: 4));
      if (resp.statusCode < 200 || resp.statusCode >= 300) return 'link';
      final body = resp.body;
      final m = RegExp(
        "<meta\\s+name=[\"']homeclaw-vmprint-ui-hint[\"']\\s+content=[\"'](inline|link)[\"']",
        caseSensitive: false,
      ).firstMatch(body);
      final hint = (m?.group(1) ?? '').toLowerCase();
      if (hint == 'inline' || hint == 'link') return hint;
    } catch (_) {}
    return 'link';
  }

  Future<void> _onTapLink(BuildContext context, String text, String? href, String title) async {
    if (href == null || href.isEmpty) return;
    Uri? uri = Uri.tryParse(href);
    if (uri == null) return;
    try {
      final isFile = _isFileLink(href);
      if (isFile && uri.scheme == 'file') {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
        return;
      }
      if ((uri.scheme == 'http' || uri.scheme == 'https') && _isVmprintPreviewLink(href)) {
        final prefs = await SharedPreferences.getInstance();
        final enabled = prefs.getBool('vmprint_native_preview') ?? false;
        if (enabled) {
          final hint = await _fetchVmprintUiHint(uri);
          if (hint != 'inline') {
            await launchUrl(uri, mode: LaunchMode.externalApplication);
            return;
          }
          if (!context.mounted) return;
          await Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => VmprintPreviewScreen(url: href)),
          );
          return;
        }
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
      onTapLink: (text, href, title) => _onTapLink(context, text, href, title),
      softLineBreak: true,
      shrinkWrap: true,
      fitContent: true,
    );
  }
}

/// Chip that opens full-screen video (data URL, local path, http(s), or Core `/files/...`).
class _VideoPlayChip extends StatelessWidget {
  final String videoRef;
  final String coreBaseUrl;
  final Map<String, String>? httpHeaders;

  const _VideoPlayChip({
    required this.videoRef,
    required this.coreBaseUrl,
    this.httpHeaders,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        onTap: () {
          Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (ctx) => _FullScreenVideoPage(
                videoRef: videoRef,
                coreBaseUrl: coreBaseUrl,
                httpHeaders: httpHeaders,
              ),
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

/// Full-screen video player: data URL, local file, http(s), or Core `/files/...`.
class _FullScreenVideoPage extends StatefulWidget {
  final String videoRef;
  final String coreBaseUrl;
  final Map<String, String>? httpHeaders;

  const _FullScreenVideoPage({
    required this.videoRef,
    required this.coreBaseUrl,
    this.httpHeaders,
  });

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
    final ref = widget.videoRef.trim();
    if (ref.isEmpty) {
      if (mounted) setState(() => _error = 'Invalid video');
      return;
    }
    try {
      if (ref.startsWith('data:video/') && ref.contains(',')) {
        final b64 = ref.split(',').last;
        final bytes = base64Decode(b64);
        final dir = await getTemporaryDirectory();
        final ext = ref.contains('webm') ? 'webm' : 'mp4';
        final file = File(path.join(dir.path, 'video_${DateTime.now().millisecondsSinceEpoch}.$ext'));
        await file.writeAsBytes(bytes);
        if (!mounted) return;
        _controller = VideoPlayerController.file(file);
      } else if (ref.startsWith('/files/') || ref.startsWith('/files/out')) {
        final base = widget.coreBaseUrl.replaceFirst(RegExp(r'/$'), '');
        final url = '$base$ref';
        _controller = VideoPlayerController.networkUrl(
          Uri.parse(url),
          httpHeaders: widget.httpHeaders ?? const {},
        );
      } else if (ref.startsWith('http://') || ref.startsWith('https://')) {
        _controller = VideoPlayerController.networkUrl(Uri.parse(ref));
      } else if (await File(ref).exists()) {
        _controller = VideoPlayerController.file(File(ref));
      } else {
        if (mounted) setState(() => _error = 'Video file not found');
        return;
      }
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

/// Play button for a voice message (data URL, local path, http(s), or Core `/files/...`).
class _AudioPlayButton extends StatefulWidget {
  final String audioRef;
  final String coreBaseUrl;
  final Map<String, String>? coreMediaHeaders;

  const _AudioPlayButton({
    required this.audioRef,
    required this.coreBaseUrl,
    this.coreMediaHeaders,
  });

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
    final ref = widget.audioRef.trim();
    if (ref.isEmpty) return;
    try {
      Source source;
      if (ref.startsWith('data:audio/') && ref.contains(',')) {
        final b64 = ref.split(',').last;
        final bytes = base64Decode(b64);
        final dir = await getTemporaryDirectory();
        final mime = ref.startsWith('data:') ? ref.split(';').first.replaceFirst('data:', '') : 'audio';
        final ext = mime == 'audio/webm' ? 'webm' : (mime == 'audio/ogg' ? 'ogg' : (mime == 'audio/mp4' ? 'm4a' : 'webm'));
        final file = File(path.join(dir.path, 'voice_${DateTime.now().millisecondsSinceEpoch}.$ext'));
        await file.writeAsBytes(bytes);
        source = DeviceFileSource(file.path);
      } else if (ref.startsWith('/files/') || ref.startsWith('/files/out')) {
        final base = widget.coreBaseUrl.replaceFirst(RegExp(r'/$'), '');
        final url = '$base$ref';
        final h = widget.coreMediaHeaders;
        if (h != null && h.isNotEmpty) {
          final resp = await http.get(Uri.parse(url), headers: h);
          if (resp.statusCode < 200 || resp.statusCode >= 300) {
            throw Exception('HTTP ${resp.statusCode}');
          }
          final dir = await getTemporaryDirectory();
          final file = File(path.join(dir.path, 'hc_audio_${DateTime.now().millisecondsSinceEpoch}.m4a'));
          await file.writeAsBytes(resp.bodyBytes);
          source = DeviceFileSource(file.path);
        } else {
          source = UrlSource(url);
        }
      } else if (ref.startsWith('http://') || ref.startsWith('https://')) {
        source = UrlSource(ref);
      } else if (await File(ref).exists()) {
        source = DeviceFileSource(ref);
      } else {
        if (mounted) {
          ScaffoldMessenger.maybeOf(context)?.showSnackBar(const SnackBar(content: Text('Audio file not found')));
        }
        return;
      }
      _completeSub?.cancel();
      _completeSub = _player.onPlayerComplete.listen((_) {
        if (mounted) setState(() => _playing = false);
      });
      await _player.play(source);
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
  final String imageRef;
  final String coreBaseUrl;
  final Map<String, String>? fetchHeaders;

  const _FullScreenImagePage({
    required this.imageRef,
    required this.coreBaseUrl,
    this.fetchHeaders,
  });

  @override
  Widget build(BuildContext context) {
    final trimmed = imageRef.trim();
    Widget bodyChild;
    if (trimmed.startsWith('data:image/')) {
      final bytes = _decodeDataUrlToBytes(trimmed);
      if (bytes != null && bytes.isNotEmpty) {
        bodyChild = Center(
          child: InteractiveViewer(
            minScale: 0.5,
            maxScale: 4.0,
            child: Image.memory(
              bytes,
              fit: BoxFit.contain,
              gaplessPlayback: true,
              errorBuilder: (_, __, ___) => const Icon(Icons.broken_image, color: Colors.white54, size: 64),
            ),
          ),
        );
      } else {
        bodyChild = const Center(child: Icon(Icons.broken_image, color: Colors.white54, size: 64));
      }
    } else {
      String? net;
      final u = Uri.tryParse(trimmed);
      if (u != null && u.hasScheme && (u.scheme == 'http' || u.scheme == 'https')) {
        net = trimmed;
      } else if (trimmed.startsWith('/')) {
        final base = coreBaseUrl.replaceFirst(RegExp(r'/$'), '');
        net = '$base$trimmed';
      }
      if (net != null) {
        bodyChild = Center(
          child: InteractiveViewer(
            minScale: 0.5,
            maxScale: 4.0,
            child: Image.network(
              net,
              fit: BoxFit.contain,
              headers: fetchHeaders,
              loadingBuilder: (c, child, prog) {
                if (prog == null) return child;
                return const SizedBox(
                  width: 48,
                  height: 48,
                  child: CircularProgressIndicator(color: Colors.white54, strokeWidth: 2),
                );
              },
              errorBuilder: (_, __, ___) => const Icon(Icons.broken_image, color: Colors.white54, size: 64),
            ),
          ),
        );
      } else {
        bodyChild = const Center(child: Icon(Icons.broken_image, color: Colors.white54, size: 64));
      }
    }
    return Scaffold(
      backgroundColor: Colors.black,
      body: GestureDetector(
        onTap: () => Navigator.of(context).pop(),
        behavior: HitTestBehavior.opaque,
        child: Stack(
          fit: StackFit.expand,
          children: [
            bodyChild,
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
