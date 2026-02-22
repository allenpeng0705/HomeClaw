import 'dart:io';

import 'package:flutter/material.dart';
import 'package:homeclaw_voice/homeclaw_voice.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core_service.dart';
import 'chat_screen.dart';

/// Keys for [SharedPreferences] (caller must ensure shared_preferences is used).
const String _keyPermissionsIntroShown = 'permissions_intro_shown';

/// Call after user has completed or skipped the permissions screen.
Future<void> markPermissionsIntroShown() async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setBool(_keyPermissionsIntroShown, true);
}

/// Whether the permissions intro has already been shown.
Future<bool> getPermissionsIntroShown() async {
  final prefs = await SharedPreferences.getInstance();
  return prefs.getBool(_keyPermissionsIntroShown) ?? false;
}

/// One permission row: title, description, status, and Allow button.
class _PermissionItem {
  final String title;
  final String description;
  final Future<PermissionStatus> Function() request;
  final String? instructionsOnly; // If set, no request button; show instructions (e.g. screen recording)

  _PermissionItem({
    required this.title,
    required this.description,
    required this.request,
    this.instructionsOnly,
  });
}

class PermissionsScreen extends StatefulWidget {
  final CoreService coreService;
  final String? initialMessage;
  /// When true, opened from Settings; bottom button is "Done" and pops back (no replace).
  final bool fromSettings;

  const PermissionsScreen({
    super.key,
    required this.coreService,
    this.initialMessage,
    this.fromSettings = false,
  });

  @override
  State<PermissionsScreen> createState() => _PermissionsScreenState();
}

class _PermissionsScreenState extends State<PermissionsScreen> {
  final _voice = HomeclawVoice();
  final Map<String, PermissionStatus> _status = {};
  final Map<String, bool> _requesting = {};
  bool _continuing = false;

  List<_PermissionItem> _buildItems() {
    final items = <_PermissionItem>[];

    // Microphone + Speech (voice input). On macOS/iOS, speech_to_text triggers both when we call isAvailable.
    items.add(_PermissionItem(
      title: 'Microphone & Speech',
      description: 'For voice input in chat.',
      request: () async {
        final ok = await _voice.isAvailable;
        return ok ? PermissionStatus.granted : PermissionStatus.denied;
      },
    ));

    // Camera (photos & videos)
    items.add(_PermissionItem(
      title: 'Camera',
      description: 'For taking photos and recording videos to send.',
      request: () => Permission.camera.request(),
    ));

    // Notifications
    items.add(_PermissionItem(
      title: 'Notifications',
      description: 'To show reply notifications when the app is in the background.',
      request: () => Permission.notification.request(),
    ));

    // Screen recording (macOS only) – no API to request; user must allow in System Settings.
    if (Platform.isMacOS) {
      items.add(_PermissionItem(
        title: 'Screen Recording',
        description: 'For sharing your screen when Core asks. Allow in System Settings → Privacy & Security → Screen Recording.',
        request: () async => PermissionStatus.denied,
        instructionsOnly: 'System Settings → Privacy & Security → Screen Recording',
      ));
    }

    return items;
  }

  Future<void> _requestPermission(_PermissionItem item) async {
    final key = item.title;
    if (item.instructionsOnly != null) return;
    setState(() => _requesting[key] = true);
    try {
      final status = await item.request();
      if (mounted) setState(() {
        _requesting[key] = false;
        _status[key] = status;
      });
    } catch (e) {
      if (mounted) setState(() {
        _requesting[key] = false;
        _status[key] = PermissionStatus.denied;
      });
    }
  }

  Future<void> _continue() async {
    setState(() => _continuing = true);
    if (!widget.fromSettings) await markPermissionsIntroShown();
    if (!mounted) return;
    if (widget.fromSettings) {
      Navigator.of(context).pop();
    } else {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(
          builder: (context) => ChatScreen(
            coreService: widget.coreService,
            initialMessage: widget.initialMessage,
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final items = _buildItems();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Permissions'),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'HomeClaw needs a few permissions to work. You can allow them now or when you first use each feature.',
                style: TextStyle(fontSize: 16),
              ),
              const SizedBox(height: 24),
              Expanded(
                child: ListView.builder(
                  itemCount: items.length,
                  itemBuilder: (context, index) {
                    final item = items[index];
                    final key = item.title;
                    final status = _status[key];
                    final requesting = _requesting[key] ?? false;
                    final isInstructionsOnly = item.instructionsOnly != null;

                    return Card(
                      margin: const EdgeInsets.only(bottom: 12),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    item.title,
                                    style: Theme.of(context).textTheme.titleMedium,
                                  ),
                                ),
                                if (!isInstructionsOnly) ...[
                                  if (status != null)
                                    Icon(
                                      status.isGranted ? Icons.check_circle : Icons.cancel,
                                      color: status.isGranted ? Colors.green : Colors.grey,
                                      size: 24,
                                    ),
                                  if (status == null || !status.isGranted) ...[
                                    FilledButton(
                                      onPressed: requesting ? null : () => _requestPermission(item),
                                      child: requesting
                                          ? const SizedBox(
                                              width: 20,
                                              height: 20,
                                              child: CircularProgressIndicator(strokeWidth: 2),
                                            )
                                          : const Text('Allow'),
                                    ),
                                    if (status != null && status.isPermanentlyDenied)
                                      Padding(
                                        padding: const EdgeInsets.only(left: 8.0),
                                        child: TextButton(
                                          onPressed: () => openAppSettings(),
                                          child: const Text('Open Settings'),
                                        ),
                                      ),
                                  ],
                                ],
                              ],
                            ),
                            const SizedBox(height: 8),
                            Text(
                              item.description,
                              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                                  ),
                            ),
                            if (item.instructionsOnly != null) ...[
                              const SizedBox(height: 8),
                              Text(
                                item.instructionsOnly!,
                                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                      fontFamily: 'monospace',
                                    ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _continuing ? null : _continue,
                child: _continuing
                    ? const SizedBox(
                        height: 24,
                        width: 24,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(widget.fromSettings ? 'Done' : 'Continue'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
