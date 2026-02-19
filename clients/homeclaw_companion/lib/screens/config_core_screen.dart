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
  bool _resetMemory = false;
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

  void _applyCore(Map<String, dynamic> core) {
    _core = core;
    _nameController.text = _str(core['name']);
    _hostController.text = _str(core['host']).isEmpty ? '0.0.0.0' : _str(core['host']);
    _portController.text = core['port']?.toString() ?? '9000';
    _modeController.text = _str(core['mode']).isEmpty ? 'dev' : _str(core['mode']);
    _modelPathController.text = _str(core['model_path']);
    _mainLlmController.text = _str(core['main_llm']);
    _embeddingLlmController.text = _str(core['embedding_llm']);
    _mainLlmLanguageController.text = _listStr(core['main_llm_language']).join(', ');
    _llmMaxConcurrentController.text = _int(core['llm_max_concurrent']).toString();
    _memoryBackendController.text = _str(core['memory_backend']).isEmpty ? 'cognee' : _str(core['memory_backend']);
    _silent = _bool(core['silent']);
    _useMemory = core['use_memory'] != false;
    _resetMemory = _bool(core['reset_memory']);
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
    final body = <String, dynamic>{
      'name': _nameController.text.trim().isEmpty ? 'core' : _nameController.text.trim(),
      'host': _hostController.text.trim().isEmpty ? '0.0.0.0' : _hostController.text.trim(),
      'port': int.tryParse(_portController.text.trim()) ?? 9000,
      'mode': _modeController.text.trim().isEmpty ? 'dev' : _modeController.text.trim(),
      'model_path': _modelPathController.text.trim(),
      'main_llm': _mainLlmController.text.trim(),
      'embedding_llm': _embeddingLlmController.text.trim().isEmpty ? null : _embeddingLlmController.text.trim(),
      'main_llm_language': listFromComma(_mainLlmLanguageController.text),
      'llm_max_concurrent': int.tryParse(_llmMaxConcurrentController.text.trim()) ?? 2,
      'memory_backend': _memoryBackendController.text.trim().isEmpty ? 'cognee' : _memoryBackendController.text.trim(),
      'silent': _silent,
      'use_memory': _useMemory,
      'reset_memory': _resetMemory,
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
            _field('Main LLM (e.g. cloud_models/Gemini-2.5-Flash)', _mainLlmController),
            _field('Embedding LLM', _embeddingLlmController),
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
            CheckboxListTile(
              title: const Text('Reset memory'),
              value: _resetMemory,
              onChanged: (v) => setState(() => _resetMemory = v ?? false),
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
          _section('Profile', [
            CheckboxListTile(
              title: const Text('Profile enabled'),
              value: _profileEnabled,
              onChanged: (v) => setState(() => _profileEnabled = v ?? true),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
            _field('Profile dir', _profileDirController),
          ]),
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
