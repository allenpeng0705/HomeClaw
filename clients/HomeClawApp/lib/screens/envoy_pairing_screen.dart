import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../core_service.dart';
import '../providers/envoy_providers.dart';

/// Scan a QR code from the EnvoyMesh home node (`envoy://pair?wsUrl=ws://...`)
/// and connect the app as a P2P peer.
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
  bool _connecting = false;

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (_scanned || _connecting) return;
    final list = capture.barcodes;
    if (list.isEmpty) return;
    final code = list.first.rawValue;
    if (code == null || code.isEmpty) return;
    final uri = Uri.tryParse(code);
    if (uri == null) return;
    // Support envoy://pair?wsUrl=... and homeclaw://envoy-pair?wsUrl=...
    final isEnvoyPair = (uri.scheme == 'envoy' && uri.host == 'pair') ||
        (uri.scheme == 'homeclaw' && uri.host == 'envoy-pair');
    if (!isEnvoyPair) return;

    setState(() => _scanned = true);
    final wsUrl = uri.queryParameters['wsUrl']?.trim();
    if (wsUrl == null || wsUrl.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Invalid QR: missing wsUrl')),
        );
        Navigator.of(context).maybePop();
      }
      return;
    }

    setState(() => _connecting = true);
    try {
      final envoy = ref.read(envoyNodeServiceProvider);
      if (!envoy.isInitialized) {
        await envoy.initialize();
        ref.read(envoyMeshProvider.notifier).setInitialized(
          envoy.peerId!,
          envoy.ownerId!,
        );
      }
      await envoy.connect(wsUrl);
      ref.read(envoyMeshProvider.notifier).setConnected(wsUrl);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Connected via EnvoyMesh P2P')),
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
          _connecting = false;
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
      body: _connecting
          ? const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 16),
                  Text('Connecting to home node…'),
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
