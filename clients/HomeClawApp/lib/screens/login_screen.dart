import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core_service.dart';
import '../providers/login_providers.dart';
import '../widgets/homeclaw_snackbars.dart';
import 'friend_list_screen.dart';

/// Login screen: Core URL, API key (persistent), username picklist, password.
/// On success navigates to FriendListScreen.
class LoginScreen extends ConsumerStatefulWidget {
  final CoreService coreService;
  /// Preserved from a cold-start deep link (e.g. Claw-Code approval) so [FriendListScreen] can open Claw-Code after login.
  final String? initialClawcodeApprovalId;

  const LoginScreen({super.key, required this.coreService, this.initialClawcodeApprovalId});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  late TextEditingController _urlController;
  late TextEditingController _apiKeyController;
  late TextEditingController _passwordController;
  late final LoginNotifier _notifier;

  @override
  void initState() {
    super.initState();
    _notifier = ref.read(loginProvider.notifier);
    _urlController = TextEditingController(text: widget.coreService.baseUrl);
    _apiKeyController = TextEditingController(text: widget.coreService.apiKey ?? '');
    _passwordController = TextEditingController();
    Future.microtask(() {
      if (!mounted) return;
      _initOrAutoLogin();
    });
  }

  @override
  void dispose() {
    _urlController.dispose();
    _apiKeyController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  /// Try auto-login with saved credentials; otherwise load user list and show form.
  Future<void> _initOrAutoLogin() async {
    _notifier.setLoadingUsers(true);
    _notifier.clearError();
    try {
      await widget.coreService.saveBaseUrlAndApiKey(
        baseUrl: _urlController.text.trim(),
        apiKey: _apiKeyController.text.trim().isEmpty ? null : _apiKeyController.text.trim(),
      );
      await widget.coreService.loadSettings();
      final saved = await widget.coreService.getSavedCredentials();
      if (saved != null && saved.username.isNotEmpty && saved.password.isNotEmpty) {
        try {
          await widget.coreService.login(username: saved.username, password: saved.password);
          if (!mounted) return;
          Navigator.of(context).pushReplacement(
            MaterialPageRoute(
              builder: (context) => FriendListScreen(
                coreService: widget.coreService,
                initialClawcodeApprovalId: widget.initialClawcodeApprovalId,
              ),
            ),
          );
          return;
        } catch (_) {
          await widget.coreService.clearCredentials();
        }
      }
      await _loadUsersWithUsernameSafe();
    } catch (e) {
      if (mounted) {
        _notifier.setError(e.toString());
      }
    }
  }

  /// Wraps _loadUsersWithUsername so errors (e.g. network) clear loading state and show error.
  Future<void> _loadUsersWithUsernameSafe() async {
    try {
      await _loadUsersWithUsername();
    } catch (e) {
      if (mounted) {
        _notifier.setError(e.toString());
      }
    }
  }

  Future<void> _loadUsersWithUsername() async {
    if (!mounted) return;
    _notifier.setLoadingUsers(true);
    _notifier.clearError();
    try {
      await widget.coreService.saveBaseUrlAndApiKey(
        baseUrl: _urlController.text.trim(),
        apiKey: _apiKeyController.text.trim().isEmpty ? null : _apiKeyController.text.trim(),
      );
      await widget.coreService.loadSettings();
      final list = await widget.coreService.getConfigUsers();
      final withUsername = list.where((u) {
        final un = (u['username'] as String?)?.trim();
        return un != null && un.isNotEmpty;
      }).toList();
      if (mounted) {
        _notifier.setUsers(withUsername);
        if (withUsername.isNotEmpty) {
          _notifier.setSelectedUsername((withUsername.first['username'] as String?)?.trim());
        }
        _checkConnection();
      }
    } catch (e) {
      if (mounted) {
        _notifier.setError(e.toString());
      }
    }
  }

  Future<void> _checkConnection() async {
    if (!mounted) return;
    _notifier.setConnectionChecking(true);
    final connected = await widget.coreService.checkConnection();
    if (mounted) {
      _notifier.setConnectionStatus(connected);
    }
  }

  Future<void> _saveUrlAndApiKey() async {
    final url = _urlController.text.trim();
    final apiKey = _apiKeyController.text.trim().isEmpty ? null : _apiKeyController.text.trim();
    await widget.coreService.saveBaseUrlAndApiKey(baseUrl: url, apiKey: apiKey);
    await widget.coreService.loadSettings();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Core URL and API key saved')));
    }
  }

  Future<void> _login() async {
    final state = ref.read(loginProvider);
    final username = state.selectedUsername?.trim();
    final password = _passwordController.text;
    if (username == null || username.isEmpty) {
      _notifier.setError('Please select a user');
      return;
    }
    if (password.isEmpty) {
      _notifier.setError('Please enter password');
      return;
    }
    await _saveUrlAndApiKey();
    _notifier.setLoadingLogin(true);
    _notifier.clearError();
    try {
      await widget.coreService.login(username: username, password: password);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (context) => FriendListScreen(
            coreService: widget.coreService,
            initialClawcodeApprovalId: widget.initialClawcodeApprovalId,
          ),
        ),
      );
    } catch (e) {
      if (mounted) {
        _notifier.setError(e.toString());
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(loginProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Login')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('User', style: TextStyle(fontWeight: FontWeight.w500)),
            const SizedBox(height: 8),
            if (state.loadingUsers)
              const Center(child: Padding(padding: EdgeInsets.all(16), child: CircularProgressIndicator()))
            else if (state.usersWithUsername.isEmpty)
              const Padding(
                padding: EdgeInsets.all(8),
                child: Text('No users with username in Core. Add username in config/user.yml, then tap Refresh the connection below.'),
              )
            else
              DropdownButtonFormField<String>(
                initialValue: state.selectedUsername,
                decoration: const InputDecoration(border: OutlineInputBorder()),
                items: state.usersWithUsername.map((u) {
                  final username = (u['username'] as String?)?.trim() ?? '';
                  return DropdownMenuItem(value: username, child: Text(username));
                }).toList(),
                onChanged: (v) => _notifier.setSelectedUsername(v),
              ),
            const SizedBox(height: 16),
            const Text('Password', style: TextStyle(fontWeight: FontWeight.w500)),
            const SizedBox(height: 8),
            TextField(
              controller: _passwordController,
              decoration: const InputDecoration(
                hintText: 'Password',
                border: OutlineInputBorder(),
              ),
              obscureText: true,
              onChanged: (_) => _notifier.clearError(),
            ),
            if (state.error != null) ...[
              const SizedBox(height: 16),
              HomeClawInlineErrorCard(message: state.error!),
            ],
            const SizedBox(height: 24),
            FilledButton(
              onPressed: (state.loadingLogin || state.loadingUsers) ? null : _login,
              child: state.loadingLogin
                  ? const SizedBox(height: 24, width: 24, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Login'),
            ),
            const SizedBox(height: 24),
            const Text('Core URL', style: TextStyle(fontWeight: FontWeight.w500)),
            const SizedBox(height: 8),
            TextField(
              controller: _urlController,
              decoration: const InputDecoration(
                hintText: 'http://127.0.0.1:9000',
                border: OutlineInputBorder(),
              ),
              keyboardType: TextInputType.url,
              onChanged: (_) => _notifier.clearError(),
            ),
            const SizedBox(height: 16),
            const Text('API key (optional; leave empty if Core auth is disabled)', style: TextStyle(fontWeight: FontWeight.w500)),
            const SizedBox(height: 8),
            TextField(
              controller: _apiKeyController,
              decoration: const InputDecoration(
                hintText: 'API key',
                border: OutlineInputBorder(),
              ),
              obscureText: true,
              onChanged: (_) => _notifier.clearError(),
            ),
            const SizedBox(height: 12),
            _buildConnectionStatus(state),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: state.loadingUsers ? null : _connect,
              icon: const Icon(Icons.refresh, size: 20),
              label: const Text('Refresh the connection'),
            ),
          ],
        ),
      ),
    );
  }

  /// Save Core URL and API key, then reconnect and refresh the user list.
  Future<void> _connect() async {
    await _loadUsersWithUsername();
    if (!mounted) return;
    final state = ref.read(loginProvider);
    if (state.error != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        homeClawErrorSnackBar(context, 'Connect failed: ${state.error}'),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Connection refreshed')));
    }
  }

  Widget _buildConnectionStatus(LoginState state) {
    final theme = Theme.of(context);
    if (state.connectionChecking) {
      return Row(
        children: [
          SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: theme.colorScheme.primary)),
          const SizedBox(width: 10),
          Text('Checking connection…', style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
        ],
      );
    }
    if (state.connectionStatus == true) {
      return Row(
        children: [
          Icon(Icons.check_circle, color: theme.colorScheme.primary, size: 20),
          const SizedBox(width: 10),
          Text('Connected', style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.primary, fontWeight: FontWeight.w500)),
        ],
      );
    }
    if (state.connectionStatus == false) {
      return Row(
        children: [
          Icon(Icons.cancel, color: theme.colorScheme.error, size: 20),
          const SizedBox(width: 10),
          Text('Disconnected', style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.error)),
        ],
      );
    }
    return Row(
      children: [
        Icon(Icons.help_outline, size: 20, color: theme.colorScheme.onSurfaceVariant),
        const SizedBox(width: 10),
        Text('Tap "Refresh the connection" to check status', style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
      ],
    );
  }
}
