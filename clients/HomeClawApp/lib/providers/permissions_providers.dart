import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:homeclaw_voice/homeclaw_voice.dart';

class PermissionsState {
  final Map<String, PermissionStatus> status;
  final Map<String, bool> requesting;
  final bool continuing;

  const PermissionsState({
    this.status = const {},
    this.requesting = const {},
    this.continuing = false,
  });

  PermissionsState copyWith({
    Map<String, PermissionStatus>? status,
    Map<String, bool>? requesting,
    bool? continuing,
  }) =>
      PermissionsState(
        status: status ?? this.status,
        requesting: requesting ?? this.requesting,
        continuing: continuing ?? this.continuing,
      );
}

final permissionsProvider =
    StateNotifierProvider.autoDispose<PermissionsNotifier, PermissionsState>(
  (ref) => PermissionsNotifier(),
);

class PermissionsNotifier extends StateNotifier<PermissionsState> {
  PermissionsNotifier() : super(const PermissionsState());

  void setRequesting(String key, bool value) {
    state = state.copyWith(requesting: {...state.requesting, key: value});
  }

  void setStatus(String key, PermissionStatus status) {
    state = state.copyWith(status: {...state.status, key: status});
  }

  void setContinuing(bool value) {
    state = state.copyWith(continuing: value);
  }
}

/// Singleton voice instance for availability check.
final _voice = HomeclawVoice();

/// Check if microphone/speech permission is available.
Future<PermissionStatus> checkMicrophonePermission() async {
  final ok = await _voice.isAvailable;
  return ok ? PermissionStatus.granted : PermissionStatus.denied;
}