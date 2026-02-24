import 'dart:convert';

import 'package:hive_flutter/hive_flutter.dart';

/// Hive-backed store for Companion chat histories. One history per user (keyed by user id from user.yml).
class ChatHistoryStore {
  static const String _boxName = 'companion_chat';
  static const String _keyPrefix = 'chat_';

  static final ChatHistoryStore _instance = ChatHistoryStore._();
  factory ChatHistoryStore() => _instance;
  ChatHistoryStore._();

  static String _keyFor(String userId) => '$_keyPrefix${userId.replaceAll(RegExp(r'[^\w\-]'), '_')}';

  Box<String>? _box;

  /// True after init() completed successfully. If false, load returns [], save/clear no-op.
  static bool _initialized = false;
  static bool get isInitialized => _initialized;

  /// Initialize Hive and open the chat box. Call once at app startup (e.g. from main).
  /// On error sets _initialized = false so app can still run; chat history won't persist until next run.
  static Future<void> init() async {
    try {
      await Hive.initFlutter();
      await Hive.openBox<String>(_boxName);
      _initialized = true;
    } catch (_) {
      _initialized = false;
    }
  }

  Box<String>? get _boxSafe {
    if (!_initialized) return null;
    try {
      if (Hive.isBoxOpen(_boxName)) {
        _box ??= Hive.box<String>(_boxName);
        return _box;
      }
    } catch (_) {}
    return null;
  }

  /// One stored message: text, isUser, optional image data URLs.
  static Map<String, dynamic> messageToMap(String text, bool isUser, List<String>? images) {
    return {
      't': text,
      'u': isUser,
      'i': images == null || images.isEmpty ? null : images,
    };
  }

  static String mapText(Map<String, dynamic> m) => (m['t'] as String?) ?? '';
  static bool mapIsUser(Map<String, dynamic> m) => m['u'] as bool? ?? true;
  static List<String>? mapImages(Map<String, dynamic> m) {
    final i = m['i'];
    if (i == null) return null;
    if (i is List) return i.map((e) => e.toString()).toList();
    return null;
  }

  /// Load messages for [userId]. Returns list of (text, isUser, images?).
  /// Returns [] if Hive not initialized or on any error.
  List<MapEntry<MapEntry<String, bool>, List<String>?>> load(String userId) {
    try {
      final b = _boxSafe;
      if (b == null) return [];
      final raw = b.get(_keyFor(userId));
      if (raw == null || raw.isEmpty) return [];
      final list = jsonDecode(raw) as List<dynamic>?;
      if (list == null) return [];
      final out = <MapEntry<MapEntry<String, bool>, List<String>?>>[];
      for (final e in list) {
        if (e is! Map<String, dynamic>) continue;
        final text = mapText(e);
        final isUser = mapIsUser(e);
        final images = mapImages(e);
        out.add(MapEntry(MapEntry(text, isUser), images));
      }
      return out;
    } catch (_) {
      return [];
    }
  }

  /// Save messages for [userId]. [messages] is same shape as ChatScreen: list of (MapEntry(text, isUser), images?).
  /// No-op if Hive not initialized or on any error.
  Future<void> save(
    String userId,
    List<MapEntry<MapEntry<String, bool>, List<String>?>> messages,
  ) async {
    try {
      final b = _boxSafe;
      if (b == null) return;
      final list = messages.map((entry) {
        final text = entry.key.key;
        final isUser = entry.key.value;
        final images = entry.value;
        return messageToMap(text, isUser, images);
      }).toList();
      await b.put(_keyFor(userId), jsonEncode(list));
    } catch (_) {}
  }

  /// Clear history for one user. No-op if Hive not initialized or on error.
  Future<void> clear(String userId) async {
    try {
      final b = _boxSafe;
      if (b == null) return;
      await b.delete(_keyFor(userId));
    } catch (_) {}
  }

  /// Clear all chat histories. No-op if Hive not initialized or on error.
  Future<void> clearAll() async {
    try {
      final b = _boxSafe;
      if (b == null) return;
      for (final key in b.keys) {
        if (key is String && key.startsWith(_keyPrefix)) {
          await b.delete(key);
        }
      }
    } catch (_) {}
  }
}
