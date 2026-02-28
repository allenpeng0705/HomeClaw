import 'dart:async';
import 'dart:io';

import 'package:app_links/app_links.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:home_claw_app/l10n/app_localizations.dart';
import 'package:homeclaw_native/homeclaw_native.dart';
import 'chat_history_store.dart';
import 'core_service.dart';
import 'screens/friend_list_screen.dart';
import 'screens/login_screen.dart';
import 'screens/permissions_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await ChatHistoryStore.init();
  } catch (_) {
    // Hive init failed (e.g. storage permission); app still runs, chat history won't persist.
  }
  // Firebase only on Android (FCM). iOS/macOS use native APNs only (no Firebase, works in China).
  if (Platform.isAndroid) {
    try {
      await Firebase.initializeApp();
    } catch (_) {
      // Firebase not configured; push notifications disabled on Android.
    }
  }
  final coreService = CoreService();
  try {
    await coreService.loadSettings();
  } catch (_) {
    // Settings load failed; app uses defaults.
  }
  // Register push token with Core when we have a session user (done per-chat in ChatScreen).
  if (coreService.isLoggedIn) {
    coreService.registerPushTokenWithCore(coreService.sessionUserId!);
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
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
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
  StreamSubscription<Map<String, dynamic>>? _pushSubscription;

  @override
  void initState() {
    super.initState();
    _homeFuture = _resolveHome();
    _pushSubscription = widget.coreService.pushMessageStream.listen((push) {
      try {
        final text = push['text'] as String? ?? '';
        if (text.isEmpty) return;
        final userId = push['user_id'] as String? ?? widget.coreService.sessionUserId;
        final friendId = (push['friend_id'] ?? push['from_friend']) as String?;
        final source = push['source'] as String? ?? 'push';
        final images = push['images'] as List<dynamic>?;
        final imageList = images != null ? images.whereType<String>().toList() : null;
        if (userId != null && userId.isNotEmpty && friendId != null && friendId.toString().trim().isNotEmpty) {
          ChatHistoryStore().appendMessage(
            userId,
            friendId.toString().trim(),
            text,
            false,
            imageList != null && imageList.isNotEmpty ? imageList : null,
          );
        }
        final title = source == 'reminder' ? 'Reminder' : (friendId?.toString() ?? 'HomeClaw');
        final body = text.length > 80 ? '${text.substring(0, 80)}…' : text;
        HomeclawNative().showNotification(title: title, body: body);
      } catch (_) {
        // Never let push handling crash the app (e.g. notification unsupported on platform).
      }
    });
  }

  @override
  void dispose() {
    _pushSubscription?.cancel();
    super.dispose();
  }

  Future<Widget> _resolveHome() async {
    final showPermissions = !(await getPermissionsIntroShown());
    if (showPermissions) {
      return PermissionsScreen(
        coreService: widget.coreService,
        initialMessage: widget.initialMessage,
      );
    }
    if (!widget.coreService.isLoggedIn) {
      return LoginScreen(coreService: widget.coreService);
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
          final l10n = AppLocalizations.of(context)!;
          return Scaffold(
            appBar: AppBar(title: Text(l10n.homeClaw)),
            body: Center(
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text('${l10n.somethingWentWrong}: ${snapshot.error}'),
                    const SizedBox(height: 16),
                    FilledButton(
                      onPressed: () => setState(() {
                        _homeFuture = _resolveHome();
                      }),
                      child: Text(l10n.retry),
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
