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

  @override
  void initState() {
    super.initState();
    _initialPushFromFriend = widget.initialPushFromFriend;
    _loadFriends();
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
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.homeClaw),
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
                  );
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
                        return _FriendTile(
                          userId: widget.coreService.sessionUserId!,
                          friendId: friendId,
                          displayName: displayName,
                          coreService: widget.coreService,
                          initialMessage: index == 0 ? widget.initialMessage : null,
                          isUserFriend: isUserFriend,
                          toUserId: toUserId?.isNotEmpty == true ? toUserId : null,
                          onRemoved: _loadFriends,
                        );
                      },
                    ),
    );
  }
}

class _FriendTile extends StatelessWidget {
  final String userId;
  final String friendId;
  final String displayName;
  final CoreService coreService;
  final String? initialMessage;
  /// True when this friend is a real person (type: user); chat uses user-message API and push-to-talk.
  final bool isUserFriend;
  /// When [isUserFriend], the other user's id for POST /api/user-message.
  final String? toUserId;
  final VoidCallback? onRemoved;

  const _FriendTile({
    required this.userId,
    required this.friendId,
    required this.displayName,
    required this.coreService,
    this.initialMessage,
    this.isUserFriend = false,
    this.toUserId,
    this.onRemoved,
  });

  /// Id to send to DELETE /api/me/friends/{id}: for user friend use toUserId, for AI use friendId.
  String get _deleteId => (isUserFriend && (toUserId ?? '').trim().isNotEmpty) ? toUserId!.trim() : friendId;

  /// HomeClaw cannot be removed (system default).
  bool get _canRemove => friendId.trim().toLowerCase() != 'homeclaw';

  Future<void> _removeFriend(BuildContext context) async {
    if (!_canRemove) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(isUserFriend ? 'Remove user friend?' : 'Remove AI friend?'),
        content: Text(
          isUserFriend
              ? 'Remove $displayName from your friends? They will no longer appear in your list.'
              : 'Remove $displayName from your friends? You can add them again later.',
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
    try {
      await coreService.deleteAIFriend(_deleteId);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$displayName removed')));
        onRemoved?.call();
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
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: theme.colorScheme.primaryContainer,
          child: Icon(
            isUserFriend ? Icons.person : Icons.smart_toy,
            color: theme.colorScheme.onPrimaryContainer,
          ),
        ),
        title: Text(displayName),
        subtitle: isUserFriend ? Text('User', style: Theme.of(context).textTheme.bodySmall) : null,
        trailing: _canRemove
            ? IconButton(
                icon: const Icon(Icons.more_vert),
                onPressed: () => _removeFriend(context),
                tooltip: 'Remove friend',
              )
            : null,
        onTap: () {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (context) => ChatScreen(
                coreService: coreService,
                userId: userId,
                userName: displayName,
                friendId: friendId,
                initialMessage: initialMessage,
                isUserFriend: isUserFriend,
                toUserId: toUserId,
              ),
            ),
          );
        },
      ),
    );
  }
}
