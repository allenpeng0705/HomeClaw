import 'package:flutter_riverpod/flutter_riverpod.dart';

enum CcRunState { idle, running, approvalPending, error }

class ClawcodeState {
  final bool loading;
  final String? error;
  final List<Map<String, dynamic>> sessions;
  final List<Map<String, dynamic>> approvals;
  final String? activeSessionId;
  final bool sending;
  final String progressLine;
  final String lastReply;
  final CcRunState ccRunState;

  const ClawcodeState({
    this.loading = true,
    this.error,
    this.sessions = const [],
    this.approvals = const [],
    this.activeSessionId,
    this.sending = false,
    this.progressLine = '',
    this.lastReply = '',
    this.ccRunState = CcRunState.idle,
  });

  ClawcodeState copyWith({
    bool? loading,
    String? error,
    bool clearError = false,
    List<Map<String, dynamic>>? sessions,
    List<Map<String, dynamic>>? approvals,
    String? activeSessionId,
    bool clearActiveSessionId = false,
    bool? sending,
    String? progressLine,
    String? lastReply,
    CcRunState? ccRunState,
  }) =>
      ClawcodeState(
        loading: loading ?? this.loading,
        error: clearError ? null : (error ?? this.error),
        sessions: sessions ?? this.sessions,
        approvals: approvals ?? this.approvals,
        activeSessionId: clearActiveSessionId ? null : (activeSessionId ?? this.activeSessionId),
        sending: sending ?? this.sending,
        progressLine: progressLine ?? this.progressLine,
        lastReply: lastReply ?? this.lastReply,
        ccRunState: ccRunState ?? this.ccRunState,
      );
}

final clawcodeProvider = StateNotifierProvider.autoDispose
    <ClawcodeNotifier, ClawcodeState>((ref) => ClawcodeNotifier());

class ClawcodeNotifier extends StateNotifier<ClawcodeState> {
  ClawcodeNotifier() : super(const ClawcodeState());

  void setLoading(bool v) {
    state = state.copyWith(loading: v, clearError: true);
  }

  void setError(String e) {
    state = state.copyWith(error: e, loading: false, clearActiveSessionId: true);
  }

  void setSessionsAndApprovals(
    List<Map<String, dynamic>> sessions,
    List<Map<String, dynamic>> approvals,
  ) {
    state = state.copyWith(
      sessions: sessions,
      approvals: approvals,
      loading: false,
      progressLine: '',
    );
  }

  void setActiveSessionId(String? id) {
    state = state.copyWith(activeSessionId: id);
  }

  void clearActiveSessionId() {
    state = state.copyWith(clearActiveSessionId: true);
  }

  void setSending(bool v) {
    state = state.copyWith(sending: v);
  }

  void setProgressLine(String line) {
    state = state.copyWith(progressLine: line);
  }

  void setLastReply(String text) {
    state = state.copyWith(lastReply: text);
  }

  void setCcRunState(CcRunState s) {
    state = state.copyWith(ccRunState: s);
  }

  void setApprovals(List<Map<String, dynamic>> a) {
    state = state.copyWith(approvals: a);
  }
}

// File browser sub-state (used within ClawcodeScreen but isolated)
class ClawcodeFilesState {
  final String? sessionId;
  final String rel;
  final List<Map<String, dynamic>> entries;
  final bool loading;

  const ClawcodeFilesState({
    this.sessionId,
    this.rel = '',
    this.entries = const [],
    this.loading = false,
  });

  ClawcodeFilesState copyWith({
    String? sessionId,
    bool clearSessionId = false,
    String? rel,
    List<Map<String, dynamic>>? entries,
    bool? loading,
  }) =>
      ClawcodeFilesState(
        sessionId: clearSessionId ? null : (sessionId ?? this.sessionId),
        rel: rel ?? this.rel,
        entries: entries ?? this.entries,
        loading: loading ?? this.loading,
      );
}

final clawcodeFilesProvider = StateNotifierProvider.autoDispose
    <ClawcodeFilesNotifier, ClawcodeFilesState>((ref) => ClawcodeFilesNotifier());

class ClawcodeFilesNotifier extends StateNotifier<ClawcodeFilesState> {
  ClawcodeFilesNotifier() : super(const ClawcodeFilesState());

  void setLoading(bool v) {
    state = state.copyWith(loading: v);
  }

  void setFiles({
    required String sessionId,
    required String rel,
    required List<Map<String, dynamic>> entries,
  }) {
    state = state.copyWith(sessionId: sessionId, rel: rel, entries: entries, loading: false);
  }

  void clearFiles() {
    state = state.copyWith(clearSessionId: true, rel: '', entries: []);
  }
}