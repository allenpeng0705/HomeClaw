// Helpers for Cursor / Claude Code / Trae dev-bridge friends in the Companion app.
// Core may expose preset on /api/me/friends; older configs used friend ids (cursor, claudecode, trae).

/// `cursor`, `claude`, or `trae` for [/api/cursor-bridge/*] calls, or null if not a dev-bridge friend.
String? devBridgeBackend({String? friendPreset, String? friendId}) {
  final p = (friendPreset ?? '').trim().toLowerCase();
  if (p == 'cursor' || p == 'claude' || p == 'trae') return p;
  final fid = (friendId ?? '').trim().toLowerCase();
  if (fid == 'claudecode') return 'claude';
  if (fid == 'cursor') return 'cursor';
  if (fid == 'trae') return 'trae';
  return null;
}

bool isDevBridgeFriend({
  required bool isUserFriend,
  String? friendPreset,
  String? friendId,
}) {
  if (isUserFriend) return false;
  return devBridgeBackend(friendPreset: friendPreset, friendId: friendId) != null;
}

/// Trae is disabled in-app; match by preset or legacy friend id.
bool isTraeDisabledInCompanion({
  required bool isUserFriend,
  String? friendPreset,
  String? friendId,
}) {
  if (isUserFriend) return false;
  final p = (friendPreset ?? '').trim().toLowerCase();
  final fid = (friendId ?? '').trim().toLowerCase();
  return p == 'trae' || fid == 'trae';
}
