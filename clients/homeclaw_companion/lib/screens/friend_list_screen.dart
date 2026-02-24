import 'package:flutter/material.dart';
import '../core_service.dart';
import 'chat_screen.dart';
import 'settings_screen.dart';

/// Chat target: System (Core assistant) or Friend (Friends plugin).
enum ChatType {
  system,
  friend,
}

/// Friend list (WhatsApp-style): two entries — System and Friend.
/// Tapping one opens the chat for that target.
class FriendListScreen extends StatelessWidget {
  final CoreService coreService;
  final String? initialMessage;

  const FriendListScreen({
    super.key,
    required this.coreService,
    this.initialMessage,
  });

  static String titleFor(ChatType type) {
    switch (type) {
      case ChatType.system:
        return 'System';
      case ChatType.friend:
        return 'Friend';
    }
  }

  static String subtitleFor(ChatType type) {
    switch (type) {
      case ChatType.system:
        return 'Talk with Core (main assistant). Identity is set in Settings.';
      case ChatType.friend:
        return 'Talk with the Friend persona (Friends plugin).';
    }
  }

  static IconData iconFor(ChatType type) {
    switch (type) {
      case ChatType.system:
        return Icons.smart_toy;
      case ChatType.friend:
        return Icons.person;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('HomeClaw'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => SettingsScreen(coreService: coreService),
                ),
              );
            },
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
        children: [
          _FriendTile(
            chatType: ChatType.system,
            coreService: coreService,
            initialMessage: initialMessage,
          ),
          _FriendTile(
            chatType: ChatType.friend,
            coreService: coreService,
            initialMessage: null,
          ),
        ],
      ),
    );
  }
}

class _FriendTile extends StatelessWidget {
  final ChatType chatType;
  final CoreService coreService;
  final String? initialMessage;

  const _FriendTile({
    required this.chatType,
    required this.coreService,
    this.initialMessage,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: theme.colorScheme.primaryContainer,
          child: Icon(FriendListScreen.iconFor(chatType), color: theme.colorScheme.onPrimaryContainer),
        ),
        title: Text(
          FriendListScreen.titleFor(chatType),
          style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
        ),
        subtitle: Text(
          FriendListScreen.subtitleFor(chatType),
          style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: () {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (context) => ChatScreen(
                coreService: coreService,
                chatType: chatType,
                initialMessage: initialMessage,
              ),
            ),
          );
        },
      ),
    );
  }
}
