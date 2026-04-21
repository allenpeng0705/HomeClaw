import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/core_service_models.dart';

/// Busy flag for Finder file preview attach action.
/// Keyed by sandboxScope so all previews for the same scope share state.
final finderFilePreviewAttachBusyProvider =
    StateProvider.autoDispose.family<bool, String>(
  (ref, sandboxScope) => false,
);

/// Busy flag for Finder file preview open-in-browser action.
/// Keyed by sandboxScope so all previews for the same scope share state.
final finderFilePreviewBrowserBusyProvider =
    StateProvider.autoDispose.family<bool, String>(
  (ref, sandboxScope) => false,
);

/// State for the finder files tab.
class FinderFilesState {
  final SandboxListResult? result;
  final String? error;
  final bool loading;
  final String? selectedPath;
  final bool attachBusy;
  final bool openBrowserBusy;

  const FinderFilesState({
    this.result,
    this.error,
    this.loading = true,
    this.selectedPath,
    this.attachBusy = false,
    this.openBrowserBusy = false,
  });

  FinderFilesState copyWith({
    SandboxListResult? result,
    bool clearResult = false,
    String? error,
    bool clearError = false,
    bool? loading,
    String? selectedPath,
    bool clearSelectedPath = false,
    bool? attachBusy,
    bool? openBrowserBusy,
  }) =>
      FinderFilesState(
        result: clearResult ? null : (result ?? this.result),
        error: clearError ? null : (error ?? this.error),
        loading: loading ?? this.loading,
        selectedPath: clearSelectedPath ? null : (selectedPath ?? this.selectedPath),
        attachBusy: attachBusy ?? this.attachBusy,
        openBrowserBusy: openBrowserBusy ?? this.openBrowserBusy,
      );
}

final finderFilesProvider = StateNotifierProvider.autoDispose
    .family<FinderFilesNotifier, FinderFilesState, String>(
  (ref, sandboxScope) => FinderFilesNotifier(),
);

class FinderFilesNotifier extends StateNotifier<FinderFilesState> {
  FinderFilesNotifier() : super(const FinderFilesState());

  void setLoading(bool value) {
    state = state.copyWith(loading: value, clearError: true, clearSelectedPath: true);
  }

  void setResult(SandboxListResult r) {
    state = state.copyWith(result: r, loading: false, clearError: true);
  }

  void setError(String e) {
    state = state.copyWith(error: e, loading: false, clearResult: true);
  }

  void setSelectedPath(String? path) {
    state = state.copyWith(selectedPath: path);
  }

  void setAttachBusy(bool value) {
    state = state.copyWith(attachBusy: value);
  }

  void setOpenBrowserBusy(bool value) {
    state = state.copyWith(openBrowserBusy: value);
  }
}
