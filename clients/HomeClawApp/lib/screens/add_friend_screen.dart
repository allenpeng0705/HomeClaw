import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core_service.dart';
import '../providers/add_friend_providers.dart';
import '../widgets/homeclaw_snackbars.dart';
import 'add_remote_friend_screen.dart';

/// Add Friend: list users on this Core, or (when federation is on) send a remote request.
class AddFriendScreen extends ConsumerStatefulWidget {
  final CoreService coreService;

  const AddFriendScreen({super.key, required this.coreService});

  @override
  ConsumerState<AddFriendScreen> createState() => _AddFriendScreenState();
}

class _AddFriendScreenState extends ConsumerState<AddFriendScreen> with SingleTickerProviderStateMixin {
  late final AddFriendNotifier _notifier;
  TabController? _tabController;

  @override
  void initState() {
    super.initState();
    _notifier = ref.read(addFriendProvider.notifier);
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
    _notifier.setLoading(true);
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
      if (mounted) _notifier.setUsers(filtered);
    } catch (e) {
      if (mounted) _notifier.setError(e.toString());
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
    _notifier.setSending(id, true);
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
      if (mounted) _notifier.setSending(id, false);
    }
  }

  Widget _buildLocalBody(AddFriendState state) {
    if (state.loading) return const Center(child: CircularProgressIndicator());
    if (state.error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              HomeClawInlineErrorCard(message: state.error!),
              const SizedBox(height: 16),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    if (state.users.isEmpty) {
      return Center(child: Text('No other users', style: Theme.of(context).textTheme.bodyLarge));
    }
    return ListView.builder(
      padding: const EdgeInsets.all(8),
      itemCount: state.users.length,
      itemBuilder: (context, index) {
        final u = state.users[index];
        final id = (u['id'] as String?)?.trim() ?? '';
        final name = (u['name'] as String?)?.trim() ?? id;
        final sending = state.sending.contains(id);
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
    final state = ref.watch(addFriendProvider);
    final fed = widget.coreService.federationEnabled;
    if (!fed) {
      return Scaffold(
        appBar: AppBar(
          title: const Text('Add friend'),
          actions: [
            IconButton(icon: const Icon(Icons.refresh), onPressed: state.loading ? null : _load, tooltip: 'Refresh'),
          ],
        ),
        body: _buildLocalBody(state),
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: const Text('Add friend'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: state.loading ? null : _load, tooltip: 'Refresh'),
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
          _buildLocalBody(state),
          AddRemoteFriendPanel(coreService: widget.coreService),
        ],
      ),
    );
  }
}
