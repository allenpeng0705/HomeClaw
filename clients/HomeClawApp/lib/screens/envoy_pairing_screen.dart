import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../core_service.dart';
import '../envoy/envoy_protocol.dart';
import '../providers/envoy_providers.dart';

/// Scan a QR code from the EnvoyMesh home node and pair the app as a P2P peer.
///
/// The QR contains a [PairingPayload] encoded as:
///   `envoy://pair?wsUrl=...&relayPeerId=...&agentPeerId=...&agentPubKey=...&token=...`
///
/// Pairing flow:
/// 1. Scan QR → decode [PairingPayload]
/// 2. Connect to relay via [EnvoyNodeService.connect]
/// 3. Send [EnvoyIntent.devicePairRequest] to bridge agent (if `agentPeerId` present)
/// 4. Persist paired info so the bridge agent appears after app restart
class EnvoyPairingScreen extends ConsumerStatefulWidget {
  final CoreService coreService;

  const EnvoyPairingScreen({
    super.key,
    required this.coreService,
  });

  @override
  ConsumerState<EnvoyPairingScreen> createState() =>
      _EnvoyPairingScreenState();
}

class _EnvoyPairingScreenState extends ConsumerState<EnvoyPairingScreen> {
  bool _scanned = false;
  bool _pairing = false;
  String _statusText = '';

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (_scanned || _pairing) return;
    final list = capture.barcodes;
    if (list.isEmpty) return;
    final code = list.first.rawValue;
    if (code == null || code.isEmpty) return;
    final uri = Uri.tryParse(code);
    if (uri == null) return;

    // Decode pairing payload
    final payload = PairingPayload.fromUri(uri);
    if (payload == null) return;

    setState(() {
      _scanned = true;
      _pairing = true;
      _statusText = 'Connecting to home node…';
    });

    try {
      final envoy = ref.read(envoyNodeServiceProvider);
      final notifier = ref.read(envoyMeshProvider.notifier);

      // Ensure identity is loaded
      if (!envoy.isInitialized) {
        await envoy.initialize();
        notifier.setInitialized(envoy.peerId!, envoy.ownerId!);
      }

      // Connect to relay
      await envoy.connect(payload.wsUrl);
      notifier.setConnected(payload.wsUrl);

      // Send device pair request to bridge agent if present
      if (payload.agentPeerId != null && payload.agentPeerId!.isNotEmpty) {
        if (mounted) setState(() => _statusText = 'Sending pair request…');

        try {
          await envoy.sendDevicePairRequest(
            payload.agentPeerId!,
            note: 'HomeClaw Companion app pairing',
            pairingToken: payload.token,
          );
        } catch (_) {
          // Pair request is best-effort; the node may auto-accept on connect
        }
      }

      // Persist paired info
      await envoy.savePairedNodeInfo(payload);

      try {
        notifier.setLoadingContacts(true);
        final contacts = await envoy.fetchP2PContacts();
        notifier.setContacts(contacts);
      } catch (_) {
        notifier.setLoadingContacts(false);
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(payload.agentPeerId != null
                ? 'Paired! Bridge agent available in friend list.'
                : 'Connected via EnvoyMesh P2P'),
          ),
        );
        Navigator.of(context).maybePop();
      }
    } catch (e) {
      ref.read(envoyMeshProvider.notifier).setError(e.toString());
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Pairing failed: $e')),
        );
        setState(() {
          _scanned = false;
          _pairing = false;
          _statusText = '';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Scan EnvoyMesh QR'),
      ),
      body: _pairing
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const CircularProgressIndicator(),
                  const SizedBox(height: 16),
                  Text(_statusText),
                ],
              ),
            )
          : MobileScanner(
              onDetect: _onDetect,
              controller: MobileScannerController(
                detectionSpeed: DetectionSpeed.normal,
                facing: CameraFacing.back,
                torchEnabled: false,
              ),
            ),
    );
  }
}
