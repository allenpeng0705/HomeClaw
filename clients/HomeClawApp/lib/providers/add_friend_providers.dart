import 'package:flutter_riverpod/flutter_riverpod.dart';

/// State for the add-friend screen (local user list).
class AddFriendState {
  final List<Map<String, dynamic>> users;
  final bool loading;
  final String? error;
  final Set<String> sending;

  const AddFriendState({
    this.users = const [],
    this.loading = true,
    this.error,
    this.sending = const {},
  });

  AddFriendState copyWith({
    List<Map<String, dynamic>>? users,
    bool? loading,
    String? error,
    bool clearError = false,
    Set<String>? sending,
  }) =>
      AddFriendState(
        users: users ?? this.users,
        loading: loading ?? this.loading,
        error: clearError ? null : (error ?? this.error),
        sending: sending ?? this.sending,
      );
}

/// Provider for add-friend screen state.
final addFriendProvider = StateNotifierProvider<AddFriendNotifier, AddFriendState>(
  (ref) => AddFriendNotifier(),
);

class AddFriendNotifier extends StateNotifier<AddFriendState> {
  AddFriendNotifier() : super(const AddFriendState());

  void setLoading(bool value) {
    state = state.copyWith(loading: value);
  }

  void setUsers(List<Map<String, dynamic>> users) {
    state = state.copyWith(users: users, loading: false, clearError: true);
  }

  void setError(String e) {
    state = state.copyWith(error: e, loading: false, users: []);
  }

  void setSending(String id, bool value) {
    final newSending = Set<String>.from(state.sending);
    if (value) {
      newSending.add(id);
    } else {
      newSending.remove(id);
    }
    state = state.copyWith(sending: newSending);
  }
}
