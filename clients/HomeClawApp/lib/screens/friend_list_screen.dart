import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:home_claw_app/l10n/app_localizations.dart';
import '../core_service.dart';
import '../utils/friend_localization.dart';
import 'add_ai_friend_screen.dart';
import 'add_friend_screen.dart';
import 'chat_screen.dart';
import 'friend_requests_screen.dart';
import 'login_screen.dart';
import 'settings_screen.dart';

/// Bundled preset thumbnail assets (used when Core does not serve one). No download; shipped with app.
const Set<String> _bundledPresetKeys = {'reminder', 'note', 'finder'};
String? _bundledPresetAssetPath(String? preset) {
  final p = (preset ?? '').trim().toLowerCase();
  if (p.isEmpty || !_bundledPresetKeys.contains(p)) return null;
  return 'assets/preset_friends/$p.png';
}

/// Known localized names -> preset key (so avatar works when API returns localized friend name).
const Map<String, String> _localizedNameToPreset = {
  'reminder': 'reminder', 'finder': 'finder', 'note': 'note', 'files': 'finder',
  '提醒': 'reminder', '文件': 'finder', '私密笔记': 'note',
  'recordatorio': 'reminder', 'archivos': 'finder', 'notas privadas': 'note',
  'rappel': 'reminder', 'fichiers': 'finder', 'notes privées': 'note',
  'erinnerung': 'reminder', 'dateien': 'finder', 'private notizen': 'note',
  'promemoria': 'reminder', 'file': 'finder', 'note private': 'note',
  'リマインダー': 'reminder', 'ファイル': 'finder', 'プライベートメモ': 'note',
  '리마인더': 'reminder', '비공개 메모': 'note',
};

/// Derive preset key from friend name when API does not return preset (e.g. Reminder→reminder, Note/Notes→note, Finder/Files→finder).
/// Handles English and localized names (zh, es, fr, de, it, ja, ko) so thumbnails show regardless of locale.
String? _presetKeyFromFriendName(String name) {
  final n = (name).trim();
  if (n.isEmpty) return null;
  final nLower = n.toLowerCase();
  final byKey = _localizedNameToPreset[nLower];
  if (byKey != null) return byKey;
  final byKeyExact = _localizedNameToPreset[n];
  if (byKeyExact != null) return byKeyExact;
  if (nLower == 'reminder' || nLower.contains('reminder')) return 'reminder';
  if (nLower == 'finder' || nLower == 'files' || nLower.contains('finder') || nLower.contains('file')) return 'finder';
  if (nLower == 'note' || nLower == 'notes' || nLower.contains('note')) return 'note';
  return null;
}

/// Friends list for the logged-in user (from GET /api/me/friends).
/// If not logged in, shows LoginScreen. Tap a friend to open chat with friendId.
/// When [initialPushFromFriend] is set (app opened by tapping FCM notification), open that chat after friends load.
class FriendListScreen extends StatefulWidget {
  final CoreService coreService;
  final String? initialMessage;
  final String? initialPushFromFriend;

  const FriendListScreen({
    super.key,
    required this.coreService,
    this.initialMessage,
    this.initialPushFromFriend,
  });

  @override
  State<FriendListScreen> createState() => _FriendListScreenState();
}

class _FriendListScreenState extends State<FriendListScreen> {
  List<Map<String, dynamic>> _friends = [];
  bool _loading = true;
  String? _error;
  String? _initialPushFromFriend;
  Uint8List? _myAvatarBytes;
  /// User ids (of user friends) that have at least one unread message in inbox.
  Set<String> _unreadUserIds = {};
  StreamSubscription<Map<String, dynamic>>? _pushSubscription;

  @override
  void initState() {
    super.initState();
    _initialPushFromFriend = widget.initialPushFromFriend;
    _loadFriends();
    _loadMyAvatar();
    _pushSubscription = widget.coreService.pushMessageStream.listen((push) {
      final source = (push['source'] as String?)?.trim();
      if (source == 'user_message' && mounted) _loadUnreadState();
    });
  }

  @override
  void dispose() {
    _pushSubscription?.cancel();
    super.dispose();
  }

  Future<void> _loadUnreadState() async {
    final userId = widget.coreService.sessionUserId?.trim();
    if (userId == null || userId.isEmpty || !mounted) return;
    try {
      final data = await widget.coreService.getUserInbox(userId: userId, limit: 200);
      final list = data['messages'] as List<dynamic>? ?? [];
      final unread = <String>{};
      for (final f in _friends) {
        if ((f['type'] as String?)?.trim().toLowerCase() != 'user') continue;
        final otherId = (f['user_id'] as String?)?.trim();
        if (otherId == null || otherId.isEmpty) continue;
        final lastRead = await widget.coreService.getUserInboxLastRead(userId, otherId);
        for (final m in list) {
          if (m is! Map) continue;
          final fromId = (m['from_user_id'] as String?)?.trim();
          if (fromId != otherId) continue;
          final at = (m['created_at'] as num?)?.toDouble();
          if (at != null && (lastRead == null || at > lastRead)) {
            unread.add(otherId);
            break;
          }
        }
      }
      if (mounted) setState(() => _unreadUserIds = unread);
    } catch (_) {}
  }

  Future<void> _loadMyAvatar() async {
    final bytes = await widget.coreService.getMyAvatarCached();
    if (mounted && bytes != null && bytes.isNotEmpty) {
      setState(() => _myAvatarBytes = bytes);
    }
  }

  Future<void> _loadFriends() async {
    if (!widget.coreService.isLoggedIn) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await widget.coreService.getFriends();
      final sorted = List<Map<String, dynamic>>.from(list);
      sortFriendsWithSystemFirst(sorted);
      if (mounted) {
        setState(() {
          _friends = sorted;
          _loading = false;
        });
        _loadUnreadState();
        _openInitialPushChatIfNeeded();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
          _friends = [];
        });
      }
    }
  }

  void _openInitialPushChatIfNeeded() {
    final name = _initialPushFromFriend?.trim();
    if (name == null || name.isEmpty || _friends.isEmpty) return;
    _initialPushFromFriend = null;
    final nameLower = name.toLowerCase();
    Map<String, dynamic>? match;
    for (final f in _friends) {
      final n = (f['name'] as String?)?.trim() ?? '';
      if (n.isNotEmpty && (n == name || n.toLowerCase() == nameLower)) {
        match = f;
        break;
      }
    }
    if (match == null) {
      for (final f in _friends) {
        if ((f['name'] as String?)?.trim().toLowerCase() == 'homeclaw') {
          match = f;
          break;
        }
      }
    }
    if (match == null) return;
    final userId = widget.coreService.sessionUserId;
    if (userId == null || userId.isEmpty) return;
    final friendId = (match['name'] as String?)?.trim() ?? 'HomeClaw';
    final isUserFriend = (match['type'] as String?)?.trim().toLowerCase() == 'user';
    final toUserId = (match['user_id'] as String?)?.trim();
    final locale = Localizations.localeOf(context);
    final displayName = localizedFriendDisplayName(friend: match, locale: locale);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      Navigator.maybeOf(context)?.push(
        MaterialPageRoute(
          builder: (context) => ChatScreen(
            coreService: widget.coreService,
            userId: userId,
            userName: displayName,
            friendId: friendId,
            initialMessage: widget.initialMessage,
            isUserFriend: isUserFriend,
            toUserId: toUserId?.isNotEmpty == true ? toUserId : null,
          ),
        ),
      );
    });
  }

  Future<void> _logout() async {
    await widget.coreService.clearSession();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (context) => LoginScreen(coreService: widget.coreService),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.coreService.isLoggedIn) {
      return LoginScreen(coreService: widget.coreService);
    }
    final l10n = AppLocalizations.of(context)!;
    final hasMyAvatar = _myAvatarBytes != null && _myAvatarBytes!.isNotEmpty;
    return Scaffold(
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircleAvatar(
              radius: 18,
              backgroundColor: Theme.of(context).colorScheme.primaryContainer,
              backgroundImage: hasMyAvatar ? MemoryImage(_myAvatarBytes!) : null,
              child: hasMyAvatar ? null : Icon(Icons.person, color: Theme.of(context).colorScheme.onPrimaryContainer, size: 22),
            ),
            const SizedBox(width: 10),
            Text(l10n.homeClaw),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.person_add),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => AddFriendScreen(coreService: widget.coreService),
                ),
              );
            },
            tooltip: 'Add friend',
          ),
          IconButton(
            icon: const Icon(Icons.smart_toy_outlined),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => AddAIFriendScreen(coreService: widget.coreService),
                ),
              ).then((_) => _loadFriends());
            },
            tooltip: 'Add AI friend',
          ),
          IconButton(
            icon: const Icon(Icons.mail_outline),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => FriendRequestsScreen(
                    coreService: widget.coreService,
                    onAccept: _loadFriends,
                  ),
                ),
              ).then((_) => _loadFriends());
            },
            tooltip: 'Friend requests',
          ),
          PopupMenuButton<String>(
            icon: const Icon(Icons.more_vert),
            tooltip: 'More',
            onSelected: (value) {
              switch (value) {
                case 'refresh':
                  if (!_loading) _loadFriends();
                  break;
                case 'settings':
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (context) => SettingsScreen(coreService: widget.coreService),
                    ),
                  ).then((_) => _loadMyAvatar());
                  break;
                case 'logout':
                  _logout();
                  break;
              }
            },
            itemBuilder: (context) => [
              PopupMenuItem(value: 'refresh', enabled: !_loading, child: Row(children: [const Icon(Icons.refresh, size: 20), const SizedBox(width: 16), Text(l10n.refreshFriends)])),
              const PopupMenuItem(value: 'settings', child: Row(children: [Icon(Icons.settings, size: 20), SizedBox(width: 16), Text('Settings')])),
              PopupMenuItem(value: 'logout', child: Row(children: [const Icon(Icons.logout, size: 20), const SizedBox(width: 16), Text(l10n.logOut)])),
            ],
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                        const SizedBox(height: 16),
                        FilledButton(onPressed: _loadFriends, child: Text(l10n.retry)),
                      ],
                    ),
                  ),
                )
              : _friends.isEmpty
                  ? Center(child: Text(l10n.noFriends))
                  : ListView.builder(
                      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
                      itemCount: _friends.length,
                      itemBuilder: (context, index) {
                        final f = _friends[index];
                        final friendId = (f['name'] as String?)?.trim() ?? 'HomeClaw';
                        final locale = Localizations.localeOf(context);
                        final displayName = localizedFriendDisplayName(friend: f, locale: locale);
                        final isUserFriend = (f['type'] as String?)?.trim().toLowerCase() == 'user';
                        final toUserId = (f['user_id'] as String?)?.trim();
                        final hasUnread = isUserFriend && toUserId != null && _unreadUserIds.contains(toUserId);
                        final preset = (f['preset'] as String?)?.trim();
                        final presetForAvatar = preset?.isNotEmpty == true
                            ? preset
                            : _presetKeyFromFriendName(friendId);
                        return _FriendTile(
                          userId: widget.coreService.sessionUserId!,
                          friendId: friendId,
                          displayName: displayName,
                          coreService: widget.coreService,
                          preset: presetForAvatar,
                          initialMessage: index == 0 ? widget.initialMessage : null,
                          isUserFriend: isUserFriend,
                          toUserId: toUserId?.isNotEmpty == true ? toUserId : null,
                          hasUnread: hasUnread,
                          onRemoved: _loadFriends,
                          onReturnFromChat: _loadUnreadState,
                        );
                      },
                    ),
    );
  }
}

class _FriendTile extends StatefulWidget {
  final String userId;
  final String friendId;
  final String displayName;
  final CoreService coreService;
  /// Preset key (e.g. reminder, note, finder) when this friend is a preset; used to request preset thumbnail from Core.
  final String? preset;
  final String? initialMessage;
  /// True when this friend is a real person (type: user); chat uses user-message API and push-to-talk.
  final bool isUserFriend;
  /// When [isUserFriend], the other user's id for POST /api/user-message.
  final String? toUserId;
  /// When true, show a red dot to indicate new messages from this user.
  final bool hasUnread;
  final VoidCallback? onRemoved;
  /// Called when returning from chat so the list can refresh unread state.
  final VoidCallback? onReturnFromChat;

  const _FriendTile({
    required this.userId,
    required this.friendId,
    required this.displayName,
    required this.coreService,
    this.preset,
    this.initialMessage,
    this.isUserFriend = false,
    this.toUserId,
    this.hasUnread = false,
    this.onRemoved,
    this.onReturnFromChat,
  });

  @override
  State<_FriendTile> createState() => _FriendTileState();
}

class _FriendTileState extends State<_FriendTile> {
  Uint8List? _avatarBytes;

  @override
  void initState() {
    super.initState();
    _loadAvatar();
  }

  Future<void> _loadAvatar() async {
    final url = widget.isUserFriend && (widget.toUserId ?? '').trim().isNotEmpty
        ? widget.coreService.userAvatarUrl(widget.toUserId!.trim())
        : widget.coreService.friendAvatarUrl(
            widget.friendId.trim(),
            preset: widget.preset,
          );
    final bytes = await widget.coreService.fetchAvatarWithAuth(url);
    if (mounted && bytes != null && bytes.isNotEmpty) {
      setState(() => _avatarBytes = bytes);
    }
  }

  /// Id to send to DELETE /api/me/friends/{id}: for user friend use toUserId, for AI use friendId.
  String get _deleteId => (widget.isUserFriend && (widget.toUserId ?? '').trim().isNotEmpty) ? widget.toUserId!.trim() : widget.friendId;

  /// HomeClaw cannot be removed (system default).
  bool get _canRemove => widget.friendId.trim().toLowerCase() != 'homeclaw';

  Future<void> _removeFriend(BuildContext context) async {
    if (!_canRemove) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(widget.isUserFriend ? 'Remove user friend?' : 'Remove AI friend?'),
        content: Text(
          widget.isUserFriend
              ? 'Remove ${widget.displayName} from your friends? They will no longer appear in your list.'
              : 'Remove ${widget.displayName} from your friends? You can add them again later.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            style: FilledButton.styleFrom(backgroundColor: Theme.of(ctx).colorScheme.error),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    if (!context.mounted) return;
    try {
      await widget.coreService.deleteAIFriend(_deleteId);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('${widget.displayName} removed')));
        widget.onRemoved?.call();
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to remove: $e'), backgroundColor: Theme.of(context).colorScheme.errorContainer),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasThumbnail = _avatarBytes != null && _avatarBytes!.isNotEmpty;
    final bundledPath = _bundledPresetAssetPath(widget.preset);
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Stack(
          clipBehavior: Clip.none,
          children: [
            ClipOval(
              child: SizedBox(
                width: 40,
                height: 40,
                child: hasThumbnail
                    ? Image.memory(
                        _avatarBytes!,
                        fit: BoxFit.cover,
                        width: 40,
                        height: 40,
                      )
                    : bundledPath != null
                        ? Image.asset(
                            bundledPath,
                            fit: BoxFit.cover,
                            width: 40,
                            height: 40,
                            errorBuilder: (_, __, ___) => ColoredBox(
                              color: theme.colorScheme.primaryContainer,
                              child: Icon(
                                widget.isUserFriend ? Icons.person : Icons.smart_toy,
                                color: theme.colorScheme.onPrimaryContainer,
                                size: 24,
                              ),
                            ),
                          )
                        : ColoredBox(
                            color: theme.colorScheme.primaryContainer,
                            child: Icon(
                              widget.isUserFriend ? Icons.person : Icons.smart_toy,
                              color: theme.colorScheme.onPrimaryContainer,
                              size: 24,
                            ),
                          ),
              ),
            ),
            if (widget.hasUnread)
              Positioned(
                right: -2,
                top: -2,
                child: Container(
                  width: 12,
                  height: 12,
                  decoration: BoxDecoration(
                    color: theme.colorScheme.error,
                    shape: BoxShape.circle,
                    border: Border.all(color: theme.colorScheme.surface, width: 1.5),
                  ),
                ),
              ),
          ],
        ),
        title: Text(widget.displayName),
        subtitle: widget.isUserFriend ? Text('User', style: Theme.of(context).textTheme.bodySmall) : null,
        onLongPress: _canRemove ? () => _removeFriend(context) : null,
        onTap: () {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (context) => ChatScreen(
                coreService: widget.coreService,
                userId: widget.userId,
                userName: widget.displayName,
                friendId: widget.friendId,
                initialMessage: widget.initialMessage,
                isUserFriend: widget.isUserFriend,
                toUserId: widget.toUserId,
              ),
            ),
          ).then((_) => widget.onReturnFromChat?.call());
        },
      ),
    );
  }
}
