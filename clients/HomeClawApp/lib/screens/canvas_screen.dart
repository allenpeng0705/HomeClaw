import 'dart:io';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';
import '../core_service.dart';

/// Canvas screen: on mobile shows the canvas in an embedded WebView; on desktop
/// opens in the system browser because the embedded WebView does not resize properly.
class CanvasScreen extends StatefulWidget {
  final CoreService coreService;

  const CanvasScreen({super.key, required this.coreService});

  @override
  State<CanvasScreen> createState() => _CanvasScreenState();
}

class _CanvasScreenState extends State<CanvasScreen> {
  static const double _kWindowFraction = 0.85;

  WebViewController? _webController;
  double _lastW = 0;
  double _lastH = 0;

  static bool get _isDesktop =>
      Platform.isMacOS || Platform.isWindows || Platform.isLinux;

  Future<void> _openInBrowser(String url) async {
    try {
      await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final url = widget.coreService.canvasUrl;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Canvas'),
        leading: BackButton(onPressed: () => Navigator.of(context).pop()),
        actions: [
          if (url != null && url.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.open_in_browser),
              tooltip: 'Open in system browser',
              onPressed: () => _openInBrowser(url),
            ),
        ],
      ),
      body: _isDesktop ? _buildDesktopBody(context, url) : _buildMobileBody(url),
    );
  }

  /// On desktop the embedded WebView does not resize with the window (platform limitation).
  /// Show a clear prompt and "Open in browser" so the canvas works in the system browser.
  Widget _buildDesktopBody(BuildContext context, String? url) {
    if (url == null || url.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24.0),
          child: Text(
            'Set a Canvas URL in Settings to load the canvas. On desktop the canvas opens in your browser.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              'On desktop, the canvas opens in your system browser so it resizes correctly.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: () => _openInBrowser(url),
              icon: const Icon(Icons.open_in_browser),
              label: const Text('Open canvas in browser'),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMobileBody(String? url) {
    if (url == null || url.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24.0),
          child: Text(
            'Set a Canvas URL in Settings to load agent-driven UI here.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final w = constraints.maxWidth * _kWindowFraction;
        final h = constraints.maxHeight * _kWindowFraction;
        final hasValidSize = w >= 100 && h >= 100;

        if (hasValidSize &&
            (_webController == null || w != _lastW || h != _lastH)) {
          _lastW = w;
          _lastH = h;
          _webController = WebViewController()
            ..setJavaScriptMode(JavaScriptMode.unrestricted)
            ..loadRequest(Uri.parse(url));
        }

        return Align(
          alignment: Alignment.center,
          child: Container(
            width: w,
            height: h,
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surfaceContainerLow,
              borderRadius: BorderRadius.circular(12),
              boxShadow: [
                BoxShadow(
                  color: Theme.of(context)
                      .colorScheme
                      .shadow
                      .withOpacity(0.15),
                  blurRadius: 16,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            clipBehavior: Clip.antiAlias,
            child: !hasValidSize
                ? const Center(child: CircularProgressIndicator())
                : SizedBox(
                    width: w,
                    height: h,
                    child: WebViewWidget(
                      key: ValueKey('${w.toInt()}_${h.toInt()}'),
                      controller: _webController!,
                    ),
                  ),
          ),
        );
      },
    );
  }
}
