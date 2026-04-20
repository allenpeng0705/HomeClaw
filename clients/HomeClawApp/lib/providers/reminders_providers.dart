import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core_service.dart';
import 'providers.dart';

/// State for reminders tab.
class RemindersState {
  final List<ReminderListItem> items;
  final bool loading;
  final String? error;
  final String? deletingId;

  const RemindersState({
    this.items = const [],
    this.loading = true,
    this.error,
    this.deletingId,
  });

  RemindersState copyWith({
    List<ReminderListItem>? items,
    bool? loading,
    String? error,
    bool clearError = false,
    String? deletingId,
    bool clearDeletingId = false,
  }) =>
      RemindersState(
        items: items ?? this.items,
        loading: loading ?? this.loading,
        error: clearError ? null : (error ?? this.error),
        deletingId: clearDeletingId ? null : (deletingId ?? this.deletingId),
      );
}

final remindersProvider = StateNotifierProvider<RemindersNotifier, RemindersState>(
  (ref) => RemindersNotifier(ref),
);

class RemindersNotifier extends StateNotifier<RemindersState> {
  final Ref _ref;

  RemindersNotifier(this._ref) : super(const RemindersState());

  CoreService get _core => _ref.read(coreServiceProvider);

  void setLoading(bool value) {
    state = state.copyWith(loading: value);
  }

  void setItems(List<ReminderListItem> items) {
    state = state.copyWith(items: items, loading: false, clearError: true);
  }

  void setError(String e) {
    state = state.copyWith(error: e, loading: false, items: []);
  }

  void setDeletingId(String? id) {
    state = state.copyWith(deletingId: id, clearDeletingId: id == null);
  }

  void removeItem(String id) {
    state = state.copyWith(
      items: state.items.where((x) => x.id != id).toList(),
      clearDeletingId: true,
    );
  }
}
