import 'package:flutter/material.dart';
import 'core_service.dart';
import 'screens/chat_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final coreService = CoreService();
  await coreService.loadSettings();
  runApp(HomeClawCompanionApp(coreService: coreService));
}

class HomeClawCompanionApp extends StatelessWidget {
  final CoreService coreService;

  const HomeClawCompanionApp({super.key, required this.coreService});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'HomeClaw Companion',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
        useMaterial3: true,
      ),
      home: ChatScreen(coreService: coreService),
    );
  }
}
