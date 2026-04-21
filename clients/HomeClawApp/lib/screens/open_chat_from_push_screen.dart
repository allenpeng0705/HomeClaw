import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/friend_list_providers.dart';
import '../widgets/homeclaw_snackbars.dart';

import '../core_service.dart';
import '../utils/friend_localization.dart';
import 'chat_screen.dart';

/// Shown when user opens the app by tapping an FCM (or APNs) notification.
/// Loads friends, finds the one matching [fromFriendName], then pushes [ChatScreen] and pops.
class OpenChatFromPushScreen extends ConsumerStatefulWidget {
  final CoreService coreService;
  final String fromFriendName;

  const OpenChatFromPushScreen({
    super.key,
    required this.coreService,
    required this.fromFriendName,
  });

  @override
  ConsumerState<OpenChatFromPushScreen> createState() => _OpenChatFromPushScreenState();
}

class _OpenChatFromPushScreenState extends ConsumerState<OpenChatFromPushScreen> {
  late final OpenChatFromPushNotifier _notifier;

  @override
  void initState() {
    super.initState();
    _notifier = ref.read(openChatFromPushProvider.notifier);
    WidgetsBinding.instance.addPostFrameCallback((_) => _openChat());
  }

  Future<void> _openChat() async {
    if (!mounted) return;
    final userId = widget.coreService.sessionUserId;
    if (userId == null || userId.isEmpty) {
      if (mounted) _notifier.setError('Not logged in');
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
        if (name.isEmpty) {
          // If push payload did not include sender, only auto-open HomeClaw.
          for (final f in list) {
            if ((f['name'] as String?)?.trim().toLowerCase() == 'homeclaw') {
              match = f;
              break;
            }
          }
        } else {
          _notifier.setError('Friend not found: $name');
          return;
        }
      }
      if (match == null) {
        _notifier.setError('No friends');
        return;
      }
      final friendId = (match['name'] as String?)?.trim() ?? 'HomeClaw';
      final presetFromApi = (match['preset'] as String?)?.trim();
      final t = (match['type'] as String?)?.trim().toLowerCase() ?? '';
      final isUserFriend = t == 'user' || t == 'remote_user';
      final toUserId = (match['user_id'] as String?)?.trim();
      final peerInst = (match['peer_instance_id'] as String?)?.trim();
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
            friendPreset: (presetFromApi != null && presetFromApi.isNotEmpty) ? presetFromApi : null,
            isUserFriend: isUserFriend,
            toUserId: toUserId?.isNotEmpty == true ? toUserId : null,
            remotePeerInstanceId: peerInst != null && peerInst.isNotEmpty ? peerInst : null,
          ),
        ),
      );
    } catch (e) {
      if (mounted) _notifier.setError(e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(openChatFromPushProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Opening…')),
      body: Center(
        child: state.error != null
            ? Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    HomeClawInlineErrorCard(message: state.error!, textAlign: TextAlign.center),
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
