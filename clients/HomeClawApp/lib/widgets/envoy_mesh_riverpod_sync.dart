import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../envoy/relay_client.dart';
import '../providers/envoy_providers.dart';

/// Keeps [envoyMeshProvider] in sync with [EnvoyNodeService] when the connection
/// is established outside interactive screens (e.g. cold start auto-reconnect
/// in `main.dart`) and when the home node emits `bridge:status`.
class EnvoyMeshRiverpodSync extends ConsumerStatefulWidget {
  final Widget child;

  const EnvoyMeshRiverpodSync({super.key, required this.child});

  @override
  ConsumerState<EnvoyMeshRiverpodSync> createState() =>
      _EnvoyMeshRiverpodSyncState();
}

class _EnvoyMeshRiverpodSyncState extends ConsumerState<EnvoyMeshRiverpodSync> {
  StreamSubscription<RelayClientState>? _statusSub;
  StreamSubscription<Map<String, dynamic>>? _bridgeSub;

  @override
  void initState() {
    super.initState();
    final envoy = ref.read(envoyNodeServiceProvider);
    final notifier = ref.read(envoyMeshProvider.notifier);

    _statusSub = envoy.onStatusChange.listen((state) {
      if (!mounted) return;
      if (state == RelayClientState.connected) {
        if (envoy.peerId != null &&
            envoy.ownerId != null &&
            !ref.read(envoyMeshProvider).initialized) {
          notifier.setInitialized(envoy.peerId!, envoy.ownerId!);
        }
        final url = envoy.homeNodeUrl;
        if (url != null && url.isNotEmpty) {
          notifier.setConnected(url);
        }
        unawaited(_refreshContacts(notifier));
      } else if (state == RelayClientState.disconnected ||
          state == RelayClientState.error) {
        notifier.setDisconnected();
      }
    });

    _bridgeSub = envoy.onBridgeStatusFromNode.listen((_) {
      if (!mounted) return;
      if (envoy.connectionState != RelayClientState.connected) return;
      unawaited(_refreshContacts(ref.read(envoyMeshProvider.notifier)));
    });

    if (envoy.connectionState == RelayClientState.connected) {
      if (envoy.peerId != null &&
          envoy.ownerId != null &&
          !ref.read(envoyMeshProvider).initialized) {
        notifier.setInitialized(envoy.peerId!, envoy.ownerId!);
      }
      final url = envoy.homeNodeUrl;
      if (url != null && url.isNotEmpty) {
        notifier.setConnected(url);
      }
      unawaited(_refreshContacts(notifier));
    }
  }

  Future<void> _refreshContacts(EnvoyMeshNotifier notifier) async {
    final envoy = ref.read(envoyNodeServiceProvider);
    if (envoy.connectionState != RelayClientState.connected) return;
    notifier.setLoadingContacts(true);
    try {
      final contacts = await envoy.fetchP2PContacts();
      if (!mounted) return;
      notifier.setContacts(contacts);
    } catch (_) {
      if (mounted) notifier.setLoadingContacts(false);
    }
  }

  @override
  void dispose() {
    _statusSub?.cancel();
    _bridgeSub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
