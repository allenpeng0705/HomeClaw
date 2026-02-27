import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import '../core_service.dart';

bool get _isMobilePlatform =>
    defaultTargetPlatform == TargetPlatform.android ||
    defaultTargetPlatform == TargetPlatform.iOS;

/// Parses homeclaw://connect?url=...&api_key=... and returns (url, apiKey) or null.
Map<String, String>? parseHomeClawConnect(String raw) {
  final uri = Uri.tryParse(raw);
  if (uri == null || uri.scheme != 'homeclaw' || uri.host != 'connect') return null;
  final url = uri.queryParameters['url'];
  if (url == null || url.isEmpty) return null;
  return {
    'url': url.replaceFirst(RegExp(r'/$'), ''),
    'api_key': uri.queryParameters['api_key'] ?? '',
  };
}

class ScanScreen extends StatefulWidget {
  final CoreService coreService;

  const ScanScreen({super.key, required this.coreService});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  bool _scanned = false;

  void _onDetect(BarcodeCapture capture) {
    if (_scanned) return;
    final list = capture.barcodes;
    for (final b in list) {
      final raw = b.rawValue;
      if (raw == null || raw.isEmpty) continue;
      final parsed = parseHomeClawConnect(raw);
      if (parsed == null) continue;
      _scanned = true;
      widget.coreService.saveSettings(
        baseUrl: parsed['url']!,
        apiKey: parsed['api_key']!,
      ).then((_) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Connected! Core URL and API key saved.')),
        );
        Navigator.of(context).pop(true);
      });
      return;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_isMobilePlatform) {
      return Scaffold(
        appBar: AppBar(title: const Text('Scan to connect')),
        body: const Center(
          child: Padding(
            padding: EdgeInsets.all(24.0),
            child: Text(
              'Scan to connect is available on Android and iOS.\nOn this device, enter Core URL and API key in Settings.',
              textAlign: TextAlign.center,
            ),
          ),
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: const Text('Scan QR to connect'),
      ),
      body: Stack(
        children: [
          MobileScanner(
            onDetect: _onDetect,
            controller: MobileScannerController(
              detectionSpeed: DetectionSpeed.normal,
              facing: CameraFacing.back,
            ),
          ),
          const Center(
            child: SizedBox(
              width: 240,
              height: 240,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  border: Border.fromBorderSide(
                    BorderSide(color: Colors.white54, width: 2),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
