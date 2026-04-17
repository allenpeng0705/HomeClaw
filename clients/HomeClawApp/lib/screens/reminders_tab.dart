import 'package:flutter/material.dart';

import '../core_service.dart';

class RemindersExplorer extends StatefulWidget {
  final CoreService coreService;

  const RemindersExplorer({super.key, required this.coreService});

  @override
  State<RemindersExplorer> createState() => _RemindersExplorerState();
}

class _RemindersExplorerState extends State<RemindersExplorer> {
  bool _loading = true;
  String? _error;
  List<ReminderListItem> _items = const [];
  String? _deletingId;

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
      final items = await widget.coreService.fetchRemindersList();
      if (!mounted) return;
      setState(() {
        _items = items;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString().replaceFirst(RegExp(r'^Exception:\s*'), '');
        _loading = false;
      });
    }
  }

  Future<void> _delete(ReminderListItem item) async {
    setState(() => _deletingId = item.id);
    try {
      await widget.coreService.deleteReminder(id: item.id, type: item.type);
      if (!mounted) return;
      setState(() => _items = _items.where((x) => x.id != item.id).toList());
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Reminder deleted')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Delete failed: $e')));
    } finally {
      if (mounted) setState(() => _deletingId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null && _error!.isNotEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.event_busy, size: 44, color: theme.colorScheme.error),
              const SizedBox(height: 8),
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    if (_items.isEmpty) {
      return Center(
        child: Text(
          'No scheduled reminders yet.',
          style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: _items.length,
        itemBuilder: (context, i) {
          final it = _items[i];
          final deleting = _deletingId == it.id;
          return Card(
            margin: const EdgeInsets.symmetric(vertical: 6),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(it.type == 'cron' ? Icons.repeat : Icons.alarm, size: 18),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          it.message.isEmpty ? '(No message)' : it.message,
                          style: theme.textTheme.titleSmall,
                        ),
                      ),
                      IconButton(
                        tooltip: 'Delete',
                        onPressed: deleting ? null : () => _delete(it),
                        icon: deleting
                            ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                            : const Icon(Icons.delete_outline),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text('Next run: ${it.nextRun.isEmpty ? "-" : it.nextRun}', style: theme.textTheme.bodySmall),
                  if (it.schedule.isNotEmpty) Text('Schedule: ${it.schedule}', style: theme.textTheme.bodySmall),
                  const SizedBox(height: 4),
                  Text('Friend: ${it.friendId}', style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

