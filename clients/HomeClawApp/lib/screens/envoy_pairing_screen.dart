import 'dart:async';

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
    final raw = list.first.rawValue;
    if (raw == null || raw.isEmpty) return;
    final code = raw.trim();

    Future<void> fail(String msg) async {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      setState(() {
        _scanned = false;
        _pairing = false;
        _statusText = '';
      });
    }

    final uri = Uri.tryParse(code);
    if (uri == null) {
      await fail('QR is not a valid URL');
      return;
    }

    final payload = PairingPayload.fromUri(uri);
    if (payload == null) {
      await fail('Not an Envoy mesh pairing QR (need envoy://pair?wsUrl=…)');
      return;
    }

    setState(() {
      _scanned = true;
      _pairing = true;
      _statusText = '';
    });

    final envoy = ref.read(envoyNodeServiceProvider);
    final notifier = ref.read(envoyMeshProvider.notifier);

    try {

      // Ensure identity is loaded
      if (!envoy.isInitialized) {
        if (mounted) setState(() => _statusText = 'Preparing device keys…');
        await envoy.initialize().timeout(
          const Duration(seconds: 30),
          onTimeout: () => throw TimeoutException(
            'Key setup timed out. Try again or restart the app.',
          ),
        );
        notifier.setInitialized(envoy.peerId!, envoy.ownerId!);
      }

      if (mounted) setState(() => _statusText = 'Connecting to home node…');
      final altWs = payload.reconstructedDialWsUrl();
      await envoy
          .connect(
            payload.wsUrl,
            pairingWsToken: payload.token,
            pairingRelayPeerId: payload.relayPeerId,
            pairingAlternateDialUrl: (altWs != null && altWs != payload.wsUrl)
                ? altWs
                : null,
          )
          .timeout(
        const Duration(seconds: 60),
        onTimeout: () => throw TimeoutException(
          'Connecting to the relay timed out. Check the URL, VPN or firewall, '
          'and that the Envoy node is running.',
        ),
      );
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
      try {
        await envoy.disconnect();
      } catch (_) {}
      final userMsg = e is TimeoutException
          ? (e.message ?? 'Operation timed out.')
          : e.toString();
      ref.read(envoyMeshProvider.notifier).setError(userMsg);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Pairing failed: $userMsg')),
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
