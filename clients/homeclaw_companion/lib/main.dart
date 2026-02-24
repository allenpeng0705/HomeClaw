import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'chat_history_store.dart';
import 'core_service.dart';
import 'screens/friend_list_screen.dart';
import 'screens/permissions_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await ChatHistoryStore.init();
  } catch (_) {
    // Hive init failed (e.g. storage permission); app still runs, chat history won't persist.
  }
  final coreService = CoreService();
  try {
    await coreService.loadSettings();
  } catch (_) {
    // Settings load failed; app uses defaults.
  }
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
  Future<Widget>? _homeFuture;

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
    return FriendListScreen(
      coreService: widget.coreService,
      initialMessage: widget.initialMessage,
    );
  }

  @override
  Widget build(BuildContext context) {
    final future = _homeFuture;
    if (future == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return FutureBuilder<Widget>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.hasData && snapshot.data != null) return snapshot.data!;
        if (snapshot.hasError) {
          return Scaffold(
            appBar: AppBar(title: const Text('HomeClaw')),
            body: Center(
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text('Something went wrong: ${snapshot.error}'),
                    const SizedBox(height: 16),
                    FilledButton(
                      onPressed: () => setState(() {
                        _homeFuture = _resolveHome();
                      }),
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ),
            ),
          );
        }
        return const Scaffold(
          body: Center(child: CircularProgressIndicator()),
        );
      },
    );
  }
}
