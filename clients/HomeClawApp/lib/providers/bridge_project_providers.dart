import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/core_service_models.dart';

/// State for Bridge project root browser dialog.
class BridgeRootBrowserState {
  final BridgeRootListResult? data;
  final String path;
  final String? error;
  final bool loading;
  final String? openingPath;
  final String? selectedDirAbsPath;

  const BridgeRootBrowserState({
    this.data,
    this.path = '.',
    this.error,
    this.loading = true,
    this.openingPath,
    this.selectedDirAbsPath,
  });

  BridgeRootBrowserState copyWith({
    BridgeRootListResult? data,
    bool clearData = false,
    String? path,
    String? error,
    bool clearError = false,
    bool? loading,
    String? openingPath,
    bool clearOpeningPath = false,
    String? selectedDirAbsPath,
    bool clearSelectedDirAbsPath = false,
  }) =>
      BridgeRootBrowserState(
        data: clearData ? null : (data ?? this.data),
        path: path ?? this.path,
        error: clearError ? null : (error ?? this.error),
        loading: loading ?? this.loading,
        openingPath: clearOpeningPath ? null : (openingPath ?? this.openingPath),
        selectedDirAbsPath: clearSelectedDirAbsPath ? null : (selectedDirAbsPath ?? this.selectedDirAbsPath),
      );
}

final bridgeRootBrowserProvider =
    StateNotifierProvider.autoDispose.family<BridgeRootBrowserNotifier, BridgeRootBrowserState, String>(
  (ref, backend) => BridgeRootBrowserNotifier(),
);

class BridgeRootBrowserNotifier extends StateNotifier<BridgeRootBrowserState> {
  BridgeRootBrowserNotifier() : super(const BridgeRootBrowserState());

  void setLoading(bool value) {
    state = state.copyWith(loading: value, clearError: true);
  }

  void setData(BridgeRootListResult r) {
    state = state.copyWith(data: r, loading: false, error: r.error);
  }

  void setError(String e) {
    state = state.copyWith(loading: false, error: e, clearData: true);
  }

  void setPath(String path) {
    state = state.copyWith(path: path);
  }

  void setOpeningPath(String? absPath) {
    state = state.copyWith(openingPath: absPath);
  }

  void clearOpeningPath() {
    state = state.copyWith(clearOpeningPath: true);
  }

  void setSelectedDirAbsPath(String? absPath) {
    state = state.copyWith(selectedDirAbsPath: absPath);
  }
}

/// Busy flag for Bridge project file preview attach action.
/// Keyed by bridgeBackend so all previews for the same backend share state.
final bridgeFilePreviewAttachBusyProvider =
    StateProvider.autoDispose.family<bool, String>(
  (ref, bridgeBackend) => false,
);

/// Busy flag for Bridge project file preview open-in-browser action.
/// Keyed by bridgeBackend so all previews for the same backend share state.
final bridgeFilePreviewBrowserBusyProvider =
    StateProvider.autoDispose.family<bool, String>(
  (ref, bridgeBackend) => false,
);

/// State for BridgeProjectFilesExplorer (Dev Bridge project browser).
class BridgeProjectState {
  final BridgeProjectListResult? result;
  final String? error;
  final bool loading;
  final BridgeProjectListEntry? selected;
  final bool attachBusy;
  final bool openBrowserBusy;
  final bool openFromRootBusy;

  const BridgeProjectState({
    this.result,
    this.error,
    this.loading = true,
    this.selected,
    this.attachBusy = false,
    this.openBrowserBusy = false,
    this.openFromRootBusy = false,
  });

  BridgeProjectState copyWith({
    BridgeProjectListResult? result,
    bool clearResult = false,
    String? error,
    bool clearError = false,
    bool? loading,
    BridgeProjectListEntry? selected,
    bool clearSelected = false,
    bool? attachBusy,
    bool? openBrowserBusy,
    bool? openFromRootBusy,
  }) =>
      BridgeProjectState(
        result: clearResult ? null : (result ?? this.result),
        error: clearError ? null : (error ?? this.error),
        loading: loading ?? this.loading,
        selected: clearSelected ? null : (selected ?? this.selected),
        attachBusy: attachBusy ?? this.attachBusy,
        openBrowserBusy: openBrowserBusy ?? this.openBrowserBusy,
        openFromRootBusy: openFromRootBusy ?? this.openFromRootBusy,
      );
}

final bridgeProjectProvider = StateNotifierProvider.autoDispose
    .family<BridgeProjectNotifier, BridgeProjectState, String>(
  (ref, bridgeBackend) => BridgeProjectNotifier(),
);

class BridgeProjectNotifier extends StateNotifier<BridgeProjectState> {
  BridgeProjectNotifier() : super(const BridgeProjectState());

  void setLoading(bool value) {
    state = state.copyWith(loading: value, clearError: true, clearSelected: true);
  }

  void setResult(BridgeProjectListResult r) {
    state = state.copyWith(result: r, error: r.error, loading: false, clearSelected: true);
  }

  void setError(String e) {
    state = state.copyWith(error: e, loading: false, clearResult: true);
  }

  void setSelected(BridgeProjectListEntry? entry) {
    state = state.copyWith(selected: entry);
  }

  void setAttachBusy(bool value) {
    state = state.copyWith(attachBusy: value);
  }

  void setOpenBrowserBusy(bool value) {
    state = state.copyWith(openBrowserBusy: value);
  }

  void setOpenFromRootBusy(bool value) {
    state = state.copyWith(openFromRootBusy: value);
  }
}