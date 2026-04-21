import 'package:flutter_riverpod/flutter_riverpod.dart';

/// State for the ConfigCoreScreen.
class ConfigCoreState {
  final Map<String, dynamic> core;
  final List<Map<String, dynamic>> users;
  final bool loading;
  final String? error;

  const ConfigCoreState({
    this.core = const {},
    this.users = const [],
    this.loading = true,
    this.error,
  });

  ConfigCoreState copyWith({
    Map<String, dynamic>? core,
    List<Map<String, dynamic>>? users,
    bool? loading,
    String? error,
    bool clearError = false,
  }) =>
      ConfigCoreState(
        core: core ?? this.core,
        users: users ?? this.users,
        loading: loading ?? this.loading,
        error: clearError ? null : (error ?? this.error),
      );
}

final configCoreProvider = StateNotifierProvider<ConfigCoreNotifier, ConfigCoreState>(
  (ref) => ConfigCoreNotifier(),
);

class ConfigCoreNotifier extends StateNotifier<ConfigCoreState> {
  ConfigCoreNotifier() : super(const ConfigCoreState());

  void setLoading(bool value) {
    state = state.copyWith(loading: value);
  }

  void setLoaded(Map<String, dynamic> core, List<Map<String, dynamic>> users) {
    state = state.copyWith(core: core, users: users, loading: false, clearError: true);
  }

  void setError(String e) {
    state = state.copyWith(error: e, loading: false);
  }

  void setUsers(List<Map<String, dynamic>> users) {
    state = state.copyWith(users: users);
  }
}
