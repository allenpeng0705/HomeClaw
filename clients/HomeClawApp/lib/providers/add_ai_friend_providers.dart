import 'dart:io';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// State for AddAIFriendScreen.
class AddAIFriendState {
  final File? avatarFile;
  final bool saving;
  final String? error;

  const AddAIFriendState({
    this.avatarFile,
    this.saving = false,
    this.error,
  });

  AddAIFriendState copyWith({
    File? avatarFile,
    bool clearAvatar = false,
    bool? saving,
    String? error,
    bool clearError = false,
  }) =>
      AddAIFriendState(
        avatarFile: clearAvatar ? null : (avatarFile ?? this.avatarFile),
        saving: saving ?? this.saving,
        error: clearError ? null : (error ?? this.error),
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
}
