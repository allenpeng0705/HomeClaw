import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Provider family for chat screen state (messages, loading, scroll).
/// Family parameters: (userId, friendId, isUserFriend) as a string key.
/// Usage: chatStateProvider((userId, friendId, isUserFriend)).cast<ChatState>();
final chatStateProvider =
    StateNotifierProvider.family<ChatStateNotifier, ChatState, String>(
  (ref, key) => ChatStateNotifier(),
);

/// Key used to store and retrieve chat state from Provider family.
String chatStateKey({
  required String userId,
  required String? friendId,
  required bool isUserFriend,
}) {
  return '$userId|${friendId ?? ""}|${isUserFriend ? "1" : "0"}';
}

/// Snapshot of chat state needed for the main ListView body.
/// All fields are plain data (no methods) so it can be used as a value type.
class ChatViewSnapshot {
  final List<MapEntry<String, bool>> messages;
  final List<List<String>?> messageImages;
  final List<List<String>?> messageAudios;
  final List<List<String>?> messageVideos;
  final List<List<String>?> messageFileLabels;
  final List<List<String>?> messageFileRefs;
  final bool loading;
  final bool loadingMoreMessages;
  final bool hasMoreMessages;
  final int chatHistoryOffset;

  const ChatViewSnapshot({
    required this.messages,
    required this.messageImages,
    required this.messageAudios,
    required this.messageVideos,
    required this.messageFileLabels,
    required this.messageFileRefs,
    required this.loading,
    required this.loadingMoreMessages,
    required this.hasMoreMessages,
    required this.chatHistoryOffset,
  });
}

/// Core state for a single chat screen.
///
/// This notifier is owned by ChatScreen but managed via Riverpod.
/// All state is held in memory here; ChatScreen reads/writes via this notifier
/// so future work can move logic into the notifier without breaking existing UI.
class ChatState {
  /// List of (content, isUser) pairs — matches ChatScreen._messages.
  final List<MapEntry<String, bool>> messages;

  /// Optional image data URLs per message (null or empty when no images).
  final List<List<String>?> messageImages;

  /// Audio refs per message: local path, data:, http(s), or /files/...
  final List<List<String>?> messageAudios;

  /// Video refs per message.
  final List<List<String>?> messageVideos;

  /// File attachment display names per message.
  final List<List<String>?> messageFileLabels;

  /// File paths/URLs per message (parallel to fileLabels).
  final List<List<String>?> messageFileRefs;

  /// True while waiting for an AI reply.
  final bool loading;

  /// Progress message from Core during streaming (e.g. "Generating…").
  final String? loadingMessage;

  /// Rotating status index for fallback loading messages.
  final int loadingStatusIndex;

  /// True when scroll should auto-follow new messages.
  final bool autoFollowBottom;

  /// Current pagination offset (for scroll-up load).
  final int chatHistoryOffset;

  /// True while fetching older messages.
  final bool loadingMoreMessages;

  /// False once Core returns fewer messages than page size.
  final bool hasMoreMessages;

  /// After "Clear chat" on AI threads: hide rows at or before this timestamp.
  final double? aiChatHideBeforeTs;

  /// User inbox hide-before timestamp (user friends only).
  final double? userInboxHideBeforeTs;

  /// Rotating status messages when waiting for reply with no progress.
  static const List<String> loadingStatusMessages = [
    'Still working…',
    'Thinking…',
    'Almost there…',
  ];

  const ChatState({
    this.messages = const [],
    this.messageImages = const [],
    this.messageAudios = const [],
    this.messageVideos = const [],
    this.messageFileLabels = const [],
    this.messageFileRefs = const [],
    this.loading = false,
    this.loadingMessage,
    this.loadingStatusIndex = 0,
    this.autoFollowBottom = true,
    this.chatHistoryOffset = 0,
    this.loadingMoreMessages = false,
    this.hasMoreMessages = true,
    this.aiChatHideBeforeTs,
    this.userInboxHideBeforeTs,
  });

  ChatState copyWith({
    List<MapEntry<String, bool>>? messages,
    List<List<String>?>? messageImages,
    List<List<String>?>? messageAudios,
    List<List<String>?>? messageVideos,
    List<List<String>?>? messageFileLabels,
    List<List<String>?>? messageFileRefs,
    bool? loading,
    String? loadingMessage,
    bool clearLoadingMessage = false,
    int? loadingStatusIndex,
    bool? autoFollowBottom,
    int? chatHistoryOffset,
    bool? loadingMoreMessages,
    bool? hasMoreMessages,
    double? aiChatHideBeforeTs,
    bool clearAiChatHideBeforeTs = false,
    double? userInboxHideBeforeTs,
    bool clearUserInboxHideBeforeTs = false,
  }) {
    return ChatState(
      messages: messages ?? this.messages,
      messageImages: messageImages ?? this.messageImages,
      messageAudios: messageAudios ?? this.messageAudios,
      messageVideos: messageVideos ?? this.messageVideos,
      messageFileLabels: messageFileLabels ?? this.messageFileLabels,
      messageFileRefs: messageFileRefs ?? this.messageFileRefs,
      loading: loading ?? this.loading,
      loadingMessage: clearLoadingMessage ? null : (loadingMessage ?? this.loadingMessage),
      loadingStatusIndex: loadingStatusIndex ?? this.loadingStatusIndex,
      autoFollowBottom: autoFollowBottom ?? this.autoFollowBottom,
      chatHistoryOffset: chatHistoryOffset ?? this.chatHistoryOffset,
      loadingMoreMessages: loadingMoreMessages ?? this.loadingMoreMessages,
      hasMoreMessages: hasMoreMessages ?? this.hasMoreMessages,
      aiChatHideBeforeTs: clearAiChatHideBeforeTs ? null : (aiChatHideBeforeTs ?? this.aiChatHideBeforeTs),
      userInboxHideBeforeTs: clearUserInboxHideBeforeTs ? null : (userInboxHideBeforeTs ?? this.userInboxHideBeforeTs),
    );
  }
}

/// How many messages to fetch per page from Core.
const int chatPageSize = 50;

class ChatStateNotifier extends StateNotifier<ChatState> {
  ChatStateNotifier() : super(const ChatState());

  // ─── Message mutations ────────────────────────────────────────────

  /// Replace all messages with [list] loaded from ChatHistoryStore.
  void setMessagesFromStore(List<MapEntry<String, bool>> list) {
    final images = List<List<String>?>.filled(list.length, null);
    final audios = List<List<String>?>.filled(list.length, null);
    final videos = List<List<String>?>.filled(list.length, null);
    final fileLabels = List<List<String>?>.filled(list.length, null);
    final fileRefs = List<List<String>?>.filled(list.length, null);
    state = state.copyWith(
      messages: list,
      messageImages: images,
      messageAudios: audios,
      messageVideos: videos,
      messageFileLabels: fileLabels,
      messageFileRefs: fileRefs,
    );
  }

  /// Set messages from Core sync (AI chat) after filtering by [hideBeforeTs].
  void setMessagesFromCore(
    List<Map<String, dynamic>> list, {
    double? hideBeforeTs,
  }) {
    final filtered = hideBeforeTs == null
        ? list
        : list.where((m) {
            final ts = _parseTimestampSeconds(m);
            return ts == null || ts > hideBeforeTs;
          }).toList();
    if (filtered.isEmpty) {
      state = state.copyWith(
        messages: [],
        messageImages: [],
        messageAudios: [],
        messageVideos: [],
        messageFileLabels: [],
        messageFileRefs: [],
        chatHistoryOffset: 0,
        hasMoreMessages: list.length >= chatPageSize,
      );
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
    final fileLabels = List<List<String>?>.filled(messages.length, null);
    final fileRefs = List<List<String>?>.filled(messages.length, null);
    state = state.copyWith(
      messages: messages,
      messageImages: images,
      messageAudios: audios,
      messageVideos: videos,
      messageFileLabels: fileLabels,
      messageFileRefs: fileRefs,
      chatHistoryOffset: 0,
      hasMoreMessages: list.length >= chatPageSize,
    );
  }

  /// Prepend older messages fetched via pagination.
  void prependOlderMessages(List<Map<String, dynamic>> list) {
    if (list.isEmpty) {
      state = state.copyWith(hasMoreMessages: false, loadingMoreMessages: false);
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
    state = state.copyWith(
      messages: [...older, ...state.messages],
      messageImages: [...olderImages, ...state.messageImages],
      messageAudios: [...olderAudios, ...state.messageAudios],
      messageVideos: [...olderVideos, ...state.messageVideos],
      messageFileLabels: [...olderFileLabels, ...state.messageFileLabels],
      messageFileRefs: [...olderFileRefs, ...state.messageFileRefs],
      loadingMoreMessages: false,
      hasMoreMessages: list.length >= chatPageSize,
    );
  }

  /// Clear all messages.
  void clearMessages() {
    state = state.copyWith(
      messages: [],
      messageImages: [],
      messageAudios: [],
      messageVideos: [],
      messageFileLabels: [],
      messageFileRefs: [],
    );
  }

  /// Append a user or AI message pair. Used when a message is persisted locally.
  void appendMessage(String content, bool isUser) {
    state = state.copyWith(
      messages: [...state.messages, MapEntry(content, isUser)],
      messageImages: [...state.messageImages, null],
      messageAudios: [...state.messageAudios, null],
      messageVideos: [...state.messageVideos, null],
      messageFileLabels: [...state.messageFileLabels, null],
      messageFileRefs: [...state.messageFileRefs, null],
    );
  }

  /// Set media (images, audio, video, files) for the last message.
  void setLastMessageMedia({
    List<String>? images,
    List<String>? audios,
    List<String>? videos,
    List<String>? fileLabels,
    List<String>? fileRefs,
  }) {
    if (state.messages.isEmpty) return;
    final idx = state.messages.length - 1;
    final newImages = List<List<String>?>.from(state.messageImages);
    final newAudios = List<List<String>?>.from(state.messageAudios);
    final newVideos = List<List<String>?>.from(state.messageVideos);
    final newFileLabels = List<List<String>?>.from(state.messageFileLabels);
    final newFileRefs = List<List<String>?>.from(state.messageFileRefs);
    newImages[idx] = images;
    newAudios[idx] = audios;
    newVideos[idx] = videos;
    newFileLabels[idx] = fileLabels;
    newFileRefs[idx] = fileRefs;
    state = state.copyWith(
      messageImages: newImages,
      messageAudios: newAudios,
      messageVideos: newVideos,
      messageFileLabels: newFileLabels,
      messageFileRefs: newFileRefs,
    );
  }

  // ─── Loading state ────────────────────────────────────────────────

  void setLoading(bool value) {
    state = state.copyWith(loading: value);
  }

  void setLoadingMessage(String? msg) {
    if (msg == null) {
      state = state.copyWith(clearLoadingMessage: true);
    } else {
      state = state.copyWith(loadingMessage: msg);
    }
  }

  void advanceLoadingStatus() {
    state = state.copyWith(
      loadingStatusIndex: (state.loadingStatusIndex + 1) % ChatState.loadingStatusMessages.length,
    );
  }

  // ─── Scroll / pagination ─────────────────────────────────────────

  void setAutoFollowBottom(bool value) {
    state = state.copyWith(autoFollowBottom: value);
  }

  void setLoadingMore(bool value) {
    state = state.copyWith(loadingMoreMessages: value);
  }

  void setHasMore(bool value) {
    state = state.copyWith(hasMoreMessages: value);
  }

  void updateChatHistoryOffset(int offset) {
    state = state.copyWith(chatHistoryOffset: offset);
  }

  /// Returns a minimal snapshot of only the fields needed for the main chat list view.
  ChatViewSnapshot forChatView(ChatState state) => ChatViewSnapshot(
        messages: state.messages,
        messageImages: state.messageImages,
        messageAudios: state.messageAudios,
        messageVideos: state.messageVideos,
        messageFileLabels: state.messageFileLabels,
        messageFileRefs: state.messageFileRefs,
        loading: state.loading,
        loadingMoreMessages: state.loadingMoreMessages,
        hasMoreMessages: state.hasMoreMessages,
        chatHistoryOffset: state.chatHistoryOffset,
      );

  // ─── Hide-before timestamps ──────────────────────────────────────

  void setAiChatHideBeforeTs(double? ts) {
    if (ts == null) {
      state = state.copyWith(clearAiChatHideBeforeTs: true);
    } else {
      state = state.copyWith(aiChatHideBeforeTs: ts);
    }
  }

  void setUserInboxHideBeforeTs(double? ts) {
    if (ts == null) {
      state = state.copyWith(clearUserInboxHideBeforeTs: true);
    } else {
      state = state.copyWith(userInboxHideBeforeTs: ts);
    }
  }
}

/// Parse timestamp from a Core chat message map.
double? _parseTimestampSeconds(Map<String, dynamic> m) {
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

/// ─── Independent (non-chat-specific) providers ─────────────────────────

/// TTS auto-speak preference.
final ttsAutoSpeakProvider = StateProvider<bool>((ref) => false);

/// Voice input locale code (e.g. 'en-US').
final voiceInputLocaleProvider = StateProvider<String?>((ref) => null);

/// TTS currently speaking.
final ttsSpeakingProvider = StateProvider<bool>((ref) => false);

/// Core WebSocket connection status: null=unknown, true=connected, false=disconnected.
final coreConnectionStatusProvider = StateProvider<bool?>((ref) => null);

/// Cursor agent yolo preference.
final cursorAgentYoloProvider = StateProvider<bool>((ref) => false);

/// Claude Skip Permissions preference.
final claudeSkipPermissionsProvider = StateProvider<bool>((ref) => false);

/// Active cursor/Claude Code/Trae project directory path.
final cursorActiveCwdProvider = StateProvider<String>((ref) => '');

/// Current Claw-Code session ID (null = normal chat mode).
final clawcodeSessionIdProvider = StateProvider<String?>((ref) => null);