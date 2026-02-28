import 'package:flutter/material.dart';

/// Localized display names for known system friends (from Core presets).
/// Same meaning across languages: Finder → "Files", Note → "Private notes", Reminder → "Reminder".
/// Languages: en, zh, es, fr, de, it, ja, ko.
///
/// When you add a new system friend on Core, the app has no translation for it —
/// we use the **name from Core directly** (e.g. English "Assistant") so it always shows something.
const Map<String, Map<String, String>> _presetDisplayNames = {
  'finder': {
    'en': 'Files',
    'zh': '文件',
    'es': 'Archivos',
    'fr': 'Fichiers',
    'de': 'Dateien',
    'it': 'File',
    'ja': 'ファイル',
    'ko': '파일',
  },
  'reminder': {
    'en': 'Reminder',
    'zh': '提醒',
    'es': 'Recordatorio',
    'fr': 'Rappel',
    'de': 'Erinnerung',
    'it': 'Promemoria',
    'ja': 'リマインダー',
    'ko': '리마인더',
  },
  'note': {
    'en': 'Private Notes',
    'zh': '私密笔记',
    'es': 'Notas privadas',
    'fr': 'Notes privées',
    'de': 'Private Notizen',
    'it': 'Note private',
    'ja': 'プライベートメモ',
    'ko': '비공개 메모',
  },
  'HomeClaw': {
    'en': 'HomeClaw',
    'zh': 'HomeClaw',
    'es': 'HomeClaw',
    'fr': 'HomeClaw',
    'de': 'HomeClaw',
    'it': 'HomeClaw',
    'ja': 'HomeClaw',
    'ko': 'HomeClaw',
  },
};

/// Fallback when preset is unknown but name matches a known key.
const Map<String, Map<String, String>> _nameDisplayNames = {
  'Finder': {'en': 'Files', 'zh': '文件', 'es': 'Archivos', 'fr': 'Fichiers', 'de': 'Dateien', 'it': 'File', 'ja': 'ファイル', 'ko': '파일'},
  'Reminder': {'en': 'Reminder', 'zh': '提醒', 'es': 'Recordatorio', 'fr': 'Rappel', 'de': 'Erinnerung', 'it': 'Promemoria', 'ja': 'リマインダー', 'ko': '리마인더'},
  'Note': {'en': 'Private Notes', 'zh': '私密笔记', 'es': 'Notas privadas', 'fr': 'Notes privées', 'de': 'Private Notizen', 'it': 'Note private', 'ja': 'プライベートメモ', 'ko': '비공개 메모'},
};

/// Returns a localized display name for a friend from the API (name, preset).
/// For known presets/names we return a translated string; otherwise we use the
/// **name from Core as-is** (so new system friends you add on Core show their name, often English).
String localizedFriendDisplayName({
  required Map<String, dynamic> friend,
  required Locale locale,
}) {
  final rawName = friend['name'];
  final String name = (rawName is String && rawName.trim().isNotEmpty)
      ? rawName.trim()
      : 'HomeClaw';
  final String? preset = (friend['preset'] as String?)?.trim();
  final String lang = locale.languageCode;

  if (preset != null && preset.isNotEmpty) {
    final byPreset = _presetDisplayNames[preset];
    if (byPreset != null) {
      return byPreset[lang] ?? byPreset['en'] ?? name;
    }
  }

  final byName = _nameDisplayNames[name];
  if (byName != null) {
    return byName[lang] ?? byName['en'] ?? name;
  }

  // No translation for this friend (e.g. new system friend added on Core) — use Core's name directly.
  return name;
}

/// Order for system friends at the top of the list: HomeClaw, Reminder, Files (finder), Note, then others.
/// Returns a sort key (lower = first). Use with [sortFriendsWithSystemFirst].
int friendListSortOrder(Map<String, dynamic> friend) {
  final name = (friend['name'] as String?)?.trim() ?? '';
  final preset = (friend['preset'] as String?)?.trim() ?? '';
  if (name == 'HomeClaw') return 0;
  if (preset == 'reminder') return 1;
  if (preset == 'finder') return 2;
  if (preset == 'note') return 3;
  return 4;
}

/// Sorts the friends list so system friends appear first: HomeClaw, Reminder, Files, Note, then others.
/// Preserves relative order among "others".
void sortFriendsWithSystemFirst(List<Map<String, dynamic>> friends) {
  friends.sort((a, b) {
    final orderA = friendListSortOrder(a);
    final orderB = friendListSortOrder(b);
    if (orderA != orderB) return orderA.compareTo(orderB);
    return 0;
  });
}
