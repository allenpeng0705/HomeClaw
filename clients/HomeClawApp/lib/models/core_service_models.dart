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
