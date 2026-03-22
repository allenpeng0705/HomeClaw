import 'package:flutter/material.dart';
import '../core_service.dart';
import '../widgets/homeclaw_snackbars.dart';

/// Friend requests: same-instance and (when federation is on) cross-instance tabs.
class FriendRequestsScreen extends StatefulWidget {
  final CoreService coreService;
  final VoidCallback? onAccept;

  const FriendRequestsScreen({super.key, required this.coreService, this.onAccept});

  @override
  State<FriendRequestsScreen> createState() => _FriendRequestsScreenState();
}

class _FriendRequestsScreenState extends State<FriendRequestsScreen> with SingleTickerProviderStateMixin {
  List<Map<String, dynamic>> _requests = [];
  List<Map<String, dynamic>> _federatedRequests = [];
  bool _loading = true;
  bool _loadingFed = true;
  String? _error;
  String? _errorFed;
  final Set<String> _busy = {};
  TabController? _tabController;

  @override
  void initState() {
    super.initState();
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
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await widget.coreService.getFriendRequests();
      if (mounted) {
        setState(() {
          _requests = list;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
          _requests = [];
        });
      }
    }
  }

  Future<void> _loadFederated() async {
    if (!widget.coreService.federationEnabled) return;
    setState(() {
      _loadingFed = true;
      _errorFed = null;
    });
    try {
      final list = await widget.coreService.getFederatedFriendRequests();
      if (mounted) {
        setState(() {
          _federatedRequests = list;
          _loadingFed = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorFed = e.toString();
          _loadingFed = false;
          _federatedRequests = [];
        });
      }
    }
  }

  Future<void> _accept(String requestId) async {
    setState(() => _busy.add(requestId));
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
      if (mounted) setState(() => _busy.remove(requestId));
    }
  }

  Future<void> _reject(String requestId) async {
    setState(() => _busy.add(requestId));
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
      if (mounted) setState(() => _busy.remove(requestId));
    }
  }

  Future<void> _acceptFed(String requestId) async {
    setState(() => _busy.add('fed_$requestId'));
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
      if (mounted) setState(() => _busy.remove('fed_$requestId'));
    }
  }

  Future<void> _rejectFed(String requestId) async {
    setState(() => _busy.add('fed_$requestId'));
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
      if (mounted) setState(() => _busy.remove('fed_$requestId'));
    }
  }

  Widget _localList() {
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
    if (_requests.isEmpty) {
      return Center(child: Text('No pending requests', style: Theme.of(context).textTheme.bodyLarge));
    }
    return ListView.builder(
      padding: const EdgeInsets.all(8),
      itemCount: _requests.length,
      itemBuilder: (context, index) {
        final r = _requests[index];
        final requestId = (r['id'] as String?)?.trim() ?? '';
        final fromName = (r['from_user_name'] as String?)?.trim() ?? (r['from_user_id'] as String?) ?? 'Someone';
        final message = (r['message'] as String?)?.trim();
        final busy = _busy.contains(requestId);
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

  Widget _federatedList() {
    if (_loadingFed) return const Center(child: CircularProgressIndicator());
    if (_errorFed != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              HomeClawInlineErrorCard(message: _errorFed!),
              const SizedBox(height: 16),
              FilledButton(onPressed: _loadFederated, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    if (_federatedRequests.isEmpty) {
      return Center(child: Text('No remote requests', style: Theme.of(context).textTheme.bodyLarge));
    }
    return ListView.builder(
      padding: const EdgeInsets.all(8),
      itemCount: _federatedRequests.length,
      itemBuilder: (context, index) {
        final r = _federatedRequests[index];
        final requestId = (r['id'] as String?)?.trim() ?? '';
        final fromFid = (r['from_fid'] as String?)?.trim() ?? '';
        final message = (r['message'] as String?)?.trim();
        final busy = _busy.contains('fed_$requestId');
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
    final fed = widget.coreService.federationEnabled;
    if (!fed) {
      return Scaffold(
        appBar: AppBar(
          title: const Text('Friend requests'),
          actions: [
            IconButton(icon: const Icon(Icons.refresh), onPressed: _loading ? null : _load, tooltip: 'Refresh'),
          ],
        ),
        body: _localList(),
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: const Text('Friend requests'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading && _loadingFed
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
          _localList(),
          _federatedList(),
        ],
      ),
    );
  }
}
