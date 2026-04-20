import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';

/// Full-screen image viewer. Tap anywhere to go back.
class FullScreenImagePage extends StatelessWidget {
  final String imageRef;
  final String coreBaseUrl;
  final Map<String, String>? fetchHeaders;

  const FullScreenImagePage({
    super.key,
    required this.imageRef,
    required this.coreBaseUrl,
    this.fetchHeaders,
  });

  @override
  Widget build(BuildContext context) {
    final trimmed = imageRef.trim();
    Widget bodyChild;
    if (trimmed.startsWith('data:image/')) {
      final bytes = _decodeDataUrlToBytes(trimmed);
      if (bytes != null && bytes.isNotEmpty) {
        bodyChild = Center(
          child: InteractiveViewer(
            minScale: 0.5,
            maxScale: 4.0,
            child: Image.memory(
              bytes,
              fit: BoxFit.contain,
              gaplessPlayback: true,
              errorBuilder: (_, __, ___) => const Icon(Icons.broken_image,
                  color: Colors.white54, size: 64),
            ),
          ),
        );
      } else {
        bodyChild = const Center(
            child: Icon(Icons.broken_image, color: Colors.white54, size: 64));
      }
    } else {
      String? net;
      final u = Uri.tryParse(trimmed);
      if (u != null &&
          u.hasScheme &&
          (u.scheme == 'http' || u.scheme == 'https')) {
        net = trimmed;
      } else if (trimmed.startsWith('/')) {
        final base = coreBaseUrl.replaceFirst(RegExp(r'/$'), '');
        net = '$base$trimmed';
      }
      if (net != null) {
        bodyChild = Center(
          child: InteractiveViewer(
            minScale: 0.5,
            maxScale: 4.0,
            child: Image.network(
              net,
              fit: BoxFit.contain,
              headers: fetchHeaders,
              loadingBuilder: (c, child, prog) {
                if (prog == null) return child;
                return const SizedBox(
                  width: 48,
                  height: 48,
                  child: CircularProgressIndicator(
                      color: Colors.white54, strokeWidth: 2),
                );
              },
              errorBuilder: (_, __, ___) => const Icon(Icons.broken_image,
                  color: Colors.white54, size: 64),
            ),
          ),
        );
      } else {
        bodyChild = const Center(
            child: Icon(Icons.broken_image, color: Colors.white54, size: 64));
      }
    }
    return Scaffold(
      backgroundColor: Colors.black,
      body: GestureDetector(
        onTap: () => Navigator.of(context).pop(),
        behavior: HitTestBehavior.opaque,
        child: Stack(
          fit: StackFit.expand,
          children: [
            bodyChild,
            SafeArea(
              child: Align(
                alignment: Alignment.topRight,
                child: IconButton(
                  icon: const Icon(Icons.close, color: Colors.white, size: 28),
                  onPressed: () => Navigator.of(context).pop(),
                  tooltip: 'Close',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Decode a data URL (e.g. `data:image/png;base64,...`) to bytes.
Uint8List? _decodeDataUrlToBytes(String dataUrl) {
  final comma = dataUrl.indexOf(',');
  if (comma < 0) return null;
  try {
    final b64 = dataUrl.substring(comma + 1).replaceAll(RegExp(r'\s'), '');
    return base64Decode(b64);
  } catch (_) {
    return null;
  }
}
