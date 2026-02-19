import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'core_service.dart';
import 'screens/chat_screen.dart';
import 'screens/permissions_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final coreService = CoreService();
  await coreService.loadSettings();
  String? initialMessage;
  try {
    final appLinks = AppLinks();
    final uri = await appLinks.getInitialLink();
    if (uri != null && (uri.path == 'agent' || uri.path == '/agent')) {
      initialMessage = uri.queryParameters['message'];
    }
  } catch (_) {}
  runApp(HomeClawCompanionApp(coreService: coreService, initialMessage: initialMessage));
}

class HomeClawCompanionApp extends StatelessWidget {
  final CoreService coreService;
  final String? initialMessage;

  const HomeClawCompanionApp({super.key, required this.coreService, this.initialMessage});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'HomeClaw Companion',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
        useMaterial3: true,
      ),
      home: _InitialScreen(coreService: coreService, initialMessage: initialMessage),
    );
  }
}

/// Shows permissions screen on first launch, then chat.
class _InitialScreen extends StatefulWidget {
  final CoreService coreService;
  final String? initialMessage;

  const _InitialScreen({required this.coreService, this.initialMessage});

  @override
  State<_InitialScreen> createState() => _InitialScreenState();
}

class _InitialScreenState extends State<_InitialScreen> {
  late final Future<Widget> _homeFuture;

  @override
  void initState() {
    super.initState();
    _homeFuture = _resolveHome();
  }

  Future<Widget> _resolveHome() async {
    final showPermissions = !(await getPermissionsIntroShown());
    if (showPermissions) {
      return PermissionsScreen(
        coreService: widget.coreService,
        initialMessage: widget.initialMessage,
      );
    }
    return ChatScreen(
      coreService: widget.coreService,
      initialMessage: widget.initialMessage,
    );
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Widget>(
      future: _homeFuture,
      builder: (context, snapshot) {
        if (snapshot.hasData) return snapshot.data!;
        return const Scaffold(
          body: Center(child: CircularProgressIndicator()),
        );
      },
    );
  }
}
