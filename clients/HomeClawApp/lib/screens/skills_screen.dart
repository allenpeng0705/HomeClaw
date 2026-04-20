import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import '../core_service.dart';
import '../providers/skills_providers.dart';

/// Skills screen: list installed skills and search/install from ClawHub via Core API (Companion->Core direct, no Portal).
class SkillsScreen extends ConsumerStatefulWidget {
  final CoreService coreService;

  const SkillsScreen({super.key, required this.coreService});

  @override
  ConsumerState<SkillsScreen> createState() => _SkillsScreenState();
}

class _SkillsScreenState extends ConsumerState<SkillsScreen> {
  late final InstalledSkillsNotifier _installedNotifier;
  late final SearchSkillsNotifier _searchNotifier;
  late final ClawhubLoginNotifier _clawhubNotifier;
  late final InstallStateNotifier _installNotifier;
  late final TextEditingController _queryController;
  late final TextEditingController _tokenController;

  @override
  void initState() {
    super.initState();
    _installedNotifier = ref.read(installedSkillsProvider.notifier);
    _searchNotifier = ref.read(searchSkillsProvider.notifier);
    _clawhubNotifier = ref.read(clawhubLoginProvider.notifier);
    _installNotifier = ref.read(installStateProvider.notifier);
    _queryController = TextEditingController();
    _tokenController = TextEditingController();
    _loadInstalled();
    _loadClawhubLoginStatus();
  }

  @override
  void dispose() {
    _queryController.dispose();
    _tokenController.dispose();
    super.dispose();
  }

  Future<void> _loadClawhubLoginStatus() async {
    _clawhubNotifier.setStatusLoading(true);
    try {
      final status = await widget.coreService.getClawhubLoginStatus();
      if (mounted) {
        _clawhubNotifier.setStatus(
          loggedIn: status['logged_in'] == true,
          message: (status['message'] ?? '').toString().isEmpty
              ? (status['clawhub_available'] == false ? 'clawhub not found on PATH' : '')
              : (status['message'] ?? '').toString(),
        );
      }
    } catch (_) {
      if (mounted) _clawhubNotifier.setStatusError('Could not check status');
    }
  }

  Future<void> _startClawhubLogin() async {
    _clawhubNotifier.setLoginInProgress(true);
    try {
      final result = await widget.coreService.clawhubLogin();
      if (mounted) {
        final u = result['url'];
        final url = (u is String && u.trim().isNotEmpty) ? u.trim() : null;
        _clawhubNotifier.setLoginResult(url: url, message: (result['message'] ?? '').toString());
        if (result['ok'] == true && url == null) _loadClawhubLoginStatus();
      }
    } catch (e) {
      if (mounted) {
        final msg = e.toString().replaceFirst(RegExp(r'^Exception:\s*'), '');
        _clawhubNotifier.setLoginResult(message: msg.isNotEmpty ? msg : 'Login request failed');
      }
    }
  }

  Future<void> _startClawhubTokenLogin() async {
    final token = _tokenController.text.trim();
    if (token.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Paste your ClawHub token first')));
      return;
    }
    _clawhubNotifier.setTokenLoginInProgress(true);
    try {
      final result = await widget.coreService.clawhubLoginWithToken(token);
      if (mounted) {
        _clawhubNotifier.setTokenLoginResult(message: (result['message'] ?? '').toString());
        if (result['ok'] == true) {
          _tokenController.clear();
          _loadClawhubLoginStatus();
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Logged in with token')));
        }
      }
    } catch (e) {
      if (mounted) {
        final msg = e.toString().replaceFirst(RegExp(r'^Exception:\s*'), '');
        _clawhubNotifier.setTokenLoginResult(message: msg);
      }
    }
  }

  Future<void> _loadInstalled() async {
    _installedNotifier.setLoading();
    try {
      final list = await widget.coreService.getSkillsList();
      _installedNotifier.setLoaded(list);
    } catch (e) {
      _installedNotifier.setError('Failed to load: $e');
    }
  }

  Future<void> _search() async {
    final q = _queryController.text.trim();
    if (q.isEmpty) {
      _searchNotifier.setEmptyQuery('Enter a search query.');
      return;
    }
    _searchNotifier.setSearching(q);
    try {
      final results = await widget.coreService.searchSkills(q);
      _searchNotifier.setResults(results);
    } catch (e) {
      final msg = e.toString().replaceFirst(RegExp(r'^Exception:\s*'), '');
      _searchNotifier.setError(msg.isNotEmpty ? 'Search error: $msg' : 'Search failed.');
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
    _installNotifier.setRemoving(folder);
    try {
      await widget.coreService.removeSkill(folder);
      _installNotifier.setSuccess('Removed.');
      _loadInstalled();
    } catch (e) {
      _installNotifier.setError('Remove failed: $e');
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
    _installNotifier.setInstalling(id);
    try {
      final out = await widget.coreService.installSkill(id);
      if (mounted) {
        final convertOut = out['convert'];
        final output = convertOut is Map && convertOut['output'] != null
            ? convertOut['output'].toString()
            : '';
        _installNotifier.setSuccess(output.isNotEmpty ? 'Installed: $output' : 'Installed.');
        _loadInstalled();
      }
    } catch (e) {
      if (mounted) {
        final msg = e.toString().replaceFirst(RegExp(r'^Exception:\s*'), '');
        _installNotifier.setError(msg.isNotEmpty ? 'Install failed: $msg' : 'Install failed.');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final installedState = ref.watch(installedSkillsProvider);
    final searchState = ref.watch(searchSkillsProvider);
    final clawhubState = ref.watch(clawhubLoginProvider);
    final installState = ref.watch(installStateProvider);
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
            if (installedState.loading)
              const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator()))
            else
              SelectableText(installedState.message, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
            if (installedState.skills.isNotEmpty) ...[
              const SizedBox(height: 8),
              ...installedState.skills.map((s) {
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
                                  child: SelectableText(desc, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                                ),
                            ],
                          ),
                        ),
                        FilledButton.tonal(
                          onPressed: installState.installing ? null : () => _remove(folder),
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
              'ClawHub account',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            if (clawhubState.statusLoading)
              const Text('Checking login status…', style: TextStyle(fontSize: 12))
            else
              SelectableText(
                clawhubState.loggedIn == true ? 'Logged in. ${clawhubState.statusMessage.isNotEmpty ? clawhubState.statusMessage : "You can search and install skills."}' : clawhubState.statusMessage,
                style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant),
              ),
            const SizedBox(height: 8),
            Row(
              children: [
                FilledButton.tonal(
                  onPressed: (clawhubState.statusLoading || clawhubState.loginInProgress) ? null : _startClawhubLogin,
                  child: clawhubState.loginInProgress
                      ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : Text(clawhubState.loggedIn == true ? 'Re-login to ClawHub' : 'Login to ClawHub'),
                ),
                if (clawhubState.loggedIn == true) ...[
                  const SizedBox(width: 8),
                  TextButton(
                    onPressed: clawhubState.statusLoading ? null : _loadClawhubLoginStatus,
                    child: const Text('Refresh status'),
                  ),
                ],
              ],
            ),
            const SizedBox(height: 12),
            SelectableText(
              'Or use token (from clawhub.ai):',
              style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 6),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: TextField(
                    controller: _tokenController,
                    decoration: const InputDecoration(
                      hintText: 'Paste ClawHub token',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                    obscureText: true,
                    maxLines: 1,
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: (clawhubState.tokenLoginInProgress || clawhubState.loginInProgress) ? null : _startClawhubTokenLogin,
                  child: clawhubState.tokenLoginInProgress
                      ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Login with token'),
                ),
              ],
            ),
            if (clawhubState.loginMessage.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: SelectableText(clawhubState.loginMessage, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
              ),
            if (clawhubState.loginMessage.toLowerCase().contains('missing state')) ...[
              const SizedBox(height: 10),
              SelectableText(
                'Workaround: Use token login. Open clawhub.ai in a browser, sign in with GitHub, get your CLI token. On the machine running Core run: clawhub login --no-browser --token YOUR_TOKEN',
                style: TextStyle(fontSize: 11, color: Theme.of(context).colorScheme.primary, fontStyle: FontStyle.italic),
              ),
            ],
            if (clawhubState.loginUrl != null && clawhubState.loginUrl!.isNotEmpty) ...[
              const SizedBox(height: 8),
              SelectableText(
                'Complete login on the machine running Core. If a browser opened there, use it; otherwise open the URL below on that machine only. Do not open the URL on this device—the OAuth callback must reach the Core machine.',
                style: TextStyle(fontSize: 11, color: Theme.of(context).colorScheme.onSurfaceVariant, fontStyle: FontStyle.italic),
              ),
              const SizedBox(height: 6),
              SelectableText(clawhubState.loginUrl!, style: TextStyle(fontSize: 11, color: Theme.of(context).colorScheme.primary)),
              const SizedBox(height: 6),
              Row(
                children: [
                  FilledButton.icon(
                    onPressed: () async {
                      final uri = Uri.tryParse(clawhubState.loginUrl!);
                      if (uri != null && await canLaunchUrl(uri)) await launchUrl(uri, mode: LaunchMode.externalApplication);
                    },
                    icon: const Icon(Icons.open_in_browser, size: 18),
                    label: const Text('Open in browser'),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton.icon(
                    onPressed: () {
                      Clipboard.setData(ClipboardData(text: clawhubState.loginUrl!));
                      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Link copied — open on the machine running Core')));
                    },
                    icon: const Icon(Icons.copy, size: 18),
                    label: const Text('Copy link'),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 24),
            const Text(
              'Import from ClawHub',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            SelectableText(
              'Search and install OpenClaw/ClawHub skills. On the machine running Core, install the CLI: npm i -g clawhub. Restart Core from a terminal where clawhub is on PATH.',
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
                  onPressed: searchState.searching ? null : _search,
                  child: searchState.searching ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Search'),
                ),
              ],
            ),
            if (searchState.message.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: SelectableText(searchState.message, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
              ),
            if (searchState.results.isNotEmpty) ...[
              const SizedBox(height: 12),
              ...searchState.results.map((r) {
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
                                  child: SelectableText(desc, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                                ),
                            ],
                          ),
                        ),
                        FilledButton.tonal(
                          onPressed: installState.installing ? null : () => _install(id.toString()),
                          child: const Text('Install'),
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ],
            if (installState.message != null && installState.message!.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 16),
                child: SelectableText(
                  installState.message!,
                  style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.primary),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
