import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import '../chat_history_store.dart';
import '../core_service.dart';
import '../envoy/relay_client.dart';
import '../providers/envoy_providers.dart';
import '../providers/settings_providers.dart';
import 'change_password_screen.dart';
import 'envoy_pairing_screen.dart';
import 'permissions_screen.dart';
import 'scan_connect_screen.dart';
import 'skills_screen.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  final CoreService coreService;

  const SettingsScreen({super.key, required this.coreService});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  late TextEditingController _urlController;
  late TextEditingController _apiKeyController;
  late TextEditingController _canvasUrlController;
  late TextEditingController _nodesUrlController;
  late TextEditingController _nodeIdController;
  late TextEditingController _execCommandController;
  late TextEditingController _envoyUrlController;
  late final SettingsNotifier _settingsNotifier;
  /// Non-null after [_loadEnvoyP2pFields] when a QR pairing payload was saved.
  String? _envoyPairedHint;

  @override
  void initState() {
    super.initState();
    _settingsNotifier = ref.read(settingsProvider.notifier);
    _urlController = TextEditingController(text: widget.coreService.baseUrl);
    _apiKeyController = TextEditingController(text: widget.coreService.apiKey ?? '');
    _canvasUrlController = TextEditingController(text: widget.coreService.canvasUrl ?? '');
    _nodesUrlController = TextEditingController(text: widget.coreService.nodesUrl ?? 'http://127.0.0.1:3020');
    _nodeIdController = TextEditingController(text: 'companion');
    _execCommandController = TextEditingController();
    _envoyUrlController = TextEditingController(text: 'ws://192.168.1.100:3030/ws');
    if (widget.coreService.isLoggedIn) _loadMyAvatar();
    unawaited(_loadEnvoyP2pFields());
  }

  Future<void> _loadEnvoyP2pFields() async {
    final envoy = ref.read(envoyNodeServiceProvider);
    try {
      if (!envoy.isInitialized) await envoy.initialize();
      final paired = await envoy.getPairedNodeInfo();
      final savedUrl = await envoy.getSavedHomeNodeUrl();
      if (!mounted) return;
      setState(() {
        if (savedUrl != null && savedUrl.trim().isNotEmpty) {
          _envoyUrlController.text = savedUrl.trim();
        }
        _envoyPairedHint = paired != null
            ? 'QR pairing saved · reconnect uses stored home node URL'
            : null;
      });
    } catch (_) {}
  }

  Future<void> _loadMyAvatar() async {
    if (!widget.coreService.isLoggedIn) return;
    _settingsNotifier.setAvatarLoading(true);
    try {
      final bytes = await widget.coreService.fetchAvatarWithAuth(widget.coreService.meAvatarUrl);
      _settingsNotifier.setMyAvatar(bytes);
    } catch (_) {
      _settingsNotifier.setMyAvatar(null);
    }
  }

  Future<void> _uploadProfilePicture() async {
    if (!widget.coreService.isLoggedIn) return;
    try {
      final picker = ImagePicker();
      final x = await picker.pickImage(source: ImageSource.gallery, maxWidth: 512, imageQuality: 85);
      if (x == null || !mounted) return;
      final path = x.path;
      if (path.isEmpty) return;
      _settingsNotifier.setAvatarUploading(true);
      await widget.coreService.uploadMyAvatar(File(path));
      await _loadMyAvatar();
      final state = ref.read(settingsProvider);
      if (mounted && state.myAvatarBytes != null && state.myAvatarBytes!.isNotEmpty) {
        await widget.coreService.saveMyAvatarToCache(state.myAvatarBytes!);
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Profile picture updated')));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Upload failed: $e')));
    } finally {
      _settingsNotifier.setAvatarUploading(false);
    }
  }

  @override
  void dispose() {
    _urlController.dispose();
    _apiKeyController.dispose();
    _canvasUrlController.dispose();
    _nodesUrlController.dispose();
    _nodeIdController.dispose();
    _execCommandController.dispose();
    _envoyUrlController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    await widget.coreService.saveSettings(
      baseUrl: _urlController.text,
      apiKey: _apiKeyController.text,
    );
    await widget.coreService.saveCanvasUrl(_canvasUrlController.text);
    await widget.coreService.saveNodesUrl(_nodesUrlController.text);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Settings saved')),
      );
    }
  }

  Future<void> _addExecCommand() async {
    final cmd = _execCommandController.text.trim();
    if (cmd.isEmpty) return;
    final list = List<String>.from(widget.coreService.execAllowlist)..add(cmd);
    await widget.coreService.saveExecAllowlist(list);
    _execCommandController.clear();
    _settingsNotifier.setExecAllowlist(list);
  }

  Future<void> _removeExecCommand(String cmd) async {
    final list = widget.coreService.execAllowlist.where((c) => c != cmd).toList();
    await widget.coreService.saveExecAllowlist(list);
    _settingsNotifier.setExecAllowlist(list);
  }

  Future<void> _clearMemory(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.coreService.postMemoryReset();
      if (mounted) messenger.showSnackBar(const SnackBar(content: Text('Memory cleared')));
    } catch (e) {
      if (mounted) messenger.showSnackBar(SnackBar(content: Text('Clear memory failed: $e')));
    }
  }

  Future<void> _clearKnowledgeBase(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.coreService.postKnowledgeBaseReset();
      if (mounted) messenger.showSnackBar(const SnackBar(content: Text('Knowledge base cleared')));
    } catch (e) {
      if (mounted) messenger.showSnackBar(SnackBar(content: Text('Clear knowledge base failed: $e')));
    }
  }

  Future<void> _clearAllSkillsPlugins(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.coreService.postTestingClearAll();
      if (mounted) messenger.showSnackBar(const SnackBar(content: Text('Skills & plugins cleared')));
    } catch (e) {
      if (mounted) messenger.showSnackBar(SnackBar(content: Text('Clear all failed: $e')));
    }
  }

  Future<void> _clearChatHistories(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ChatHistoryStore().clearAll();
      if (mounted) messenger.showSnackBar(const SnackBar(content: Text('Chat histories (Hive) cleared')));
    } catch (e) {
      if (mounted) messenger.showSnackBar(SnackBar(content: Text('Clear chat histories failed: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final settings = ref.watch(settingsProvider);
    final envoyState = ref.watch(envoyMeshProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: ListView(
          children: [
            if (widget.coreService.isLoggedIn) ...[
              const Text('Profile picture', style: TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Row(
                children: [
                  CircleAvatar(
                    radius: 32,
                    backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                    backgroundImage: settings.avatarLoading
                        ? null
                        : (settings.myAvatarBytes != null && settings.myAvatarBytes!.isNotEmpty
                            ? MemoryImage(settings.myAvatarBytes!)
                            : null),
                    child: settings.avatarLoading
                        ? const Padding(padding: EdgeInsets.all(16), child: CircularProgressIndicator(strokeWidth: 2))
                        : (settings.myAvatarBytes == null || settings.myAvatarBytes!.isEmpty ? const Icon(Icons.person, size: 32) : null),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: settings.avatarUploading ? null : _uploadProfilePicture,
                      icon: settings.avatarUploading ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.photo_camera),
                      label: Text(settings.avatarUploading ? 'Uploading…' : 'Upload profile picture'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => ChangePasswordScreen(coreService: widget.coreService),
                    ),
                  );
                },
                icon: const Icon(Icons.lock),
                label: const Text('Change password'),
              ),
              const SizedBox(height: 24),
            ],
            const Text(
              'Core URL',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            TextField(
              controller: _urlController,
              decoration: const InputDecoration(
                hintText: 'http://127.0.0.1:9000',
                border: OutlineInputBorder(),
              ),
              keyboardType: TextInputType.url,
              autocorrect: false,
            ),
            const SizedBox(height: 16),
            const Text(
              'API Key (optional)',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            TextField(
              controller: _apiKeyController,
              decoration: const InputDecoration(
                hintText: 'Leave empty if Core auth is disabled',
                border: OutlineInputBorder(),
              ),
              obscureText: true,
              autocorrect: false,
            ),
            const SizedBox(height: 24),
            SwitchListTile(
              title: const Text('Show progress during long tasks'),
              subtitle: const Text(
                'When on, shows messages like "Generating your presentation…" while Core is working. Uses streaming (SSE); turn off for a simple loading bar.',
              ),
              value: widget.coreService.showProgressDuringLongTasks,
              onChanged: (bool value) async {
                await widget.coreService.saveShowProgressDuringLongTasks(value);
                if (mounted) setState(() {});
              },
            ),
            SwitchListTile(
              title: const Text('Bridge agent streaming preview'),
              subtitle: const Text(
                'For Cursor and Claude Code bridge chats: stream partial output while polling async results. Turn off if large streaming responses cause errors.',
              ),
              value: widget.coreService.bridgeAgentStreamPreview,
              onChanged: (bool value) async {
                await widget.coreService.saveBridgeAgentStreamPreview(value);
                if (mounted) setState(() {});
              },
            ),
            SwitchListTile(
              title: const Text('Cursor chat: plain text (copy-friendly)'),
              subtitle: const Text(
                'When on, Cursor friend replies are shown as plain selectable text instead of Markdown rendering.',
              ),
              value: widget.coreService.cursorChatPlainText,
              onChanged: (bool value) async {
                await widget.coreService.saveCursorChatPlainText(value);
                if (mounted) setState(() {});
              },
            ),
            SwitchListTile(
              title: const Text('VMPrint native preview (Companion)'),
              subtitle: const Text(
                'When on, VMPrint preview links open inside Companion WebView first. If unsupported, it falls back to system browser.',
              ),
              value: widget.coreService.vmprintNativePreview,
              onChanged: (bool value) async {
                await widget.coreService.saveVmprintNativePreview(value);
                if (mounted) setState(() {});
              },
            ),
            const SizedBox(height: 24),
            const Text(
              'Users are listed on the chat screen (from Core user.yml). Select a user to chat; each message is sent with that user\'s id.',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) => PermissionsScreen(
                      coreService: widget.coreService,
                      fromSettings: true,
                    ),
                  ),
                );
              },
              icon: const Icon(Icons.security),
              label: const Text('Review permissions'),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) => SkillsScreen(coreService: widget.coreService),
                  ),
                );
              },
              icon: const Icon(Icons.extension),
              label: const Text('Skills (search & install from Core)'),
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: () async {
                await Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) => ScanConnectScreen(
                      coreService: widget.coreService,
                      onSaved: () async {
                        await widget.coreService.loadSettings();
                        if (mounted) {
                          setState(() {
                            _urlController.text = widget.coreService.baseUrl;
                            _apiKeyController.text = widget.coreService.apiKey ?? '';
                          });
                        }
                      },
                    ),
                  ),
                );
                await widget.coreService.loadSettings();
                if (mounted) {
                  setState(() {
                    _urlController.text = widget.coreService.baseUrl;
                    _apiKeyController.text = widget.coreService.apiKey ?? '';
                  });
                }
              },
              icon: const Icon(Icons.qr_code_scanner),
              label: const Text('Scan QR to connect'),
            ),
            const SizedBox(height: 24),
            const Text(
              'Testing (clear data for a clean test)',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.tonal(
                  onPressed: () => _clearMemory(context),
                  child: const Text('Clear memory'),
                ),
                FilledButton.tonal(
                  onPressed: () => _clearKnowledgeBase(context),
                  child: const Text('Clear knowledge base'),
                ),
                FilledButton.tonal(
                  onPressed: () => _clearAllSkillsPlugins(context),
                  child: const Text('Clear all (skills & plugins)'),
                ),
                FilledButton.tonal(
                  onPressed: () => _clearChatHistories(context),
                  child: const Text('Clear chat histories (Hive)'),
                ),
              ],
            ),
            const SizedBox(height: 24),
            const Text(
              'Nodes URL (plugin for node registration)',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            TextField(
              controller: _nodesUrlController,
              decoration: const InputDecoration(
                hintText: 'http://127.0.0.1:3020',
                border: OutlineInputBorder(),
              ),
              keyboardType: TextInputType.url,
              autocorrect: false,
            ),
            const SizedBox(height: 8),
            const Text(
              'Node ID (when connecting as node)',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
            TextField(
              controller: _nodeIdController,
              decoration: const InputDecoration(
                hintText: 'companion',
                border: OutlineInputBorder(),
                isDense: true,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                if (widget.coreService.nodeService?.isConnected == true)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: Text(
                      'Connected as ${widget.coreService.nodeService?.nodeId ?? "?"}',
                      style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.primary),
                    ),
                  ),
                FilledButton(
                  onPressed: settings.nodeConnecting
                      ? null
                      : () async {
                          if (widget.coreService.nodeService?.isConnected == true) {
                            _settingsNotifier.setNodeConnecting(true);
                            await widget.coreService.disconnectNode();
                            _settingsNotifier.setNodeConnecting(false);
                            return;
                          }
                          final url = _nodesUrlController.text.trim();
                          final nodeId = _nodeIdController.text.trim().isEmpty ? 'companion' : _nodeIdController.text.trim();
                          if (url.isEmpty) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Enter Nodes URL')),
                            );
                            return;
                          }
                          final messenger = ScaffoldMessenger.of(context);
                          _settingsNotifier.setNodeConnecting(true);
                          try {
                            await widget.coreService.connectAsNode(nodesUrl: url, nodeId: nodeId);
                            _settingsNotifier.setNodeConnecting(false);
                            if (mounted) {
                              messenger.showSnackBar(
                                SnackBar(content: Text('Connected as $nodeId')),
                              );
                            }
                          } catch (e) {
                            _settingsNotifier.setNodeConnecting(false);
                            if (mounted) {
                              messenger.showSnackBar(
                                SnackBar(content: Text('Node connect failed: $e')),
                              );
                            }
                          }
                        },
                  child: Text(
                    widget.coreService.nodeService?.isConnected == true ? 'Disconnect node' : 'Connect as node',
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),
            const Text(
              'Canvas URL (for agent UI)',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            const Text(
              'Usually the homeclaw-browser plugin (different port than Core), e.g. http://host:3020/canvas. For remote access use a second tunnel or a reverse proxy; see docs/companion-app.md.',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _canvasUrlController,
              decoration: const InputDecoration(
                hintText: 'http://host:3020/canvas or leave empty',
                border: OutlineInputBorder(),
              ),
              keyboardType: TextInputType.url,
              autocorrect: false,
            ),
            const SizedBox(height: 24),
            const Text(
              'EnvoyMesh P2P',
              style: TextStyle(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            // Connection status indicator
            Row(
              children: [
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(
                    color: envoyState.isConnected
                        ? Colors.green
                        : envoyState.connectionStatus == RelayClientState.connecting
                            ? Colors.orange
                            : envoyState.connectionStatus == RelayClientState.error
                                ? Colors.red
                                : Colors.grey.shade400,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  envoyState.isConnected
                      ? 'Connected'
                      : envoyState.connectionStatus == RelayClientState.connecting
                          ? 'Connecting…'
                          : envoyState.connectionStatus == RelayClientState.error
                              ? 'Error${envoyState.error != null ? ': ${envoyState.error}' : ''}'
                              : 'Disconnected',
                  style: TextStyle(
                    color: envoyState.isConnected
                        ? Colors.green
                        : envoyState.connectionStatus == RelayClientState.error
                            ? Colors.red
                            : null,
                  ),
                ),
              ],
            ),
            if (_envoyPairedHint != null) ...[
              const SizedBox(height: 8),
              Text(
                _envoyPairedHint!,
                style: const TextStyle(fontSize: 12, color: Colors.grey),
              ),
            ],
            if (envoyState.initialized) ...[
              const SizedBox(height: 8),
              // Peer ID
              const Text('Peer ID', style: TextStyle(fontSize: 12, color: Colors.grey)),
              SelectableText(
                envoyState.peerId ?? '',
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
              ),
              const SizedBox(height: 4),
              // Owner ID
              const Text('Owner ID', style: TextStyle(fontSize: 12, color: Colors.grey)),
              SelectableText(
                envoyState.ownerId ?? '',
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
              ),
            ],
            const SizedBox(height: 12),
            // Home node URL
            const Text(
              'Home node WebSocket URL',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
            const SizedBox(height: 4),
            TextField(
              controller: _envoyUrlController,
              decoration: const InputDecoration(
                hintText: 'ws://192.168.1.100:3030/ws',
                border: OutlineInputBorder(),
                isDense: true,
              ),
              keyboardType: TextInputType.url,
              autocorrect: false,
            ),
            const SizedBox(height: 8),
            // Connect / Disconnect button
            Row(
              children: [
                FilledButton(
                  onPressed: envoyState.connectionStatus == RelayClientState.connecting
                      ? null
                      : () async {
                          final envoy = ref.read(envoyNodeServiceProvider);
                          if (envoyState.isConnected) {
                            await envoy.disconnect();
                            ref.read(envoyMeshProvider.notifier).setDisconnected();
                          } else {
                            final url = _envoyUrlController.text.trim();
                            if (url.isEmpty) {
                              if (mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(content: Text('Enter home node WebSocket URL')),
                                );
                              }
                              return;
                            }
                            ref.read(envoyMeshProvider.notifier).setConnecting();
                            try {
                              if (!envoy.isInitialized) {
                                await envoy.initialize();
                                ref.read(envoyMeshProvider.notifier).setInitialized(
                                  envoy.peerId!,
                                  envoy.ownerId!,
                                );
                              }
                              await envoy.connect(url);
                              ref.read(envoyMeshProvider.notifier).setConnected(url);
                              try {
                                ref.read(envoyMeshProvider.notifier).setLoadingContacts(true);
                                final contacts = await envoy.fetchP2PContacts();
                                ref.read(envoyMeshProvider.notifier).setContacts(contacts);
                              } catch (_) {
                                ref.read(envoyMeshProvider.notifier).setLoadingContacts(false);
                              }
                              if (mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(content: Text('Connected via EnvoyMesh P2P')),
                                );
                              }
                            } catch (e) {
                              ref.read(envoyMeshProvider.notifier).setError(e.toString());
                              if (mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(content: Text('Connect failed: $e')),
                                );
                              }
                            }
                          }
                        },
                  child: Text(
                    envoyState.isConnected ? 'Disconnect' : 'Connect',
                  ),
                ),
                const SizedBox(width: 12),
                OutlinedButton.icon(
                  onPressed: () {
                    Navigator.of(context)
                        .push(
                      MaterialPageRoute(
                        builder: (context) => EnvoyPairingScreen(
                          coreService: widget.coreService,
                        ),
                      ),
                    )
                        .then((_) {
                      if (mounted) unawaited(_loadEnvoyP2pFields());
                    });
                  },
                  icon: const Icon(Icons.qr_code_scanner, size: 18),
                  label: const Text('Scan QR to pair'),
                ),
              ],
            ),
            if (Platform.isMacOS || Platform.isWindows || Platform.isLinux) ...[
              const SizedBox(height: 24),
              const Text(
                'Exec allowlist (system run)',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 4),
              const Text(
                'Allowed commands: exact executable name (e.g. ls) or regex pattern (e.g. ^/usr/bin/.*). Desktop only.',
                style: TextStyle(fontSize: 12, color: Colors.grey),
              ),
              const SizedBox(height: 8),
              ...widget.coreService.execAllowlist.map((cmd) => ListTile(
                title: Text(cmd, style: const TextStyle(fontFamily: 'monospace')),
                trailing: IconButton(
                  icon: const Icon(Icons.remove_circle_outline),
                  onPressed: () => _removeExecCommand(cmd),
                ),
              )),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _execCommandController,
                      decoration: const InputDecoration(
                        hintText: 'e.g. ls, pwd',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                      onSubmitted: (_) => _addExecCommand(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: _addExecCommand,
                    child: const Text('Add'),
                  ),
                ],
              ),
              const SizedBox(height: 32),
            ],
            SafeArea(
              top: false,
              child: FilledButton(
                onPressed: _save,
                style: FilledButton.styleFrom(
                  minimumSize: const Size(double.infinity, 48),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
                child: const Text('Save'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
