import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core_service.dart';
import '../providers/reminders_providers.dart';

class RemindersExplorer extends ConsumerStatefulWidget {
  final CoreService coreService;

  const RemindersExplorer({super.key, required this.coreService});

  @override
  ConsumerState<RemindersExplorer> createState() => _RemindersExplorerState();
}

class _RemindersExplorerState extends ConsumerState<RemindersExplorer> {
  late final RemindersNotifier _notifier;

  @override
  void initState() {
    super.initState();
    _notifier = ref.read(remindersProvider.notifier);
    _load();
  }

  Future<void> _load() async {
    _notifier.setLoading(true);
    try {
      final items = await widget.coreService.fetchRemindersList();
      if (!mounted) return;
      _notifier.setItems(items);
    } catch (e) {
      if (!mounted) return;
      _notifier.setError(e.toString().replaceFirst(RegExp(r'^Exception:\s*'), ''));
    }
  }

  Future<void> _delete(ReminderListItem item) async {
    _notifier.setDeletingId(item.id);
    try {
      await widget.coreService.deleteReminder(id: item.id, type: item.type);
      if (!mounted) return;
      _notifier.removeItem(item.id);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Reminder deleted')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Delete failed: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(remindersProvider);
    final theme = Theme.of(context);
    if (state.loading) return const Center(child: CircularProgressIndicator());
    if (state.error != null && state.error!.isNotEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.event_busy, size: 44, color: theme.colorScheme.error),
              const SizedBox(height: 8),
              Text(state.error!, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    if (state.items.isEmpty) {
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
        itemCount: state.items.length,
        itemBuilder: (context, i) {
          final it = state.items[i];
          final deleting = state.deletingId == it.id;
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

