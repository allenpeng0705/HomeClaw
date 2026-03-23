import 'package:flutter/material.dart';
import '../core_service.dart';
import '../widgets/homeclaw_snackbars.dart';
import 'add_remote_friend_screen.dart';

/// Add Friend: list users on this Core, or (when federation is on) send a remote request.
class AddFriendScreen extends StatefulWidget {
  final CoreService coreService;

  const AddFriendScreen({super.key, required this.coreService});

  @override
  State<AddFriendScreen> createState() => _AddFriendScreenState();
}

class _AddFriendScreenState extends State<AddFriendScreen> with SingleTickerProviderStateMixin {
  List<Map<String, dynamic>> _users = [];
  bool _loading = true;
  String? _error;
  final Set<String> _sending = {};
  TabController? _tabController;

  @override
  void initState() {
    super.initState();
    if (widget.coreService.federationEnabled) {
      _tabController = TabController(length: 2, vsync: this);
    }
    _load();
  }

  @override
  void dispose() {
    _tabController?.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await widget.coreService.getUsers();
      final friends = await widget.coreService.getFriends();
      final alreadyFriendIds = <String>{};
      for (final f in friends) {
        final type = (f['type'] as String?)?.trim().toLowerCase();
        if (type == 'user' || type == 'remote_user') {
          final uid = (f['user_id'] as String?)?.trim();
          if (uid != null && uid.isNotEmpty) alreadyFriendIds.add(uid);
        }
      }
      final filtered = list.where((u) {
        final id = (u['id'] as String?)?.trim() ?? '';
        return id.isNotEmpty && !alreadyFriendIds.contains(id);
      }).toList();
      if (mounted) {
        setState(() {
          _users = filtered;
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

  Future<void> _sendRequest(Map<String, dynamic> user) async {
    final id = (user['id'] as String?)?.trim() ?? '';
    final name = (user['name'] as String?)?.trim() ?? id;
    if (id.isEmpty) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Send friend request?'),
        content: Text('Send a friend request to $name? They can accept or decline.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text('Send request')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _sending.add(id));
    try {
      await widget.coreService.sendFriendRequest(id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Request sent to $name')));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          homeClawErrorSnackBar(context, 'Failed: $e'),
        );
      }
    } finally {
      if (mounted) setState(() => _sending.remove(id));
    }
  }

  Widget _buildLocalBody() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              HomeClawInlineErrorCard(message: _error!),
              const SizedBox(height: 16),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    if (_users.isEmpty) {
      return Center(child: Text('No other users', style: Theme.of(context).textTheme.bodyLarge));
    }
    return ListView.builder(
      padding: const EdgeInsets.all(8),
      itemCount: _users.length,
      itemBuilder: (context, index) {
        final u = _users[index];
        final id = (u['id'] as String?)?.trim() ?? '';
        final name = (u['name'] as String?)?.trim() ?? id;
        final sending = _sending.contains(id);
        return Card(
          margin: const EdgeInsets.only(bottom: 8),
          child: ListTile(
            leading: CircleAvatar(
              child: Text((name.isNotEmpty ? name[0] : '?').toUpperCase()),
            ),
            title: Text(name),
            subtitle: Text(id),
            trailing: sending
                ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2))
                : FilledButton.tonal(
                    onPressed: () => _sendRequest(u),
                    child: const Text('Add'),
                  ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final fed = widget.coreService.federationEnabled;
    if (!fed) {
      return Scaffold(
        appBar: AppBar(
          title: const Text('Add friend'),
          actions: [
            IconButton(icon: const Icon(Icons.refresh), onPressed: _loading ? null : _load, tooltip: 'Refresh'),
          ],
        ),
        body: _buildLocalBody(),
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: const Text('Add friend'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _loading ? null : _load, tooltip: 'Refresh'),
        ],
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(text: 'This Core'),
            Tab(text: 'Remote'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildLocalBody(),
          AddRemoteFriendPanel(coreService: widget.coreService),
        ],
      ),
    );
  }
}
