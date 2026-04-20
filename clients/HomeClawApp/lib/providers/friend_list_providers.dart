import 'dart:typed_data';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core_service.dart';
import 'providers.dart';

/// Friend list entry from GET /api/me/friends.
class FriendEntry {
  final String id;
  final String name;
  final String? type;
  final String? preset;
  final String? userId;
  final String? remoteInstanceId;
  final Uint8List? avatarBytes;

  const FriendEntry({
    required this.id,
    required this.name,
    this.type,
    this.preset,
    this.userId,
    this.remoteInstanceId,
    this.avatarBytes,
  });

  bool get isPerson => (type ?? '').trim().toLowerCase() == 'user' ||
      (type ?? '').trim().toLowerCase() == 'remote_user';
}

/// State for the friend list screen.
class FriendListState {
  final List<FriendEntry> friends;
  final bool loading;
  final String? error;
  final Uint8List? myAvatarBytes;
  /// User ids (of user friends) that have at least one unread message in inbox.
  final Set<String> unreadUserIds;

  const FriendListState({
    this.friends = const [],
    this.loading = true,
    this.error,
    this.myAvatarBytes,
    this.unreadUserIds = const {},
  });

  FriendListState copyWith({
    List<FriendEntry>? friends,
    bool? loading,
    String? error,
    bool clearError = false,
    Uint8List? myAvatarBytes,
    bool clearMyAvatar = false,
    Set<String>? unreadUserIds,
  }) =>
      FriendListState(
        friends: friends ?? this.friends,
        loading: loading ?? this.loading,
        error: clearError ? null : (error ?? this.error),
        myAvatarBytes: clearMyAvatar ? null : (myAvatarBytes ?? this.myAvatarBytes),
        unreadUserIds: unreadUserIds ?? this.unreadUserIds,
      );
}

/// Provider for friend list state (per-user, so family keyed by userId).
final friendListProvider = StateNotifierProvider.family<FriendListNotifier, FriendListState, String>(
  (ref, userId) => FriendListNotifier(userId, ref),
);

class FriendListNotifier extends StateNotifier<FriendListState> {
  final String _userId;
  final Ref _ref;

  FriendListNotifier(this._userId, this._ref) : super(const FriendListState());

  CoreService get _core => _ref.read(coreServiceProvider);

  void setLoading(bool value) {
    state = state.copyWith(loading: value);
  }

  void setError(String? e) {
    if (e == null) {
      state = state.copyWith(clearError: true, loading: false);
    } else {
      state = state.copyWith(error: e, loading: false);
    }
  }

  void setFriends(List<FriendEntry> friends) {
    state = state.copyWith(friends: friends, loading: false, clearError: true);
  }

  void setMyAvatar(Uint8List? bytes) {
    if (bytes == null || bytes.isEmpty) {
      state = state.copyWith(clearMyAvatar: true);
    } else {
      state = state.copyWith(myAvatarBytes: bytes);
    }
  }

  void setUnreadUserIds(Set<String> ids) {
    state = state.copyWith(unreadUserIds: ids);
  }
}