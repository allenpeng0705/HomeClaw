import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Installed skills list.
class InstalledSkillsState {
  final List<Map<String, dynamic>> skills;
  final String message;
  final bool loading;

  const InstalledSkillsState({
    this.skills = const [],
    this.message = 'Loading…',
    this.loading = true,
  });

  InstalledSkillsState copyWith({
    List<Map<String, dynamic>>? skills,
    String? message,
    bool? loading,
  }) =>
      InstalledSkillsState(
        skills: skills ?? this.skills,
        message: message ?? this.message,
        loading: loading ?? this.loading,
      );
}

/// Search results state.
class SearchSkillsState {
  final List<Map<String, dynamic>> results;
  final String message;
  final bool searching;

  const SearchSkillsState({
    this.results = const [],
    this.message = '',
    this.searching = false,
  });

  SearchSkillsState copyWith({
    List<Map<String, dynamic>>? results,
    String? message,
    bool? searching,
  }) =>
      SearchSkillsState(
        results: results ?? this.results,
        message: message ?? this.message,
        searching: searching ?? this.searching,
      );
}

/// ClawHub login status state.
class ClawhubLoginState {
  final bool? loggedIn;
  final String statusMessage;
  final bool statusLoading;
  final bool loginInProgress;
  final String? loginUrl;
  final String loginMessage;
  final bool tokenLoginInProgress;

  const ClawhubLoginState({
    this.loggedIn,
    this.statusMessage = '',
    this.statusLoading = true,
    this.loginInProgress = false,
    this.loginUrl,
    this.loginMessage = '',
    this.tokenLoginInProgress = false,
  });

  ClawhubLoginState copyWith({
    bool? loggedIn,
    bool clearLoggedIn = false,
    String? statusMessage,
    bool? statusLoading,
    bool? loginInProgress,
    String? loginUrl,
    bool clearLoginUrl = false,
    String? loginMessage,
    bool? tokenLoginInProgress,
  }) =>
      ClawhubLoginState(
        loggedIn: clearLoggedIn ? null : (loggedIn ?? this.loggedIn),
        statusMessage: statusMessage ?? this.statusMessage,
        statusLoading: statusLoading ?? this.statusLoading,
        loginInProgress: loginInProgress ?? this.loginInProgress,
        loginUrl: clearLoginUrl ? null : (loginUrl ?? this.loginUrl),
        loginMessage: loginMessage ?? this.loginMessage,
        tokenLoginInProgress: tokenLoginInProgress ?? this.tokenLoginInProgress,
      );
}

/// Install state (install/remove in progress).
class InstallState {
  final String? message;
  final bool installing;

  const InstallState({
    this.message,
    this.installing = false,
  });

  InstallState copyWith({
    String? message,
    bool clearMessage = false,
    bool? installing,
  }) =>
      InstallState(
        message: clearMessage ? null : (message ?? this.message),
        installing: installing ?? this.installing,
      );
}

/// Provider for installed skills list.
final installedSkillsProvider =
    StateNotifierProvider<InstalledSkillsNotifier, InstalledSkillsState>(
  (ref) => InstalledSkillsNotifier(),
);

class InstalledSkillsNotifier extends StateNotifier<InstalledSkillsState> {
  InstalledSkillsNotifier() : super(const InstalledSkillsState());

  void setLoading() {
    state = state.copyWith(loading: true, message: 'Loading…');
  }

  void setLoaded(List<Map<String, dynamic>> skills) {
    state = state.copyWith(
      skills: skills,
      loading: false,
      message: '${skills.length} skill(s) loaded.',
    );
  }

  void setError(String msg) {
    state = state.copyWith(skills: [], loading: false, message: msg);
  }
}

/// Provider for skills search.
final searchSkillsProvider =
    StateNotifierProvider<SearchSkillsNotifier, SearchSkillsState>(
  (ref) => SearchSkillsNotifier(),
);

class SearchSkillsNotifier extends StateNotifier<SearchSkillsState> {
  SearchSkillsNotifier() : super(const SearchSkillsState());

  void setSearching(String query) {
    state = state.copyWith(searching: true, message: 'Searching…', results: []);
  }

  void setResults(List<Map<String, dynamic>> results) {
    state = state.copyWith(
      searching: false,
      message: 'Results: ${results.length}',
      results: results,
    );
  }

  void setError(String msg) {
    state = state.copyWith(searching: false, message: msg, results: []);
  }

  void setEmptyQuery(String msg) {
    state = state.copyWith(searching: false, message: msg, results: []);
  }
}

/// Provider for ClawHub login status.
final clawhubLoginProvider =
    StateNotifierProvider<ClawhubLoginNotifier, ClawhubLoginState>(
  (ref) => ClawhubLoginNotifier(),
);

class ClawhubLoginNotifier extends StateNotifier<ClawhubLoginState> {
  ClawhubLoginNotifier() : super(const ClawhubLoginState());

  void setStatusLoading(bool value) {
    state = state.copyWith(statusLoading: value);
  }

  void setStatus({required bool loggedIn, required String message}) {
    state = state.copyWith(
      loggedIn: loggedIn,
      statusMessage: message,
      statusLoading: false,
    );
  }

  void setStatusError(String msg) {
    state = state.copyWith(
      loggedIn: false,
      statusMessage: msg,
      statusLoading: false,
    );
  }

  void setLoginInProgress(bool value) {
    state = state.copyWith(
      loginInProgress: value,
      loginUrl: null,
      loginMessage: '',
    );
  }

  void setLoginResult({String? url, required String message, bool? ok}) {
    state = state.copyWith(
      loginInProgress: false,
      loginUrl: url,
      loginMessage: message,
    );
  }

  void setTokenLoginInProgress(bool value) {
    state = state.copyWith(
      tokenLoginInProgress: value,
      loginMessage: '',
      loginUrl: null,
    );
  }

  void setTokenLoginResult({required String message, bool? ok}) {
    state = state.copyWith(
      tokenLoginInProgress: false,
      loginMessage: message,
    );
  }

  void clearLoginUrl() {
    state = state.copyWith(clearLoginUrl: true);
  }
}

/// Provider for install state.
final installStateProvider =
    StateNotifierProvider<InstallStateNotifier, InstallState>(
  (ref) => InstallStateNotifier(),
);

class InstallStateNotifier extends StateNotifier<InstallState> {
  InstallStateNotifier() : super(const InstallState());

  void setInstalling(String id) {
    state = state.copyWith(installing: true, message: 'Installing $id…');
  }

  void setRemoving(String folder) {
    state = state.copyWith(installing: true, message: 'Removing…');
  }

  void setSuccess(String msg) {
    state = state.copyWith(installing: false, message: msg);
  }

  void setError(String msg) {
    state = state.copyWith(installing: false, message: msg);
  }

  void clear() {
    state = state.copyWith(installing: false, clearMessage: true);
  }
}