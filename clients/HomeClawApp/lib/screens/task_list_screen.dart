import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core_service.dart';
import '../models/core_service_models.dart';

/// Task list screen — Phase 4: Subagent Registry & Task Lifecycle.
class TaskListScreen extends ConsumerStatefulWidget {
  final CoreService coreService;

  const TaskListScreen({super.key, required this.coreService});

  @override
  ConsumerState<TaskListScreen> createState() => _TaskListScreenState();
}

class _TaskListScreenState extends ConsumerState<TaskListScreen> {
  List<TaskItem>? _tasks;
  TaskSummary? _summary;
  bool _loading = true;
  String? _error;
  String _filterStatus = '';
  String _filterRuntime = '';
  Timer? _refreshTimer;

  @override
  void initState() {
    super.initState();
    _fetch();
    _refreshTimer = Timer.periodic(const Duration(seconds: 30), (_) => _fetch());
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _fetch() async {
    try {
      final data = await widget.coreService.fetchTasks(
        status: _filterStatus.isNotEmpty ? _filterStatus : null,
        runtime: _filterRuntime.isNotEmpty ? _filterRuntime : null,
      );
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = null;
        if (data.containsKey('tasks')) {
          _tasks = (data['tasks'] as List<dynamic>?)
              ?.map((e) => TaskItem.fromJson(e as Map<String, dynamic>))
              .toList();
          _summary = null;
        } else if (data.containsKey('summary')) {
          _summary = TaskSummary.fromJson(data['summary'] as Map<String, dynamic>);
          _tasks = null;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { _loading = false; _error = e.toString(); });
    }
  }

  Color _statusColor(String status) => switch (status) {
    'running' || 'queued' => Colors.blue,
    'succeeded' => Colors.green,
    'failed' || 'timed_out' || 'lost' => Colors.red,
    'cancelled' => Colors.orange,
    _ => Colors.grey,
  };

  IconData _statusIcon(String status) => switch (status) {
    'running' => Icons.play_circle,
    'queued' => Icons.schedule,
    'succeeded' => Icons.check_circle,
    'failed' => Icons.error,
    'timed_out' => Icons.timer_off,
    'cancelled' => Icons.cancel,
    'lost' => Icons.help_outline,
    _ => Icons.circle,
  };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tasks'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: () { setState(() => _loading = true); _fetch(); }),
        ],
      ),
      body: Column(
        children: [
          // ── Filters ────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    value: _filterStatus.isEmpty ? null : _filterStatus,
                    decoration: const InputDecoration(
                      labelText: 'Status', isDense: true,
                      border: OutlineInputBorder(),
                    ),
                    items: const [
                      DropdownMenuItem(value: '', child: Text('All')),
                      DropdownMenuItem(value: 'queued', child: Text('Queued')),
                      DropdownMenuItem(value: 'running', child: Text('Running')),
                      DropdownMenuItem(value: 'succeeded', child: Text('Succeeded')),
                      DropdownMenuItem(value: 'failed', child: Text('Failed')),
                    ],
                    onChanged: (v) { setState(() { _filterStatus = v ?? ''; _loading = true; }); _fetch(); },
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    value: _filterRuntime.isEmpty ? null : _filterRuntime,
                    decoration: const InputDecoration(
                      labelText: 'Runtime', isDense: true,
                      border: OutlineInputBorder(),
                    ),
                    items: const [
                      DropdownMenuItem(value: '', child: Text('All')),
                      DropdownMenuItem(value: 'subagent', child: Text('Subagent')),
                      DropdownMenuItem(value: 'skill', child: Text('Skill')),
                      DropdownMenuItem(value: 'cron', child: Text('Cron')),
                    ],
                    onChanged: (v) { setState(() { _filterRuntime = v ?? ''; _loading = true; }); _fetch(); },
                  ),
                ),
              ],
            ),
          ),
          // ── Content ────────────────────────────────────────────
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? Center(child: Text('Error: $_error', style: const TextStyle(color: Colors.red)))
                    : _buildContent(),
          ),
        ],
      ),
    );
  }

  Widget _buildContent() {
    // Summary mode (no filters)
    if (_summary != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _StatCard(label: 'Total', value: '${_summary!.total}'),
            _StatCard(label: 'Active', value: '${_summary!.active}', color: Colors.blue),
            _StatCard(label: 'Failures', value: '${_summary!.failures}', color: Colors.red),
            const SizedBox(height: 16),
            const Text('Apply a filter to see task list.', style: TextStyle(color: Colors.grey)),
          ],
        ),
      );
    }

    // Task list mode
    if (_tasks == null || _tasks!.isEmpty) {
      return const Center(child: Text('No tasks found.'));
    }

    return ListView.builder(
      itemCount: _tasks!.length,
      itemBuilder: (ctx, i) {
        final t = _tasks![i];
        return Card(
          margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          child: ListTile(
            leading: Icon(_statusIcon(t.status), color: _statusColor(t.status)),
            title: Text(t.taskKind ?? t.runtime, maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text(
              '${t.status}${t.resultSummary != null ? ' — ${t.resultSummary}' : ''}',
              maxLines: 2, overflow: TextOverflow.ellipsis,
            ),
            trailing: Text(
              t.taskId.length > 8 ? '#${t.taskId.substring(0, 8)}' : '#${t.taskId}',
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ),
        );
      },
    );
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;
  const _StatCard({required this.label, required this.value, this.color});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('$label: ', style: const TextStyle(fontSize: 16)),
          Text(value, style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: color)),
        ],
      ),
    );
  }
}
