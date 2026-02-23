import 'package:flutter/material.dart';

import '../core_service.dart';

/// Manage Core config (core.yml) and users (user.yml) via Core's config API.
/// All whitelisted core.yml keys are loadable/editable; sections match config structure.
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
  Map<String, dynamic> _core = {};

  // Server
  late TextEditingController _nameController;
  late TextEditingController _hostController;
  late TextEditingController _portController;
  late TextEditingController _modeController;
  late TextEditingController _modelPathController;
  // LLM
  late TextEditingController _mainLlmController;
  late TextEditingController _embeddingLlmController;
  late TextEditingController _mainLlmLanguageController;
  late TextEditingController _llmMaxConcurrentController;
  late TextEditingController _cloudModelApiKeyController;
  String? _selectedCloudModelId;
  String? _selectedLocalModelId;
  // Memory
  late TextEditingController _memoryBackendController;
  // Session
  late TextEditingController _sessionDmScopeController;
  late TextEditingController _sessionPruneKeepController;
  late TextEditingController _sessionIdleMinutesController;
  late TextEditingController _sessionDailyResetController;
  // Completion
  late TextEditingController _completionMaxTokensController;
  late TextEditingController _completionTempController;
  late TextEditingController _completionImageMaxDimController;
  // Profile
  late TextEditingController _profileDirController;
  // Skills / plugins
  late TextEditingController _skillsDirController;
  late TextEditingController _skillsMaxInPromptController;
  late TextEditingController _pluginsMaxInPromptController;
  late TextEditingController _systemPluginsController;
  // Tools
  late TextEditingController _toolsFileReadBaseController;
  late TextEditingController _toolsExecAllowlistController;
  late TextEditingController _toolsTimeoutController;
  // Result viewer
  late TextEditingController _resultViewerPortController;
  late TextEditingController _resultViewerBaseUrlController;
  // Auth
  late TextEditingController _authApiKeyController;

  bool _silent = false;
  bool _useMemory = true;
  bool _authEnabled = false;
  bool _sessionApiEnabled = true;
  bool _sessionPruneAfterTurn = false;
  bool _profileEnabled = true;
  bool _useSkills = true;
  bool _systemPluginsAutoStart = true;
  bool _resultViewerEnabled = true;
  bool _knowledgeBaseEnabled = true;
  bool _useWorkspaceBootstrap = true;
  bool _useAgentMemoryFile = true;
  bool _useAgentMemorySearch = true;
  bool _useDailyMemory = true;
  bool _orchestratorUnifiedWithTools = true;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController();
    _hostController = TextEditingController();
    _portController = TextEditingController();
    _modeController = TextEditingController();
    _modelPathController = TextEditingController();
    _mainLlmController = TextEditingController();
    _embeddingLlmController = TextEditingController();
    _mainLlmLanguageController = TextEditingController();
    _llmMaxConcurrentController = TextEditingController();
    _cloudModelApiKeyController = TextEditingController();
    _memoryBackendController = TextEditingController();
    _sessionDmScopeController = TextEditingController();
    _sessionPruneKeepController = TextEditingController();
    _sessionIdleMinutesController = TextEditingController();
    _sessionDailyResetController = TextEditingController();
    _completionMaxTokensController = TextEditingController();
    _completionTempController = TextEditingController();
    _completionImageMaxDimController = TextEditingController();
    _profileDirController = TextEditingController();
    _skillsDirController = TextEditingController();
    _skillsMaxInPromptController = TextEditingController();
    _pluginsMaxInPromptController = TextEditingController();
    _systemPluginsController = TextEditingController();
    _toolsFileReadBaseController = TextEditingController();
    _toolsExecAllowlistController = TextEditingController();
    _toolsTimeoutController = TextEditingController();
    _resultViewerPortController = TextEditingController();
    _resultViewerBaseUrlController = TextEditingController();
    _authApiKeyController = TextEditingController();
    _load();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _hostController.dispose();
    _portController.dispose();
    _modeController.dispose();
    _modelPathController.dispose();
    _mainLlmController.dispose();
    _embeddingLlmController.dispose();
    _mainLlmLanguageController.dispose();
    _llmMaxConcurrentController.dispose();
    _cloudModelApiKeyController.dispose();
    _memoryBackendController.dispose();
    _sessionDmScopeController.dispose();
    _sessionPruneKeepController.dispose();
    _sessionIdleMinutesController.dispose();
    _sessionDailyResetController.dispose();
    _completionMaxTokensController.dispose();
    _completionTempController.dispose();
    _completionImageMaxDimController.dispose();
    _profileDirController.dispose();
    _skillsDirController.dispose();
    _skillsMaxInPromptController.dispose();
    _pluginsMaxInPromptController.dispose();
    _systemPluginsController.dispose();
    _toolsFileReadBaseController.dispose();
    _toolsExecAllowlistController.dispose();
    _toolsTimeoutController.dispose();
    _resultViewerPortController.dispose();
    _resultViewerBaseUrlController.dispose();
    _authApiKeyController.dispose();
    super.dispose();
  }

  static String _str(dynamic v) => v?.toString() ?? '';
  static bool _bool(dynamic v) => v == true;
  static int _int(dynamic v) {
    if (v == null) return 0;
    if (v is int) return v;
    return int.tryParse(v.toString()) ?? 0;
  }

  static List<String> _listStr(dynamic v) {
    if (v == null) return [];
    if (v is List) return v.map((e) => e.toString()).toList();
    return [];
  }

  List<Map<String, dynamic>> _cloudModelsList() {
    final list = _core['cloud_models'];
    if (list == null || list is! List) return [];
    return list.map((e) => Map<String, dynamic>.from(e is Map ? e : {})).toList();
  }

  List<Map<String, dynamic>> _localChatModelsList() {
    final list = _core['local_models'];
    if (list == null || list is! List) return [];
    return list.map((e) {
      final m = Map<String, dynamic>.from(e is Map ? e : {});
      final caps = m['capabilities'];
      final hasChat = caps is List && caps.any((c) => c.toString().toLowerCase().contains('chat'));
      return hasChat ? m : null;
    }).whereType<Map<String, dynamic>>().toList();
  }

  void _applyCore(Map<String, dynamic> core) {
    _core = core;
    _nameController.text = _str(core['name']);
    _hostController.text = _str(core['host']).isEmpty ? '0.0.0.0' : _str(core['host']);
    _portController.text = core['port']?.toString() ?? '9000';
    _modeController.text = _str(core['mode']).isEmpty ? 'dev' : _str(core['mode']);
    _modelPathController.text = _str(core['model_path']);
    final mainLlm = _str(core['main_llm']);
    _mainLlmController.text = mainLlm;
    if (mainLlm.startsWith('cloud_models/')) {
      _selectedCloudModelId = mainLlm.substring('cloud_models/'.length);
      _selectedLocalModelId = null;
    } else if (mainLlm.startsWith('local_models/')) {
      _selectedLocalModelId = mainLlm.substring('local_models/'.length);
      _selectedCloudModelId = null;
    } else {
      _selectedCloudModelId = null;
      _selectedLocalModelId = null;
    }
    _cloudModelApiKeyController.clear();
    _embeddingLlmController.text = _str(core['embedding_llm']);
    _mainLlmLanguageController.text = _listStr(core['main_llm_language']).join(', ');
    _llmMaxConcurrentController.text = _int(core['llm_max_concurrent']).toString();
    _memoryBackendController.text = _str(core['memory_backend']).isEmpty ? 'cognee' : _str(core['memory_backend']);
    _silent = _bool(core['silent']);
    _useMemory = core['use_memory'] != false;
    _authEnabled = _bool(core['auth_enabled']);
    _authApiKeyController.text = (core['auth_api_key'] == '***' || core['auth_api_key'] == null) ? '' : _str(core['auth_api_key']);

    final session = core['session'] as Map<String, dynamic>? ?? {};
    _sessionDmScopeController.text = _str(session['dm_scope']).isEmpty ? 'main' : _str(session['dm_scope']);
    _sessionApiEnabled = session['api_enabled'] != false;
    _sessionPruneKeepController.text = _int(session['prune_keep_last_n']).toString();
    if (_sessionPruneKeepController.text == '0') _sessionPruneKeepController.text = '50';
    _sessionPruneAfterTurn = _bool(session['prune_after_turn']);
    _sessionIdleMinutesController.text = _int(session['idle_minutes']).toString();
    if (_sessionIdleMinutesController.text == '0') _sessionIdleMinutesController.text = '-1';
    _sessionDailyResetController.text = _int(session['daily_reset_at_hour']).toString();
    if (_sessionDailyResetController.text == '0') _sessionDailyResetController.text = '-1';

    final completion = core['completion'] as Map<String, dynamic>? ?? {};
    _completionMaxTokensController.text = _int(completion['max_tokens']).toString();
    if (_completionMaxTokensController.text == '0') _completionMaxTokensController.text = '8192';
    _completionTempController.text = (completion['temperature'] ?? 0.7).toString();
    _completionImageMaxDimController.text = _int(completion['image_max_dimension']).toString();
    if (_completionImageMaxDimController.text == '0') _completionImageMaxDimController.text = '512';

    final profile = core['profile'] as Map<String, dynamic>? ?? {};
    _profileEnabled = profile['enabled'] != false;
    _profileDirController.text = _str(profile['dir']);

    _useSkills = core['use_skills'] != false;
    _skillsDirController.text = _str(core['skills_dir']).isEmpty ? 'config/skills' : _str(core['skills_dir']);
    _skillsMaxInPromptController.text = _int(core['skills_max_in_prompt']).toString();
    if (_skillsMaxInPromptController.text == '0') _skillsMaxInPromptController.text = '5';
    _pluginsMaxInPromptController.text = _int(core['plugins_max_in_prompt']).toString();
    if (_pluginsMaxInPromptController.text == '0') _pluginsMaxInPromptController.text = '5';
    _systemPluginsAutoStart = core['system_plugins_auto_start'] != false;
    _systemPluginsController.text = _listStr(core['system_plugins']).join(', ');
    _useWorkspaceBootstrap = core['use_workspace_bootstrap'] != false;
    _useAgentMemoryFile = core['use_agent_memory_file'] != false;
    _useAgentMemorySearch = core['use_agent_memory_search'] != false;
    _useDailyMemory = core['use_daily_memory'] != false;
    _orchestratorUnifiedWithTools = core['orchestrator_unified_with_tools'] != false;

    final tools = core['tools'] as Map<String, dynamic>? ?? {};
    _toolsFileReadBaseController.text = _str(tools['file_read_base']).isEmpty ? '.' : _str(tools['file_read_base']);
    _toolsExecAllowlistController.text = _listStr(tools['exec_allowlist']).join(', ');
    _toolsTimeoutController.text = _int(tools['tool_timeout_seconds']).toString();

    final resultViewer = core['result_viewer'] as Map<String, dynamic>? ?? {};
    _resultViewerEnabled = resultViewer['enabled'] != false;
    _resultViewerPortController.text = _int(resultViewer['port']).toString();
    if (_resultViewerPortController.text == '0') _resultViewerPortController.text = '9001';
    _resultViewerBaseUrlController.text = _str(resultViewer['base_url']);

    final kb = core['knowledge_base'] as Map<String, dynamic>? ?? {};
    _knowledgeBaseEnabled = kb['enabled'] != false;
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
        _applyCore(core);
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

  Map<String, dynamic> _buildPatchBody() {
    final listFromComma = (String s) =>
        s.trim().isEmpty ? <String>[] : s.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
    String mainLlm = _mainLlmController.text.trim();
    if (_selectedCloudModelId != null) {
      mainLlm = 'cloud_models/$_selectedCloudModelId';
    } else if (_selectedLocalModelId != null) {
      mainLlm = 'local_models/$_selectedLocalModelId';
    }
    final body = <String, dynamic>{
      'name': _nameController.text.trim().isEmpty ? 'core' : _nameController.text.trim(),
      'host': _hostController.text.trim().isEmpty ? '0.0.0.0' : _hostController.text.trim(),
      'port': int.tryParse(_portController.text.trim()) ?? 9000,
      'mode': _modeController.text.trim().isEmpty ? 'dev' : _modeController.text.trim(),
      'model_path': _modelPathController.text.trim(),
      'main_llm': mainLlm,
      'embedding_llm': _embeddingLlmController.text.trim().isEmpty ? null : _embeddingLlmController.text.trim(),
      'main_llm_language': listFromComma(_mainLlmLanguageController.text),
      'llm_max_concurrent': int.tryParse(_llmMaxConcurrentController.text.trim()) ?? 2,
      'memory_backend': _memoryBackendController.text.trim().isEmpty ? 'cognee' : _memoryBackendController.text.trim(),
      'silent': _silent,
      'use_memory': _useMemory,
      'auth_enabled': _authEnabled,
      'use_skills': _useSkills,
      'skills_dir': _skillsDirController.text.trim(),
      'skills_max_in_prompt': int.tryParse(_skillsMaxInPromptController.text.trim()) ?? 5,
      'plugins_max_in_prompt': int.tryParse(_pluginsMaxInPromptController.text.trim()) ?? 5,
      'system_plugins_auto_start': _systemPluginsAutoStart,
      'system_plugins': listFromComma(_systemPluginsController.text),
      'use_workspace_bootstrap': _useWorkspaceBootstrap,
      'use_agent_memory_file': _useAgentMemoryFile,
      'use_agent_memory_search': _useAgentMemorySearch,
      'use_daily_memory': _useDailyMemory,
      'orchestrator_unified_with_tools': _orchestratorUnifiedWithTools,
      'session': <String, dynamic>{
        'dm_scope': _sessionDmScopeController.text.trim().isEmpty ? 'main' : _sessionDmScopeController.text.trim(),
        'api_enabled': _sessionApiEnabled,
        'prune_keep_last_n': int.tryParse(_sessionPruneKeepController.text.trim()) ?? 50,
        'prune_after_turn': _sessionPruneAfterTurn,
        'idle_minutes': int.tryParse(_sessionIdleMinutesController.text.trim()) ?? -1,
        'daily_reset_at_hour': int.tryParse(_sessionDailyResetController.text.trim()) ?? -1,
      },
      'completion': <String, dynamic>{
        'max_tokens': int.tryParse(_completionMaxTokensController.text.trim()) ?? 8192,
        'temperature': double.tryParse(_completionTempController.text.trim()) ?? 0.7,
        'image_max_dimension': int.tryParse(_completionImageMaxDimController.text.trim()) ?? 512,
      },
      'profile': <String, dynamic>{
        'enabled': _profileEnabled,
        'dir': _profileDirController.text.trim(),
      },
      'tools': <String, dynamic>{
        'file_read_base': _toolsFileReadBaseController.text.trim().isEmpty ? '.' : _toolsFileReadBaseController.text.trim(),
        'exec_allowlist': listFromComma(_toolsExecAllowlistController.text),
        'tool_timeout_seconds': int.tryParse(_toolsTimeoutController.text.trim()) ?? 0,
      },
      'result_viewer': <String, dynamic>{
        'enabled': _resultViewerEnabled,
        'port': int.tryParse(_resultViewerPortController.text.trim()) ?? 9001,
        'base_url': _resultViewerBaseUrlController.text.trim(),
      },
      'knowledge_base': <String, dynamic>{
        'enabled': _knowledgeBaseEnabled,
      },
    };
    body.removeWhere((k, v) => v == null);
    final key = _authApiKeyController.text.trim();
    if (key.isNotEmpty) body['auth_api_key'] = key;
    if (_selectedCloudModelId != null && _cloudModelApiKeyController.text.trim().isNotEmpty) {
      final cloudList = _cloudModelsList();
      final patched = cloudList.map((m) {
        final copy = Map<String, dynamic>.from(m);
        copy['api_key'] = (m['id'] == _selectedCloudModelId)
            ? _cloudModelApiKeyController.text.trim()
            : '***';
        return copy;
      }).toList();
      body['cloud_models'] = patched;
    }
    return body;
  }

  Future<void> _saveCore() async {
    try {
      final body = _buildPatchBody();
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
    final emailController = TextEditingController();
    final imController = TextEditingController();
    final phoneController = TextEditingController();
    final permissionsController = TextEditingController();
    final result = await showDialog<Map<String, dynamic>>(
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
                controller: emailController,
                decoration: const InputDecoration(
                  labelText: 'Email (comma-separated)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: imController,
                decoration: const InputDecoration(
                  labelText: 'IM (e.g. matrix:@user:domain, comma-separated)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: phoneController,
                decoration: const InputDecoration(
                  labelText: 'Phone (comma-separated)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: permissionsController,
                decoration: const InputDecoration(
                  labelText: 'Permissions (comma-separated)',
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
              final listFromComma = (String s) =>
                  s.trim().isEmpty ? <String>[] : s.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
              Navigator.of(ctx).pop({
                'name': name,
                'id': idController.text.trim().isEmpty ? name : idController.text.trim(),
                'email': listFromComma(emailController.text),
                'im': listFromComma(imController.text),
                'phone': listFromComma(phoneController.text),
                'permissions': listFromComma(permissionsController.text),
              });
            },
            child: const Text('Add'),
          ),
        ],
      ),
    );
    if (result == null) return;
    final name = result['name'] as String? ?? '';
    final id = (result['id'] as String?)?.trim().isEmpty == true ? name : (result['id'] as String?)?.trim() ?? name;
    final email = result['email'] is List ? List<String>.from(result['email'] as List) : [];
    final im = result['im'] is List ? List<String>.from(result['im'] as List) : [];
    final phone = result['phone'] is List ? List<String>.from(result['phone'] as List) : [];
    final permissions = result['permissions'] is List ? List<String>.from(result['permissions'] as List) : [];
    try {
      await widget.coreService.addConfigUser({
        'name': name,
        'id': id,
        'email': email,
        'im': im,
        'phone': phone,
        'permissions': permissions,
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

  Future<void> _editUser(Map<String, dynamic> u) async {
    final name = u['name'] as String? ?? '?';
    final id = u['id'] as String? ?? name;
    final emailList = u['email'] as List<dynamic>? ?? [];
    final imList = u['im'] as List<dynamic>? ?? [];
    final phoneList = u['phone'] as List<dynamic>? ?? [];
    final permList = u['permissions'] as List<dynamic>? ?? [];
    final nameController = TextEditingController(text: name);
    final idController = TextEditingController(text: id);
    final emailController = TextEditingController(text: emailList.map((e) => e.toString()).join(', '));
    final imController = TextEditingController(text: imList.map((e) => e.toString()).join(', '));
    final phoneController = TextEditingController(text: phoneList.map((e) => e.toString()).join(', '));
    final permissionsController = TextEditingController(text: permList.map((e) => e.toString()).join(', '));
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit user'),
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
                decoration: const InputDecoration(labelText: 'ID (system user id)', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: emailController,
                decoration: const InputDecoration(
                  labelText: 'Email (comma-separated)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: imController,
                decoration: const InputDecoration(
                  labelText: 'IM (e.g. matrix:@user:domain, comma-separated)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: phoneController,
                decoration: const InputDecoration(
                  labelText: 'Phone (comma-separated)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: permissionsController,
                decoration: const InputDecoration(
                  labelText: 'Permissions (comma-separated, e.g. IM, EMAIL, PHONE)',
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
              final newName = nameController.text.trim();
              if (newName.isEmpty) return;
              final listFromComma = (String s) =>
                  s.trim().isEmpty ? <String>[] : s.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
              Navigator.of(ctx).pop({
                'name': newName,
                'id': idController.text.trim().isEmpty ? newName : idController.text.trim(),
                'email': listFromComma(emailController.text),
                'im': listFromComma(imController.text),
                'phone': listFromComma(phoneController.text),
                'permissions': listFromComma(permissionsController.text),
              });
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (result == null) return;
    try {
      await widget.coreService.patchConfigUser(name, result);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Updated: ${result['name']}')));
        _load();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Update failed: $e')));
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

  Widget _section(String title, List<Widget> children) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 8),
        Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
        const SizedBox(height: 6),
        ...children,
      ],
    );
  }

  Widget _field(String label, TextEditingController c, {TextInputType? keyboardType}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: TextField(
        controller: c,
        decoration: InputDecoration(labelText: label, border: const OutlineInputBorder(), isDense: true),
        keyboardType: keyboardType,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: const Text('Manage Core')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Manage Core')),
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
        title: const Text('Manage Core'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load, tooltip: 'Refresh'),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _section('Server (core.yml)', [
            _field('Name', _nameController),
            _field('Host', _hostController),
            _field('Port', _portController, keyboardType: TextInputType.number),
            _field('Mode', _modeController),
            _field('Model path', _modelPathController),
          ]),
          _section('LLM', [
            const Text(
              'Main model: choose one from cloud or local. Both can work together later for better capability and cost.',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
            const SizedBox(height: 12),
            const Text('Cloud models', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 12)),
            const SizedBox(height: 4),
            ..._cloudModelsList().map((m) {
              final id = m['id'] as String? ?? '';
              final alias = m['alias'] as String? ?? id;
              return RadioListTile<String>(
                title: Text(alias),
                subtitle: id != alias ? Text(id, style: const TextStyle(fontSize: 11, color: Colors.grey)) : null,
                value: id,
                groupValue: _selectedCloudModelId,
                onChanged: (v) => setState(() {
                  _selectedCloudModelId = v;
                  _selectedLocalModelId = null;
                  _mainLlmController.text = v != null ? 'cloud_models/$v' : _mainLlmController.text;
                }),
              );
            }),
            if (_selectedCloudModelId != null) ...[
              const SizedBox(height: 4),
              TextField(
                controller: _cloudModelApiKeyController,
                decoration: const InputDecoration(
                  labelText: 'API key (leave empty to keep current)',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                obscureText: true,
                autocorrect: false,
              ),
            ],
            const SizedBox(height: 12),
            const Text('Local models', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 12)),
            const SizedBox(height: 4),
            ..._localChatModelsList().map((m) {
              final id = m['id'] as String? ?? '';
              final alias = m['alias'] as String? ?? id;
              return RadioListTile<String>(
                title: Text(alias),
                subtitle: id != alias ? Text(id, style: const TextStyle(fontSize: 11, color: Colors.grey)) : null,
                value: id,
                groupValue: _selectedLocalModelId,
                onChanged: (v) => setState(() {
                  _selectedLocalModelId = v;
                  _selectedCloudModelId = null;
                  _mainLlmController.text = v != null ? 'local_models/$v' : _mainLlmController.text;
                }),
              );
            }),
            const SizedBox(height: 12),
            const Text('Embedding model (read-only)', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 12)),
            const SizedBox(height: 4),
            ListTile(
              title: Text(_embeddingLlmController.text.isEmpty ? '—' : _embeddingLlmController.text),
              dense: true,
            ),
            _field('Main LLM language (comma-separated)', _mainLlmLanguageController),
            _field('LLM max concurrent', _llmMaxConcurrentController, keyboardType: TextInputType.number),
          ]),
          _section('Memory', [
            CheckboxListTile(
              title: const Text('Use memory'),
              value: _useMemory,
              onChanged: (v) => setState(() => _useMemory = v ?? true),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            _field('Memory backend (cognee | chroma)', _memoryBackendController),
          ]),
          _section('Session', [
            _field('DM scope (main | per-peer | per-channel-peer)', _sessionDmScopeController),
            _field('Prune keep last N', _sessionPruneKeepController, keyboardType: TextInputType.number),
            _field('Idle minutes (-1 = disabled)', _sessionIdleMinutesController, keyboardType: TextInputType.number),
            _field('Daily reset at hour (0-23, -1 = disabled)', _sessionDailyResetController, keyboardType: TextInputType.number),
            CheckboxListTile(
              title: const Text('Session API enabled'),
              value: _sessionApiEnabled,
              onChanged: (v) => setState(() => _sessionApiEnabled = v ?? true),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            CheckboxListTile(
              title: const Text('Prune after each turn'),
              value: _sessionPruneAfterTurn,
              onChanged: (v) => setState(() => _sessionPruneAfterTurn = v ?? false),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
          ]),
          _section('Completion', [
            _field('Max tokens', _completionMaxTokensController, keyboardType: TextInputType.number),
            _field('Temperature', _completionTempController),
            _field('Image max dimension (0 = no resize)', _completionImageMaxDimController, keyboardType: TextInputType.number),
          ]),
          // Profile section hidden (learned by LLM; do not expose in settings)
          _section('Skills & plugins', [
            CheckboxListTile(
              title: const Text('Use skills'),
              value: _useSkills,
              onChanged: (v) => setState(() => _useSkills = v ?? true),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            _field('Skills dir', _skillsDirController),
            _field('Skills max in prompt', _skillsMaxInPromptController, keyboardType: TextInputType.number),
            _field('Plugins max in prompt', _pluginsMaxInPromptController, keyboardType: TextInputType.number),
            CheckboxListTile(
              title: const Text('System plugins auto start'),
              value: _systemPluginsAutoStart,
              onChanged: (v) => setState(() => _systemPluginsAutoStart = v ?? true),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            _field('System plugins (comma-separated)', _systemPluginsController),
            CheckboxListTile(
              title: const Text('Use workspace bootstrap'),
              value: _useWorkspaceBootstrap,
              onChanged: (v) => setState(() => _useWorkspaceBootstrap = v ?? true),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            CheckboxListTile(
              title: const Text('Use agent memory file'),
              value: _useAgentMemoryFile,
              onChanged: (v) => setState(() => _useAgentMemoryFile = v ?? true),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            CheckboxListTile(
              title: const Text('Use agent memory search'),
              value: _useAgentMemorySearch,
              onChanged: (v) => setState(() => _useAgentMemorySearch = v ?? true),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            CheckboxListTile(
              title: const Text('Use daily memory'),
              value: _useDailyMemory,
              onChanged: (v) => setState(() => _useDailyMemory = v ?? true),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            CheckboxListTile(
              title: const Text('Orchestrator unified with tools'),
              value: _orchestratorUnifiedWithTools,
              onChanged: (v) => setState(() => _orchestratorUnifiedWithTools = v ?? true),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
          ]),
          _section('Tools', [
            _field('File read base path', _toolsFileReadBaseController),
            _field('Exec allowlist (comma-separated)', _toolsExecAllowlistController),
            _field('Tool timeout seconds (0 = no timeout)', _toolsTimeoutController, keyboardType: TextInputType.number),
          ]),
          _section('Result viewer', [
            CheckboxListTile(
              title: const Text('Result viewer enabled'),
              value: _resultViewerEnabled,
              onChanged: (v) => setState(() => _resultViewerEnabled = v ?? true),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            _field('Result viewer port', _resultViewerPortController, keyboardType: TextInputType.number),
            _field('Result viewer base URL', _resultViewerBaseUrlController),
          ]),
          _section('Knowledge base', [
            CheckboxListTile(
              title: const Text('Knowledge base enabled'),
              value: _knowledgeBaseEnabled,
              onChanged: (v) => setState(() => _knowledgeBaseEnabled = v ?? true),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
          ]),
          _section('Logging & auth', [
            CheckboxListTile(
              title: const Text('Silent (suppress component logs)'),
              value: _silent,
              onChanged: (v) => setState(() => _silent = v ?? false),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            CheckboxListTile(
              title: const Text('Auth enabled (API key required)'),
              value: _authEnabled,
              onChanged: (v) => setState(() => _authEnabled = v ?? false),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            TextField(
              controller: _authApiKeyController,
              decoration: const InputDecoration(
                labelText: 'Auth API key (leave empty to keep current)',
                border: OutlineInputBorder(),
                isDense: true,
              ),
              obscureText: true,
            ),
          ]),
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
              onTap: () => _editUser(u),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    icon: const Icon(Icons.edit_outlined),
                    onPressed: () => _editUser(u),
                    tooltip: 'Edit user',
                  ),
                  IconButton(
                    icon: const Icon(Icons.remove_circle_outline),
                    onPressed: () => _removeUser(name),
                    tooltip: 'Remove user',
                  ),
                ],
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
