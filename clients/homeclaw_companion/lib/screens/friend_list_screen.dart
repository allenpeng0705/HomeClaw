import 'package:flutter/material.dart';
import '../core_service.dart';
import 'chat_screen.dart';
import 'settings_screen.dart';

/// User list from Core (user.yml). One chat per user; tap to open chat and send that user's id with every message.
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
  List<Map<String, dynamic>> _users = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadUsers();
  }

  Future<void> _loadUsers() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await widget.coreService.getConfigUsers();
      if (mounted) {
        setState(() {
          _users = list;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
          _users = [];
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('HomeClaw'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _loadUsers,
            tooltip: 'Refresh user list',
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
                        FilledButton(onPressed: _loadUsers, child: const Text('Retry')),
                      ],
                    ),
                  ),
                )
              : _users.isEmpty
                  ? const Center(child: Text('No users in config. Add users in Core (user.yml).'))
                  : ListView.builder(
                      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
                      itemCount: _users.length,
                      itemBuilder: (context, index) {
                        final u = _users[index];
                        final userId = (u['id'] ?? u['name'] ?? '').toString();
                        final name = (u['name'] ?? userId).toString();
                        return _UserTile(
                          userId: userId,
                          userName: name,
                          userType: (u['type'] ?? '').toString(),
                          coreService: widget.coreService,
                          initialMessage: index == 0 ? widget.initialMessage : null,
                        );
                      },
                    ),
    );
  }
}

class _UserTile extends StatelessWidget {
  final String userId;
  final String userName;
  final String userType;
  final CoreService coreService;
  final String? initialMessage;

  const _UserTile({
    required this.userId,
    required this.userName,
    required this.userType,
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
        title: Text(userName),
        subtitle: Text(userType.isNotEmpty ? 'type: $userType' : ''),
        onTap: () {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (context) => ChatScreen(
                coreService: coreService,
                userId: userId,
                userName: userName,
                initialMessage: initialMessage,
              ),
            ),
          );
        },
      ),
    );
  }
}
