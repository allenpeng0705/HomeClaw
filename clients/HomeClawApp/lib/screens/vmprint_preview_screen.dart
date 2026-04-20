import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';

class VmprintPreviewScreen extends ConsumerStatefulWidget {
  final String url;
  const VmprintPreviewScreen({super.key, required this.url});

  @override
  ConsumerState<VmprintPreviewScreen> createState() => _VmprintPreviewScreenState();
}

class _VmprintPreviewScreenState extends ConsumerState<VmprintPreviewScreen> {
  static bool get _isDesktop => Platform.isMacOS || Platform.isWindows || Platform.isLinux;
  WebViewController? _controller;

  Future<void> _openExternal() async {
    try {
      await launchUrl(Uri.parse(widget.url), mode: LaunchMode.externalApplication);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    if (_isDesktop) {
      return Scaffold(
        appBar: AppBar(title: const Text('VMPrint Preview')),
        body: Center(
          child: FilledButton.icon(
            onPressed: _openExternal,
            icon: const Icon(Icons.open_in_browser),
            label: const Text('Open preview in browser'),
          ),
        ),
      );
    }
    _controller ??= (WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..loadRequest(Uri.parse(widget.url)));
    return Scaffold(
      appBar: AppBar(
        title: const Text('VMPrint Preview'),
        actions: [
          IconButton(
            onPressed: _openExternal,
            icon: const Icon(Icons.open_in_browser),
            tooltip: 'Open in browser',
          ),
        ],
      ),
      body: WebViewWidget(controller: _controller!),
    );
  }
}
