import 'package:flutter/material.dart';
import '../core_service.dart';
import 'config_core_screen.dart';
import 'permissions_screen.dart';
import 'scan_connect_screen.dart';

class SettingsScreen extends StatefulWidget {
  final CoreService coreService;

  const SettingsScreen({super.key, required this.coreService});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController _urlController;
  late TextEditingController _apiKeyController;
  late TextEditingController _canvasUrlController;
  late TextEditingController _nodesUrlController;
  late TextEditingController _nodeIdController;
  late TextEditingController _execCommandController;
  bool _nodeConnecting = false;

  @override
  void initState() {
    super.initState();
    _urlController = TextEditingController(text: widget.coreService.baseUrl);
    _apiKeyController = TextEditingController(text: widget.coreService.apiKey ?? '');
    _canvasUrlController = TextEditingController(text: widget.coreService.canvasUrl ?? '');
    _nodesUrlController = TextEditingController(text: widget.coreService.nodesUrl ?? 'http://127.0.0.1:3020');
    _nodeIdController = TextEditingController(text: 'companion');
    _execCommandController = TextEditingController();
  }

  @override
  void dispose() {
    _urlController.dispose();
    _apiKeyController.dispose();
    _canvasUrlController.dispose();
    _nodesUrlController.dispose();
    _nodeIdController.dispose();
    _execCommandController.dispose();
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
    if (mounted) setState(() {});
  }

  Future<void> _removeExecCommand(String cmd) async {
    final list = widget.coreService.execAllowlist.where((c) => c != cmd).toList();
    await widget.coreService.saveExecAllowlist(list);
    if (mounted) setState(() {});
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: ListView(
          children: [
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
            FilledButton(
              onPressed: _save,
              child: const Text('Save'),
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) => ConfigCoreScreen(coreService: widget.coreService),
                  ),
                );
              },
              icon: const Icon(Icons.tune),
              label: const Text('Manage Core (core.yml & user.yml)'),
            ),
            const SizedBox(height: 8),
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
                  onPressed: _nodeConnecting
                      ? null
                      : () async {
                          if (widget.coreService.nodeService?.isConnected == true) {
                            setState(() => _nodeConnecting = true);
                            await widget.coreService.disconnectNode();
                            if (mounted) setState(() => _nodeConnecting = false);
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
                          setState(() => _nodeConnecting = true);
                          try {
                            await widget.coreService.connectAsNode(nodesUrl: url, nodeId: nodeId);
                            if (mounted) {
                              setState(() => _nodeConnecting = false);
                              messenger.showSnackBar(
                                SnackBar(content: Text('Connected as $nodeId')),
                              );
                            }
                          } catch (e) {
                            if (mounted) {
                              setState(() => _nodeConnecting = false);
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
            TextField(
              controller: _canvasUrlController,
              decoration: const InputDecoration(
                hintText: 'https://... or leave empty',
                border: OutlineInputBorder(),
              ),
              keyboardType: TextInputType.url,
              autocorrect: false,
            ),
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
          ],
        ),
      ),
    );
  }
}
