import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import '../core_service.dart';

/// Agent-driven UI: full-screen WebView loading [CoreService.canvasUrl].
class CanvasScreen extends StatelessWidget {
  final CoreService coreService;

  const CanvasScreen({super.key, required this.coreService});

  @override
  Widget build(BuildContext context) {
    final url = coreService.canvasUrl;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Canvas'),
      ),
      body: url == null || url.isEmpty
          ? const Center(
              child: Padding(
                padding: EdgeInsets.all(24.0),
                child: Text(
                  'Set a Canvas URL in Settings to load agent-driven UI here.',
                  textAlign: TextAlign.center,
                ),
              ),
            )
          : WebViewWidget(
              controller: WebViewController()
                ..setJavaScriptMode(JavaScriptMode.unrestricted)
                ..loadRequest(Uri.parse(url)),
            ),
    );
  }
}
