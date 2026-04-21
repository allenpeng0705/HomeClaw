import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/core_service_models.dart';

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
  (ref, bridgeBackend) => BridgeProjectNotifier(bridgeBackend),
);

class BridgeProjectNotifier extends StateNotifier<BridgeProjectState> {
  final String _bridgeBackend;

  BridgeProjectNotifier(this._bridgeBackend) : super(const BridgeProjectState());

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