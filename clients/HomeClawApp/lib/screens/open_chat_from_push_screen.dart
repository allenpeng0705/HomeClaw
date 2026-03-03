import 'package:flutter/material.dart';

import '../core_service.dart';
import '../utils/friend_localization.dart';
import 'chat_screen.dart';

/// Shown when user opens the app by tapping an FCM (or APNs) notification.
/// Loads friends, finds the one matching [fromFriendName], then pushes [ChatScreen] and pops.
class OpenChatFromPushScreen extends StatefulWidget {
  final CoreService coreService;
  final String fromFriendName;

  const OpenChatFromPushScreen({
    super.key,
    required this.coreService,
    required this.fromFriendName,
  });

  @override
  State<OpenChatFromPushScreen> createState() => _OpenChatFromPushScreenState();
}

class _OpenChatFromPushScreenState extends State<OpenChatFromPushScreen> {
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _openChat());
  }

  Future<void> _openChat() async {
    if (!mounted) return;
    final userId = widget.coreService.sessionUserId;
    if (userId == null || userId.isEmpty) {
      if (mounted) setState(() => _error = 'Not logged in');
      return;
    }
    try {
      final list = await widget.coreService.getFriends();
      final name = widget.fromFriendName.trim();
      final nameLower = name.toLowerCase();
      Map<String, dynamic>? match;
      for (final f in list) {
        final n = (f['name'] as String?)?.trim() ?? '';
        if (n.isEmpty) continue;
        if (n == name || n.toLowerCase() == nameLower) {
          match = f;
          break;
        }
      }
      if (!mounted) return;
      if (match == null) {
        match = list.isNotEmpty ? list.first : null;
        // Prefer HomeClaw if no exact match (reminder is usually from system).
        for (final f in list) {
          if ((f['name'] as String?)?.trim().toLowerCase() == 'homeclaw') {
            match = f;
            break;
          }
        }
      }
      if (match == null) {
        setState(() => _error = 'No friends');
        return;
      }
      final friendId = (match['name'] as String?)?.trim() ?? 'HomeClaw';
      final isUserFriend = (match['type'] as String?)?.trim().toLowerCase() == 'user';
      final toUserId = (match['user_id'] as String?)?.trim();
      final locale = Localizations.localeOf(context);
      final displayName = localizedFriendDisplayName(friend: match, locale: locale);
      if (!mounted) return;
      Navigator.maybeOf(context)?.pushReplacement(
        MaterialPageRoute(
          builder: (context) => ChatScreen(
            coreService: widget.coreService,
            userId: userId,
            userName: displayName,
            friendId: friendId,
            isUserFriend: isUserFriend,
            toUserId: toUserId?.isNotEmpty == true ? toUserId : null,
          ),
        ),
      );
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Opening…')),
      body: Center(
        child: _error != null
            ? Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                    const SizedBox(height: 16),
                    FilledButton(
                      onPressed: () => Navigator.maybeOf(context)?.maybePop(),
                      child: const Text('Back'),
                    ),
                  ],
                ),
              )
            : const CircularProgressIndicator(),
      ),
    );
  }
}
