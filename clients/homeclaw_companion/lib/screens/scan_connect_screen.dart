import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import '../core_service.dart';

/// Scan a QR code from `homeclaw pair` (homeclaw://connect?url=...&api_key=...)
/// and save URL + API key to CoreService.
class ScanConnectScreen extends StatefulWidget {
  final CoreService coreService;
  final VoidCallback? onSaved;

  const ScanConnectScreen({
    super.key,
    required this.coreService,
    this.onSaved,
  });

  @override
  State<ScanConnectScreen> createState() => _ScanConnectScreenState();
}

class _ScanConnectScreenState extends State<ScanConnectScreen> {
  bool _scanned = false;

  void _onDetect(BarcodeCapture capture) {
    if (_scanned) return;
    final list = capture.barcodes;
    if (list.isEmpty) return;
    final code = list.first.rawValue;
    if (code == null || code.isEmpty) return;
    final uri = Uri.tryParse(code);
    if (uri == null) return;
    if (uri.scheme != 'homeclaw' || uri.host != 'connect') return;
    setState(() => _scanned = true);
    final url = uri.queryParameters['url']?.trim();
    final apiKey = uri.queryParameters['api_key']?.trim();
    if (url == null || url.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Invalid QR: missing url')),
        );
        Navigator.of(context).maybePop();
      }
      return;
    }
    widget.coreService.saveSettings(baseUrl: url, apiKey: apiKey).then((_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Connected. You can go back.')),
        );
        widget.onSaved?.call();
        Navigator.of(context).maybePop();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Scan to connect'),
      ),
      body: MobileScanner(
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
