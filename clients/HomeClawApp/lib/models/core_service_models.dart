/// One row from [CoreService.fetchSandboxList] / GET /api/sandbox/list.
class SandboxListEntry {
  final String name;
  final String type;
  /// Path relative to homeclaw root (same as [path] query for /api/sandbox/file).
  final String path;

  const SandboxListEntry({required this.name, required this.type, required this.path});
}

/// Result of GET /api/sandbox/list.
class SandboxListResult {
  final String scope;
  final String path;
  final List<SandboxListEntry> entries;

  const SandboxListResult({required this.scope, required this.path, required this.entries});
}

/// One row from [CoreService.fetchBridgeProjectList] / GET /api/cursor-bridge/project-list (Dev Bridge active project).
class BridgeProjectListEntry {
  final String name;
  final String type;
  final String relPath;
  final String absPath;
  final int? size;

  const BridgeProjectListEntry({
    required this.name,
    required this.type,
    required this.relPath,
    required this.absPath,
    this.size,
  });
}

/// Result of GET /api/cursor-bridge/project-list.
class BridgeProjectListResult {
  final String? error;
  final String root;
  final String path;
  final List<BridgeProjectListEntry> entries;

  const BridgeProjectListResult({
    this.error,
    required this.root,
    required this.path,
    required this.entries,
  });
}

/// UTF-8 preview from GET /api/cursor-bridge/project-file.
class BridgeProjectFilePreview {
  final String? error;
  final String content;
  final bool truncated;
  final String absPath;

  const BridgeProjectFilePreview({
    this.error,
    required this.content,
    required this.truncated,
    required this.absPath,
  });
}

class BridgeRootListResult {
  final String? error;
  final String root;
  final String path;
  final List<BridgeProjectListEntry> entries;

  const BridgeRootListResult({
    this.error,
    required this.root,
    required this.path,
    required this.entries,
  });
}

class ReminderListItem {
  final String id;
  final String type; // cron | oneshot
  final String message;
  final String schedule;
  final String nextRun;
  final bool enabled;
  final String friendId;

  const ReminderListItem({
    required this.id,
    required this.type,
    required this.message,
    required this.schedule,
    required this.nextRun,
    required this.enabled,
    required this.friendId,
  });
}

// ── Phase 4-6 models ──────────────────────────────────────────────

/// Task record from GET /api/tasks (Phase 4).
class TaskItem {
  final String taskId;
  final String status;
  final String runtime;
  final String? taskKind;
  final double? createdAt;
  final double? completedAt;
  final String? resultSummary;

  const TaskItem({
    required this.taskId,
    required this.status,
    required this.runtime,
    this.taskKind,
    this.createdAt,
    this.completedAt,
    this.resultSummary,
  });

  factory TaskItem.fromJson(Map<String, dynamic> json) => TaskItem(
    taskId: json['task_id']?.toString() ?? '',
    status: json['status']?.toString() ?? 'unknown',
    runtime: json['runtime']?.toString() ?? '',
    taskKind: json['task_kind']?.toString(),
    createdAt: (json['created_at'] as num?)?.toDouble(),
    completedAt: (json['completed_at'] as num?)?.toDouble(),
    resultSummary: json['result_summary']?.toString(),
  );
}

/// Task summary from GET /api/tasks (no filters).
class TaskSummary {
  final int total;
  final int active;
  final int failures;

  const TaskSummary({required this.total, required this.active, required this.failures});

  factory TaskSummary.fromJson(Map<String, dynamic> json) => TaskSummary(
    total: (json['total'] as num?)?.toInt() ?? 0,
    active: (json['active'] as num?)?.toInt() ?? 0,
    failures: (json['failures'] as num?)?.toInt() ?? 0,
  );
}

/// Memory health from GET /memory/health (Phase 1-3).
class MemoryHealth {
  final bool ok;
  final String backend;
  final int? indexSize;
  final int errorCount;
  final Map<String, dynamic>? doctor;

  const MemoryHealth({
    required this.ok,
    required this.backend,
    this.indexSize,
    this.errorCount = 0,
    this.doctor,
  });

  factory MemoryHealth.fromJson(Map<String, dynamic> json) => MemoryHealth(
    ok: json['ok'] == true,
    backend: json['backend']?.toString() ?? 'unknown',
    indexSize: (json['index_size'] as num?)?.toInt(),
    errorCount: (json['error_count'] as num?)?.toInt() ?? 0,
    doctor: json['doctor'] as Map<String, dynamic>?,
  );
}

/// Pending approval from GET /api/clawcode/approvals (Phase 5).
class PendingApproval {
  final String approvalId;
  final String toolName;
  final String state;
  final String ownerUserId;
  final double? createdAt;

  const PendingApproval({
    required this.approvalId,
    required this.toolName,
    required this.state,
    required this.ownerUserId,
    this.createdAt,
  });

  factory PendingApproval.fromJson(Map<String, dynamic> json) => PendingApproval(
    approvalId: json['approval_id']?.toString() ?? '',
    toolName: json['tool_name']?.toString() ?? '',
    state: json['state']?.toString() ?? 'pending',
    ownerUserId: json['owner_user_id']?.toString() ?? '',
    createdAt: (json['created_at'] as num?)?.toDouble(),
  );
}
