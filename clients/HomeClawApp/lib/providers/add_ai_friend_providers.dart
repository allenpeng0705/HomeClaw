import 'dart:io';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// State for AddAIFriendScreen.
class AddAIFriendState {
  final File? avatarFile;
  final bool saving;
  final String? error;
  final String? preset; // 'cursor', 'claude', or null for custom AI

  const AddAIFriendState({
    this.avatarFile,
    this.saving = false,
    this.error,
    this.preset,
  });

  AddAIFriendState copyWith({
    File? avatarFile,
    bool clearAvatar = false,
    bool? saving,
    String? error,
    bool clearError = false,
    String? preset,
    bool clearPreset = false,
  }) =>
      AddAIFriendState(
        avatarFile: clearAvatar ? null : (avatarFile ?? this.avatarFile),
        saving: saving ?? this.saving,
        error: clearError ? null : (error ?? this.error),
        preset: clearPreset ? null : (preset ?? this.preset),
      );
}

final addAIFriendProvider = StateNotifierProvider<AddAIFriendNotifier, AddAIFriendState>(
  (ref) => AddAIFriendNotifier(),
);

class AddAIFriendNotifier extends StateNotifier<AddAIFriendState> {
  AddAIFriendNotifier() : super(const AddAIFriendState());

  void setAvatar(File? file) {
    if (file == null) {
      state = state.copyWith(clearAvatar: true);
    } else {
      state = state.copyWith(avatarFile: file);
    }
  }

  void setSaving(bool value) {
    state = state.copyWith(saving: value);
  }

  void setError(String? e) {
    state = state.copyWith(error: e, saving: false);
  }

  void clearError() {
    state = state.copyWith(clearError: true);
  }

  void setSubmitting(bool value, {String? error}) {
    if (error != null) {
      state = state.copyWith(saving: value, error: error);
    } else {
      state = state.copyWith(saving: value, clearError: true);
    }
  }

  void setPreset(String? p) {
    final v = (p != null && p.trim().toLowerCase() == 'trae') ? null : p;
    state = state.copyWith(preset: v, clearPreset: v == null);
  }
}
