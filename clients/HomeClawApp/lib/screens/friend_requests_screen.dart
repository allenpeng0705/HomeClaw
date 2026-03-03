import 'package:flutter/material.dart';
import '../core_service.dart';

/// Friend requests: list pending requests, Accept / Reject.
class FriendRequestsScreen extends StatefulWidget {
  final CoreService coreService;
  final VoidCallback? onAccept;

  const FriendRequestsScreen({super.key, required this.coreService, this.onAccept});

  @override
  State<FriendRequestsScreen> createState() => _FriendRequestsScreenState();
}

class _FriendRequestsScreenState extends State<FriendRequestsScreen> {
  List<Map<String, dynamic>> _requests = [];
  bool _loading = true;
  String? _error;
  final Set<String> _busy = {};

  @override
  void initState() {
    super.initState();
    _load();
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
          SnackBar(content: Text('Accept failed: $e'), backgroundColor: Theme.of(context).colorScheme.errorContainer),
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
          SnackBar(content: Text('Reject failed: $e'), backgroundColor: Theme.of(context).colorScheme.errorContainer),
        );
      }
    } finally {
      if (mounted) setState(() => _busy.remove(requestId));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Friend requests'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _loading ? null : _load, tooltip: 'Refresh'),
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
                        Text(_error!, style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: Theme.of(context).colorScheme.error)),
                        const SizedBox(height: 16),
                        FilledButton(onPressed: _load, child: const Text('Retry')),
                      ],
                    ),
                  ),
                )
              : _requests.isEmpty
                  ? Center(child: Text('No pending requests', style: Theme.of(context).textTheme.bodyLarge))
                  : ListView.builder(
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
                    ),
    );
  }
}
