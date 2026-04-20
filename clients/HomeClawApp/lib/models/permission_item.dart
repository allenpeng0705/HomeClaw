import 'package:permission_handler/permission_handler.dart';

/// A single permission entry shown on the permissions screen.
class PermissionItem {
  final String title;
  final String description;
  final Future<PermissionStatus> Function() request;
  /// If set, no request button; show instructions instead (e.g. screen recording).
  final String? instructionsOnly;

  const PermissionItem({
    required this.title,
    required this.description,
    required this.request,
    this.instructionsOnly,
  });
}
