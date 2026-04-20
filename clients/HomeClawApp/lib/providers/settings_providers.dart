import 'dart:typed_data';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Settings screen state: avatar, node connection, exec allowlist.
class SettingsState {
  final Uint8List? myAvatarBytes;
  final bool avatarLoading;
  final bool avatarUploading;
  final bool nodeConnecting;
  final List<String> execAllowlist;

  const SettingsState({
    this.myAvatarBytes,
    this.avatarLoading = true,
    this.avatarUploading = false,
    this.nodeConnecting = false,
    this.execAllowlist = const [],
  });

  SettingsState copyWith({
    Uint8List? myAvatarBytes,
    bool clearAvatar = false,
    bool? avatarLoading,
    bool? avatarUploading,
    bool? nodeConnecting,
    List<String>? execAllowlist,
  }) =>
      SettingsState(
        myAvatarBytes: clearAvatar ? null : (myAvatarBytes ?? this.myAvatarBytes),
        avatarLoading: avatarLoading ?? this.avatarLoading,
        avatarUploading: avatarUploading ?? this.avatarUploading,
        nodeConnecting: nodeConnecting ?? this.nodeConnecting,
        execAllowlist: execAllowlist ?? this.execAllowlist,
      );
}

/// Provider for settings screen state.
final settingsProvider = StateNotifierProvider<SettingsNotifier, SettingsState>(
  (ref) => SettingsNotifier(),
);

class SettingsNotifier extends StateNotifier<SettingsState> {
  SettingsNotifier() : super(const SettingsState());

  void setAvatarLoading(bool value) {
    state = state.copyWith(avatarLoading: value);
  }

  void setMyAvatar(Uint8List? bytes) {
    if (bytes == null || bytes.isEmpty) {
      state = state.copyWith(clearAvatar: true, avatarLoading: false);
    } else {
      state = state.copyWith(myAvatarBytes: bytes, avatarLoading: false);
    }
  }

  void setAvatarUploading(bool value) {
    state = state.copyWith(avatarUploading: value);
  }

  void setNodeConnecting(bool value) {
    state = state.copyWith(nodeConnecting: value);
  }

  void setExecAllowlist(List<String> list) {
    state = state.copyWith(execAllowlist: list);
  }
}