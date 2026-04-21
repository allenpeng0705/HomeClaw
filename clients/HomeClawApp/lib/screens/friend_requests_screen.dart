import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core_service.dart';
import '../providers/friend_list_providers.dart';
import '../widgets/homeclaw_snackbars.dart';

/// Friend requests: same-instance and (when federation is on) cross-instance tabs.
class FriendRequestsScreen extends ConsumerStatefulWidget {
  final CoreService coreService;
  final VoidCallback? onAccept;

  const FriendRequestsScreen({super.key, required this.coreService, this.onAccept});

  @override
  ConsumerState<FriendRequestsScreen> createState() => _FriendRequestsScreenState();
}

class _FriendRequestsScreenState extends ConsumerState<FriendRequestsScreen> with SingleTickerProviderStateMixin {
  late final FriendRequestsNotifier _notifier;
  TabController? _tabController;

  @override
  void initState() {
    super.initState();
    _notifier = ref.read(friendRequestsProvider.notifier);
    if (widget.coreService.federationEnabled) {
      _tabController = TabController(length: 2, vsync: this);
    }
    _load();
    if (widget.coreService.federationEnabled) _loadFederated();
  }

  @override
  void dispose() {
    _tabController?.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    _notifier.setLoading(true);
    try {
      final list = await widget.coreService.getFriendRequests();
      if (mounted) _notifier.setRequests(list);
    } catch (e) {
      if (mounted) _notifier.setError(e.toString());
    }
  }

  Future<void> _loadFederated() async {
    if (!widget.coreService.federationEnabled) return;
    _notifier.setLoadingFed(true);
    try {
      final list = await widget.coreService.getFederatedFriendRequests();
      if (mounted) _notifier.setFederatedRequests(list);
    } catch (e) {
      if (mounted) _notifier.setErrorFed(e.toString());
    }
  }

  Future<void> _accept(String requestId) async {
    _notifier.setBusy(requestId, true);
    try {
      await widget.coreService.acceptFriendRequest(requestId);
      if (!mounted) return;
      widget.onAccept?.call();
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Friend added')));
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          homeClawErrorSnackBar(context, 'Accept failed: $e'),
        );
      }
    } finally {
      if (mounted) _notifier.setBusy(requestId, false);
    }
  }

  Future<void> _reject(String requestId) async {
    _notifier.setBusy(requestId, true);
    try {
      await widget.coreService.rejectFriendRequest(requestId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Request declined')));
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          homeClawErrorSnackBar(context, 'Reject failed: $e'),
        );
      }
    } finally {
      if (mounted) _notifier.setBusy(requestId, false);
    }
  }

  Future<void> _acceptFed(String requestId) async {
    _notifier.setBusyFed(requestId, true);
    try {
      await widget.coreService.acceptFederatedFriendRequest(requestId);
      if (!mounted) return;
      widget.onAccept?.call();
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Remote friend request accepted')));
      _loadFederated();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          homeClawErrorSnackBar(context, 'Accept failed: $e'),
        );
      }
    } finally {
      if (mounted) _notifier.setBusyFed(requestId, false);
    }
  }

  Future<void> _rejectFed(String requestId) async {
    _notifier.setBusyFed(requestId, true);
    try {
      await widget.coreService.rejectFederatedFriendRequest(requestId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Declined')));
      _loadFederated();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          homeClawErrorSnackBar(context, 'Reject failed: $e'),
        );
      }
    } finally {
      if (mounted) _notifier.setBusyFed(requestId, false);
    }
  }

  Widget _localList(FriendRequestsState state) {
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
    if (state.requests.isEmpty) {
      return Center(child: Text('No pending requests', style: Theme.of(context).textTheme.bodyLarge));
    }
    return ListView.builder(
      padding: const EdgeInsets.all(8),
      itemCount: state.requests.length,
      itemBuilder: (context, index) {
        final r = state.requests[index];
        final requestId = (r['id'] as String?)?.trim() ?? '';
        final fromName = (r['from_user_name'] as String?)?.trim() ?? (r['from_user_id'] as String?) ?? 'Someone';
        final message = (r['message'] as String?)?.trim();
        final busy = state.busy.contains(requestId);
        return Card(
          margin: const EdgeInsets.only(bottom: 8),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('$fromName wants to add you as a friend', style: Theme.of(context).textTheme.titleSmall),
                if (message != null && message.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(message, style: Theme.of(context).textTheme.bodyMedium),
                  ),
                const SizedBox(height: 10),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      onPressed: busy ? null : () => _reject(requestId),
                      child: const Text('Decline'),
                    ),
                    const SizedBox(width: 8),
                    FilledButton(
                      onPressed: busy ? null : () => _accept(requestId),
                      child: busy ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Accept'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _federatedList(FriendRequestsState state) {
    if (state.loadingFed) return const Center(child: CircularProgressIndicator());
    if (state.errorFed != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              HomeClawInlineErrorCard(message: state.errorFed!),
              const SizedBox(height: 16),
              FilledButton(onPressed: _loadFederated, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    if (state.federatedRequests.isEmpty) {
      return Center(child: Text('No remote requests', style: Theme.of(context).textTheme.bodyLarge));
    }
    return ListView.builder(
      padding: const EdgeInsets.all(8),
      itemCount: state.federatedRequests.length,
      itemBuilder: (context, index) {
        final r = state.federatedRequests[index];
        final requestId = (r['id'] as String?)?.trim() ?? '';
        final fromFid = (r['from_fid'] as String?)?.trim() ?? '';
        final message = (r['message'] as String?)?.trim();
        final busy = state.busy.contains('fed_$requestId');
        return Card(
          margin: const EdgeInsets.only(bottom: 8),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    Icon(Icons.cloud_outlined, size: 18, color: Theme.of(context).colorScheme.primary),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        fromFid.isNotEmpty ? '$fromFid (remote)' : 'Remote request',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                    ),
                  ],
                ),
                if (message != null && message.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(message, style: Theme.of(context).textTheme.bodyMedium),
                  ),
                const SizedBox(height: 10),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      onPressed: busy ? null : () => _rejectFed(requestId),
                      child: const Text('Decline'),
                    ),
                    const SizedBox(width: 8),
                    FilledButton(
                      onPressed: busy ? null : () => _acceptFed(requestId),
                      child: busy ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Accept'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(friendRequestsProvider);
    final fed = widget.coreService.federationEnabled;
    if (!fed) {
      return Scaffold(
        appBar: AppBar(
          title: const Text('Friend requests'),
          actions: [
            IconButton(icon: const Icon(Icons.refresh), onPressed: state.loading ? null : _load, tooltip: 'Refresh'),
          ],
        ),
        body: _localList(state),
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: const Text('Friend requests'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: state.loading && state.loadingFed
                ? null
                : () {
                    _load();
                    _loadFederated();
                  },
            tooltip: 'Refresh',
          ),
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
          _localList(state),
          _federatedList(state),
        ],
      ),
    );
  }
}
