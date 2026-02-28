import 'package:flutter/material.dart';
import 'package:home_claw_app/l10n/app_localizations.dart';
import '../core_service.dart';
import '../utils/friend_localization.dart';
import 'chat_screen.dart';
import 'login_screen.dart';
import 'settings_screen.dart';

/// Friends list for the logged-in user (from GET /api/me/friends).
/// If not logged in, shows LoginScreen. Tap a friend to open chat with friendId.
class FriendListScreen extends StatefulWidget {
  final CoreService coreService;
  final String? initialMessage;

  const FriendListScreen({
    super.key,
    required this.coreService,
    this.initialMessage,
  });

  @override
  State<FriendListScreen> createState() => _FriendListScreenState();
}

class _FriendListScreenState extends State<FriendListScreen> {
  List<Map<String, dynamic>> _friends = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
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
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _loadFriends,
            tooltip: l10n.refreshFriends,
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
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: _logout,
            tooltip: l10n.logOut,
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
                        return _FriendTile(
                          userId: widget.coreService.sessionUserId!,
                          friendId: friendId,
                          displayName: displayName,
                          coreService: widget.coreService,
                          initialMessage: index == 0 ? widget.initialMessage : null,
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

  const _FriendTile({
    required this.userId,
    required this.friendId,
    required this.displayName,
    required this.coreService,
    this.initialMessage,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: theme.colorScheme.primaryContainer,
          child: Icon(Icons.person, color: theme.colorScheme.onPrimaryContainer),
        ),
        title: Text(displayName),
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
              ),
            ),
          );
        },
      ),
    );
  }
}
