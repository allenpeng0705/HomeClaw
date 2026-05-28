import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core_service.dart';
import '../models/core_service_models.dart';

/// Auto-refreshing provider for pending approvals (Phase 5).
final pendingApprovalsProvider = AsyncNotifierProvider<PendingApprovalsNotifier, List<PendingApproval>>(
  PendingApprovalsNotifier.new,
);

class PendingApprovalsNotifier extends AsyncNotifier<List<PendingApproval>> {
  Timer? _timer;

  @override
  Future<List<PendingApproval>> build() async {
    _startAutoRefresh();
    return _fetch();
  }

  void _startAutoRefresh() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 15), (_) => _refresh());
  }

  Future<void> _refresh() async {
    state = const AsyncValue.loading();
    state = await AsyncValue.guard(_fetch);
  }

  Future<List<PendingApproval>> _fetch() async {
    final cs = ref.read(coreServiceProvider);
    try {
      final data = await cs.fetchClawcodeApprovals('');
      final list = (data['approvals'] as List<dynamic>?)
          ?.map((e) => PendingApproval.fromJson(e as Map<String, dynamic>))
          .toList() ?? [];
      return list;
    } catch (_) {
      return [];
    }
  }

  Future<void> approve(String approvalId) async {
    final cs = ref.read(coreServiceProvider);
    await cs.resolveApproval(approvalId, approved: true);
    await _refresh();
  }

  Future<void> deny(String approvalId) async {
    final cs = ref.read(coreServiceProvider);
    await cs.resolveApproval(approvalId, approved: false);
    await _refresh();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

/// Provider for memory health (Phase 1-3). Fetched once, manual refresh.
final memoryHealthProvider = FutureProvider<MemoryHealth?>((ref) async {
  final cs = ref.read(coreServiceProvider);
  try {
    final data = await cs.fetchMemoryHealth();
    return MemoryHealth.fromJson(data);
  } catch (_) {
    return null;
  }
});

/// Provider for task summary (Phase 4).
final taskSummaryProvider = FutureProvider<TaskSummary?>((ref) async {
  final cs = ref.read(coreServiceProvider);
  try {
    final data = await cs.fetchTasks();
    final summary = data['summary'] as Map<String, dynamic>?;
    if (summary != null) return TaskSummary.fromJson(summary);
    return null;
  } catch (_) {
    return null;
  }
});
