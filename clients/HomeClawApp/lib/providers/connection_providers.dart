import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'providers.dart';

/// WebSocket connection status to Core.
enum WsStatus {
  /// Never attempted or disconnected after an error.
  disconnected,
  /// Actively attempting to connect.
  connecting,
  /// Open and registered with Core.
  connected,
}

/// Per-connection metadata tracked in [_wsStatusMap].
class _WsMeta {
  final WsStatus status;
  final String? sessionId;
  final String? registeredUserId;
  final DateTime? lastPing;

  const _WsMeta({
    this.status = WsStatus.disconnected,
    this.sessionId,
    this.registeredUserId,
    this.lastPing,
  });

  _WsMeta copyWith({
    WsStatus? status,
    String? sessionId,
    String? registeredUserId,
    DateTime? lastPing,
  }) =>
      _WsMeta(
        status: status ?? this.status,
        sessionId: sessionId ?? this.sessionId,
        registeredUserId: registeredUserId ?? this.registeredUserId,
        lastPing: lastPing ?? this.lastPing,
      );
}

/// Map from baseUrl to its WebSocket status metadata.
/// Multiple Cores can be configured (multi-instance support).
final wsStatusMapProvider =
    StateNotifierProvider<WsStatusMapNotifier, Map<String, _WsMeta>>(
  (ref) => WsStatusMapNotifier(),
);

class WsStatusMapNotifier extends StateNotifier<Map<String, _WsMeta>> {
  WsStatusMapNotifier() : super({});

  void updateStatus(String baseUrl, WsStatus status) {
    final meta = state[baseUrl] ?? const _WsMeta();
    state = {
      ...state,
      baseUrl: meta.copyWith(status: status),
    };
  }

  void setConnected(String baseUrl, String sessionId, String userId) {
    final meta = state[baseUrl] ?? const _WsMeta();
    state = {
      ...state,
      baseUrl: meta.copyWith(
        status: WsStatus.connected,
        sessionId: sessionId,
        registeredUserId: userId,
        lastPing: DateTime.now(),
      ),
    };
  }

  void recordPing(String baseUrl) {
    final meta = state[baseUrl];
    if (meta == null) return;
    state = {
      ...state,
      baseUrl: meta.copyWith(lastPing: DateTime.now()),
    };
  }
}

/// Convenience provider: status for the currently configured Core base URL.
final currentWsStatusProvider = Provider<WsStatus>((ref) {
  final core = ref.watch(coreServiceProvider);
  final meta = ref.watch(wsStatusMapProvider);
  return meta[core.baseUrl]?.status ?? WsStatus.disconnected;
});

/// Stream of incoming push messages from Core (cron, reminders, etc.).
/// Listeners should check event type and route accordingly.
final pushMessageStreamProvider = StreamProvider<Map<String, dynamic>>((ref) {
  final core = ref.watch(coreServiceProvider);
  return core.pushMessageStream;
});

/// Stream of push notification taps (FCM/APNs wake-up taps).
/// App uses this to navigate to the relevant chat.
final pushNotificationTapStreamProvider =
    StreamProvider<Map<String, dynamic>>((ref) {
  final core = ref.watch(coreServiceProvider);
  return core.pushNotificationTapStream;
});

/// ID of the ongoing async inbound request (can be cancelled via POST /inbound/cancel).
/// null when no request is in flight.
final ongoingInboundRequestIdProvider = StateProvider<String?>((ref) => null);

/// True when a pending inbound result exists and is waiting to be fetched.
final hasPendingInboundResultProvider = StateProvider<bool>((ref) => false);