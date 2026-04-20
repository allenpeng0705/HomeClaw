import 'package:flutter_riverpod/flutter_riverpod.dart';

/// State for LoginScreen.
class LoginState {
  final List<Map<String, dynamic>> usersWithUsername;
  final String? selectedUsername;
  final bool loadingUsers;
  final bool loadingLogin;
  final String? error;
  final bool? connectionStatus; // true=connected, false=disconnected, null=not checked
  final bool connectionChecking;

  const LoginState({
    this.usersWithUsername = const [],
    this.selectedUsername,
    this.loadingUsers = true,
    this.loadingLogin = false,
    this.error,
    this.connectionStatus,
    this.connectionChecking = false,
  });

  LoginState copyWith({
    List<Map<String, dynamic>>? usersWithUsername,
    String? selectedUsername,
    bool clearSelectedUsername = false,
    bool? loadingUsers,
    bool? loadingLogin,
    String? error,
    bool clearError = false,
    bool? connectionStatus,
    bool clearConnectionStatus = false,
    bool? connectionChecking,
  }) =>
      LoginState(
        usersWithUsername: usersWithUsername ?? this.usersWithUsername,
        selectedUsername: clearSelectedUsername ? null : (selectedUsername ?? this.selectedUsername),
        loadingUsers: loadingUsers ?? this.loadingUsers,
        loadingLogin: loadingLogin ?? this.loadingLogin,
        error: clearError ? null : (error ?? this.error),
        connectionStatus: clearConnectionStatus ? null : (connectionStatus ?? this.connectionStatus),
        connectionChecking: connectionChecking ?? this.connectionChecking,
      );
}

final loginProvider = StateNotifierProvider<LoginNotifier, LoginState>(
  (ref) => LoginNotifier(),
);

class LoginNotifier extends StateNotifier<LoginState> {
  LoginNotifier() : super(const LoginState());

  void setUsers(List<Map<String, dynamic>> users) {
    state = state.copyWith(usersWithUsername: users, loadingUsers: false, clearError: true);
  }

  void setSelectedUsername(String? u) {
    state = state.copyWith(selectedUsername: u);
  }

  void setLoadingUsers(bool value) {
    state = state.copyWith(loadingUsers: value);
  }

  void setLoadingLogin(bool value) {
    state = state.copyWith(loadingLogin: value);
  }

  void setError(String? e) {
    state = state.copyWith(error: e, loadingUsers: false, loadingLogin: false);
  }

  void setConnectionStatus(bool? value) {
    state = state.copyWith(connectionStatus: value, clearConnectionStatus: value == null, connectionChecking: false);
  }

  void setConnectionChecking(bool value) {
    state = state.copyWith(connectionChecking: value);
  }

  void clearError() {
    state = state.copyWith(clearError: true);
  }
}
