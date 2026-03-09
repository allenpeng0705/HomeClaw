import 'package:flutter/material.dart';
import '../core_service.dart';

/// Skills screen: list installed skills and search/install from ClawHub via Core API (Companion->Core direct, no Portal).
class SkillsScreen extends StatefulWidget {
  final CoreService coreService;

  const SkillsScreen({super.key, required this.coreService});

  @override
  State<SkillsScreen> createState() => _SkillsScreenState();
}

class _SkillsScreenState extends State<SkillsScreen> {
  List<Map<String, dynamic>> _installed = [];
  String _installedMsg = 'Loading…';
  bool _installedLoading = true;

  final TextEditingController _queryController = TextEditingController();
  List<Map<String, dynamic>> _searchResults = [];
  String _searchMsg = '';
  bool _searching = false;
  String? _installMsg;
  bool _installing = false;

  @override
  void initState() {
    super.initState();
    _loadInstalled();
  }

  @override
  void dispose() {
    _queryController.dispose();
    super.dispose();
  }

  Future<void> _loadInstalled() async {
    setState(() {
      _installedLoading = true;
      _installedMsg = 'Loading…';
    });
    try {
      final list = await widget.coreService.getSkillsList();
      if (mounted) {
        setState(() {
          _installed = list;
          _installedLoading = false;
          _installedMsg = '${list.length} skill(s) loaded.';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _installed = [];
          _installedLoading = false;
          _installedMsg = 'Failed to load: $e';
        });
      }
    }
  }

  Future<void> _search() async {
    final q = _queryController.text.trim();
    if (q.isEmpty) {
      setState(() {
        _searchMsg = 'Enter a search query.';
        _searchResults = [];
      });
      return;
    }
    setState(() {
      _searching = true;
      _searchMsg = 'Searching…';
      _searchResults = [];
    });
    try {
      final results = await widget.coreService.searchSkills(q);
      if (mounted) {
        setState(() {
          _searching = false;
          _searchMsg = 'Results: ${results.length}';
          _searchResults = results;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _searching = false;
          _searchMsg = 'Search error: $e';
          _searchResults = [];
        });
      }
    }
  }

  Future<void> _remove(String folder) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove skill'),
        content: Text('Remove skill "$folder"? This deletes the skill folder from external_skills. Built-in skills cannot be removed.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _installMsg = 'Removing…';
    });
    try {
      await widget.coreService.removeSkill(folder);
      if (mounted) {
        setState(() => _installMsg = 'Removed.');
        _loadInstalled();
      }
    } catch (e) {
      if (mounted) {
        setState(() => _installMsg = 'Remove failed: $e');
      }
    }
  }

  Future<void> _install(String id) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Install skill'),
        content: Text('Install and import "$id" from ClawHub?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Install'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _installing = true;
      _installMsg = 'Installing $id…';
    });
    try {
      final out = await widget.coreService.installSkill(id);
      if (mounted) {
        final convertOut = out['convert'];
        final output = convertOut is Map && convertOut['output'] != null
            ? convertOut['output'].toString()
            : '';
        setState(() {
          _installing = false;
          _installMsg = output.isNotEmpty ? 'Installed: $output' : 'Installed.';
        });
        _loadInstalled();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _installing = false;
          _installMsg = 'Install failed: $e';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Skills'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Installed skills',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            if (_installedLoading)
              const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator()))
            else
              Text(_installedMsg, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
            if (_installed.isNotEmpty) ...[
              const SizedBox(height: 8),
              ..._installed.map((s) {
                final folder = (s['folder'] ?? s['name'] ?? '').toString();
                final desc = (s['description'] ?? '').toString();
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              SelectableText(folder, style: const TextStyle(fontWeight: FontWeight.w600, fontFamily: 'monospace')),
                              if (desc.isNotEmpty)
                                Padding(
                                  padding: const EdgeInsets.only(top: 4),
                                  child: Text(desc, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                                ),
                            ],
                          ),
                        ),
                        FilledButton.tonal(
                          onPressed: _installing ? null : () => _remove(folder),
                          style: FilledButton.styleFrom(foregroundColor: Theme.of(context).colorScheme.error),
                          child: const Text('Remove'),
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ],
            const SizedBox(height: 24),
            const Text(
              'Import from ClawHub',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(
              'Search and install OpenClaw/ClawHub skills. Core must have clawhub on PATH.',
              style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _queryController,
                    decoration: const InputDecoration(
                      hintText: 'Search skills…',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                    onSubmitted: (_) => _search(),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: _searching ? null : _search,
                  child: _searching ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Search'),
                ),
              ],
            ),
            if (_searchMsg.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(_searchMsg, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
              ),
            if (_searchResults.isNotEmpty) ...[
              const SizedBox(height: 12),
              ..._searchResults.map((r) {
                final id = r['id'] ?? r['name'] ?? '';
                final desc = (r['description'] ?? '').toString();
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              SelectableText('$id', style: const TextStyle(fontWeight: FontWeight.w600, fontFamily: 'monospace')),
                              if (desc.isNotEmpty)
                                Padding(
                                  padding: const EdgeInsets.only(top: 4),
                                  child: Text(desc, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                                ),
                            ],
                          ),
                        ),
                        FilledButton.tonal(
                          onPressed: _installing ? null : () => _install(id.toString()),
                          child: const Text('Install'),
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ],
            if (_installMsg != null && _installMsg!.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 16),
                child: Text(
                  _installMsg!,
                  style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.primary),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
