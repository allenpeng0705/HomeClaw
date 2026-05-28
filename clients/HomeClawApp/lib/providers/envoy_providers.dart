import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../envoy/envoy_node_service.dart';
import '../envoy/relay_client.dart';

// ============================================
// EnvoyMeshState
// ============================================

/// State for the EnvoyMesh P2P integration.
class EnvoyMeshState {
  /// Current WebSocket connection status.
  final RelayClientState connectionStatus;

  /// Own peer ID after initialization.
  final String? peerId;

  /// Own owner ID after initialization.
  final String? ownerId;

  /// Whether the identity has been initialized.
  final bool initialized;

  /// Last error message, if any.
  final String? error;

  /// The home node WebSocket URL, if connected.
  final String? homeNodeUrl;

  /// Known P2P contacts (bridge agent + bonded peers).
  final List<EnvoyMeshContact> contacts;

  /// Whether contacts are being fetched.
  final bool loadingContacts;

  const EnvoyMeshState({
    this.connectionStatus = RelayClientState.disconnected,
    this.peerId,
    this.ownerId,
    this.initialized = false,
    this.error,
    this.homeNodeUrl,
    this.contacts = const [],
    this.loadingContacts = false,
  });

  EnvoyMeshState copyWith({
    RelayClientState? connectionStatus,
    String? peerId,
    String? ownerId,
    bool? initialized,
    String? error,
    bool clearError = false,
    String? homeNodeUrl,
    List<EnvoyMeshContact>? contacts,
    bool? loadingContacts,
  }) =>
      EnvoyMeshState(
        connectionStatus: connectionStatus ?? this.connectionStatus,
        peerId: peerId ?? this.peerId,
        ownerId: ownerId ?? this.ownerId,
        initialized: initialized ?? this.initialized,
        error: clearError ? null : (error ?? this.error),
        homeNodeUrl: homeNodeUrl ?? this.homeNodeUrl,
        contacts: contacts ?? this.contacts,
        loadingContacts: loadingContacts ?? this.loadingContacts,
      );

  /// Whether we're currently connected to the home node.
  bool get isConnected =>
      connectionStatus == RelayClientState.connected;

  /// Whether the bridge agent is available as a contact.
  EnvoyMeshContact? get bridgeAgentContact {
    try {
      return contacts.firstWhere(
        (c) =>
            c.kind == EnvoyMeshContactKind.bridgeAgent || c.role == 'agent',
      );
    } catch (_) {
      return null;
    }
  }

  /// Human contacts (not the bridge agent).
  List<EnvoyMeshContact> get humanContacts => contacts
      .where((c) => c.kind == EnvoyMeshContactKind.bondedHuman)
      .toList();
}

// ============================================
// EnvoyMeshNotifier
// ============================================

class EnvoyMeshNotifier extends StateNotifier<EnvoyMeshState> {
  EnvoyMeshNotifier() : super(const EnvoyMeshState());

  void setInitialized(String peerId, String ownerId) {
    state = state.copyWith(
      initialized: true,
      peerId: peerId,
      ownerId: ownerId,
    );
  }

  void setConnectionStatus(RelayClientState status) {
    state = state.copyWith(connectionStatus: status);
  }

  void setConnected(String homeNodeUrl) {
    state = state.copyWith(
      connectionStatus: RelayClientState.connected,
      homeNodeUrl: homeNodeUrl,
    );
  }

  void setDisconnected() {
    state = state.copyWith(
      connectionStatus: RelayClientState.disconnected,
      homeNodeUrl: null,
      contacts: [],
    );
  }

  void setConnecting() {
    state = state.copyWith(connectionStatus: RelayClientState.connecting);
  }

  void setError(String error) {
    state = state.copyWith(
      connectionStatus: RelayClientState.error,
      error: error,
    );
  }

  void clearError() {
    state = state.copyWith(clearError: true);
  }

  void setLoadingContacts(bool loading) {
    state = state.copyWith(loadingContacts: loading);
  }

  void setContacts(List<EnvoyMeshContact> contacts) {
    state = state.copyWith(contacts: contacts, loadingContacts: false);
  }
}

// ============================================
// Providers
// ============================================

/// Provider for the singleton [EnvoyNodeService] instance.
///
/// Must be overridden at app startup via `ProviderScope.overrides` when
/// EnvoyMesh integration is enabled, similar to [coreServiceProvider].
final envoyNodeServiceProvider = Provider<EnvoyNodeService>((ref) {
  throw UnimplementedError(
    'envoyNodeServiceProvider must be overridden at app startup via '
    'ProviderScope.overrides or by providing an EnvoyNodeService instance.',
  );
});

/// Reactive provider for EnvoyMesh P2P state.
///
/// UI widgets watch this to react to connection changes, new contacts, etc.
final envoyMeshProvider =
    StateNotifierProvider<EnvoyMeshNotifier, EnvoyMeshState>(
  (ref) => EnvoyMeshNotifier(),
);
