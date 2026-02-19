import 'package:flutter/material.dart';

import '../core_service.dart';

/// Manage Core config (core.yml) and users (user.yml) via Core's config API.
class ConfigCoreScreen extends StatefulWidget {
  final CoreService coreService;

  const ConfigCoreScreen({super.key, required this.coreService});

  @override
  State<ConfigCoreScreen> createState() => _ConfigCoreScreenState();
}

class _ConfigCoreScreenState extends State<ConfigCoreScreen> {
  List<Map<String, dynamic>> _users = [];
  bool _loading = true;
  String? _error;
  late TextEditingController _hostController;
  late TextEditingController _portController;
  late TextEditingController _modeController;
  late TextEditingController _mainLlmController;
  late TextEditingController _authApiKeyController;
  bool _silent = false;
  bool _useMemory = true;
  bool _authEnabled = false;

  @override
  void initState() {
    super.initState();
    _hostController = TextEditingController();
    _portController = TextEditingController();
    _modeController = TextEditingController();
    _mainLlmController = TextEditingController();
    _authApiKeyController = TextEditingController();
    _load();
  }

  @override
  void dispose() {
    _hostController.dispose();
    _portController.dispose();
    _modeController.dispose();
    _mainLlmController.dispose();
    _authApiKeyController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final core = await widget.coreService.getConfigCore();
      final users = await widget.coreService.getConfigUsers();
      if (!mounted) return;
      setState(() {
        _users = users;
        _hostController.text = (core['host'] as String?) ?? '0.0.0.0';
        _portController.text = (core['port']?.toString()) ?? '9000';
        _modeController.text = (core['mode'] as String?) ?? 'dev';
        _mainLlmController.text = (core['main_llm'] as String?) ?? '';
        _silent = core['silent'] == true;
        _useMemory = core['use_memory'] != false;
        _authEnabled = core['auth_enabled'] == true;
        _authApiKeyController.text = (core['auth_api_key'] as String?) == '***' ? '' : (core['auth_api_key'] as String? ?? '');
        _loading = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  Future<void> _saveCore() async {
    try {
      final body = <String, dynamic>{
        'host': _hostController.text.trim().isEmpty ? '0.0.0.0' : _hostController.text.trim(),
        'port': int.tryParse(_portController.text.trim()) ?? 9000,
        'mode': _modeController.text.trim().isEmpty ? 'dev' : _modeController.text.trim(),
        'main_llm': _mainLlmController.text.trim(),
        'silent': _silent,
        'use_memory': _useMemory,
        'auth_enabled': _authEnabled,
      };
      final key = _authApiKeyController.text.trim();
      if (key.isNotEmpty) body['auth_api_key'] = key;
      await widget.coreService.patchConfigCore(body);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Core config saved. Restart Core for host/port changes.')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Save failed: $e')));
      }
    }
  }

  Future<void> _addUser() async {
    final nameController = TextEditingController();
    final idController = TextEditingController();
    final imController = TextEditingController();
    final result = await showDialog<Map<String, String>>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add user'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: nameController,
                decoration: const InputDecoration(labelText: 'Name *', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: idController,
                decoration: const InputDecoration(labelText: 'ID (optional)', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: imController,
                decoration: const InputDecoration(
                  labelText: 'IM (e.g. matrix:@user:domain)',
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              final name = nameController.text.trim();
              if (name.isEmpty) return;
              Navigator.of(ctx).pop({
                'name': name,
                'id': idController.text.trim(),
                'im': imController.text.trim(),
              });
            },
            child: const Text('Add'),
          ),
        ],
      ),
    );
    if (result == null) return;
    final name = result['name'] ?? '';
    final id = result['id'] ?? '';
    final imStr = result['im'] ?? '';
    final im = imStr.isEmpty ? <String>[] : imStr.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
    try {
      await widget.coreService.addConfigUser({
        'name': name,
        if (id.isNotEmpty) 'id': id,
        'im': im,
        'email': [],
        'phone': [],
        'permissions': [],
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Added user: $name')));
        _load();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Add failed: $e')));
      }
    }
  }

  Future<void> _removeUser(String name) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Remove user'),
        content: Text('Remove user "$name"?'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text('Remove')),
        ],
      ),
    );
    if (confirm != true) return;
    try {
      await widget.coreService.removeConfigUser(name);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Removed: $name')));
        _load();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Remove failed: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: const Text('Config Core')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Config Core')),
        body: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              const SizedBox(height: 16),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: const Text('Config Core'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load, tooltip: 'Refresh'),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Core (core.yml)', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          const SizedBox(height: 8),
          TextField(
            controller: _hostController,
            decoration: const InputDecoration(labelText: 'Host', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _portController,
            decoration: const InputDecoration(labelText: 'Port', border: OutlineInputBorder()),
            keyboardType: TextInputType.number,
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _modeController,
            decoration: const InputDecoration(labelText: 'Mode', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _mainLlmController,
            decoration: const InputDecoration(labelText: 'Main LLM', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 8),
          CheckboxListTile(
            title: const Text('Silent (suppress component logs)'),
            value: _silent,
            onChanged: (v) => setState(() => _silent = v ?? false),
          ),
          CheckboxListTile(
            title: const Text('Use memory'),
            value: _useMemory,
            onChanged: (v) => setState(() => _useMemory = v ?? true),
          ),
          CheckboxListTile(
            title: const Text('Auth enabled (API key required)'),
            value: _authEnabled,
            onChanged: (v) => setState(() => _authEnabled = v ?? false),
          ),
          TextField(
            controller: _authApiKeyController,
            decoration: const InputDecoration(
              labelText: 'Auth API key (leave empty to keep current)',
              border: OutlineInputBorder(),
            ),
            obscureText: true,
          ),
          const SizedBox(height: 16),
          FilledButton(onPressed: _saveCore, child: const Text('Save Core config')),
          const SizedBox(height: 24),
          const Text('Users (user.yml)', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          const SizedBox(height: 8),
          ..._users.map((u) {
            final name = u['name'] as String? ?? '?';
            final id = u['id'] as String? ?? name;
            final im = (u['im'] as List<dynamic>?)?.join(', ') ?? '';
            return ListTile(
              title: Text(name),
              subtitle: Text('$id${im.isNotEmpty ? ' · $im' : ''}'),
              trailing: IconButton(
                icon: const Icon(Icons.remove_circle_outline),
                onPressed: () => _removeUser(name),
              ),
            );
          }),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: _addUser,
            icon: const Icon(Icons.add),
            label: const Text('Add user'),
          ),
        ],
      ),
    );
  }
}
