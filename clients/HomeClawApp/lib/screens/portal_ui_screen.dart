import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../core_service.dart';

/// WebView that loads Core's /portal-ui (Portal proxy). Passes token in URL so Core allows access.
/// Back button clears token and returns to login.
class PortalUiScreen extends StatefulWidget {
  final CoreService coreService;

  const PortalUiScreen({super.key, required this.coreService});

  @override
  State<PortalUiScreen> createState() => _PortalUiScreenState();
}

class _PortalUiScreenState extends State<PortalUiScreen> {
  late final WebViewController _controller;
  String? _token;
  String _baseUrl = '';

  @override
  void initState() {
    super.initState();
    _token = widget.coreService.portalAdminToken;
    _baseUrl = widget.coreService.baseUrl.replaceFirst(RegExp(r'/$'), '');
    final initialUrl = _token != null && _token!.isNotEmpty
        ? '$_baseUrl/portal-ui?token=${Uri.encodeComponent(_token!)}'
        : '$_baseUrl/portal-ui';
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (_) {},
          onWebResourceError: (error) {
            if (error.errorCode == 401) {
              widget.coreService.clearPortalAdminToken();
            }
          },
          onNavigationRequest: (request) {
            final url = request.url;
            if (_token == null || _token!.isEmpty) return NavigationDecision.navigate;
            if (url.contains('token=')) return NavigationDecision.navigate;
            if (!url.startsWith(_baseUrl) || !url.contains('/portal-ui')) return NavigationDecision.navigate;
            final separator = url.contains('?') ? '&' : '?';
            final withToken = '$url$separator${'token='}${Uri.encodeComponent(_token!)}';
            _controller.loadRequest(Uri.parse(withToken));
            return NavigationDecision.prevent;
          },
        ),
      )
      ..loadRequest(Uri.parse(initialUrl));
  }

  Future<void> _logoutAndPop() async {
    await widget.coreService.clearPortalAdminToken();
    if (!mounted) return;
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        await _logoutAndPop();
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Core setting'),
          leading: IconButton(
            icon: const Icon(Icons.close),
            onPressed: _logoutAndPop,
            tooltip: 'Log out',
          ),
        ),
        body: WebViewWidget(controller: _controller),
      ),
    );
  }
}
