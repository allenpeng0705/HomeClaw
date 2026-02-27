import 'package:flutter/material.dart';
import '../core_service.dart';
import 'friend_list_screen.dart';

/// Login screen: Core URL, API key (persistent), username picklist, password.
/// On success navigates to FriendListScreen.
class LoginScreen extends StatefulWidget {
  final CoreService coreService;

  const LoginScreen({super.key, required this.coreService});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  late TextEditingController _urlController;
  late TextEditingController _apiKeyController;
  late TextEditingController _passwordController;
  List<Map<String, dynamic>> _usersWithUsername = [];
  String? _selectedUsername;
  bool _loadingUsers = true;
  bool _loadingLogin = false;
  String? _error;
  bool? _connectionStatus; // true = connected, false = disconnected, null = not checked
  bool _connectionChecking = false;

  @override
  void initState() {
    super.initState();
    _urlController = TextEditingController(text: widget.coreService.baseUrl);
    _apiKeyController = TextEditingController(text: widget.coreService.apiKey ?? '');
    _passwordController = TextEditingController();
    _initOrAutoLogin();
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
    setState(() {
      _loadingUsers = true;
      _error = null;
    });
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
              builder: (context) => FriendListScreen(coreService: widget.coreService),
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
        setState(() {
          _loadingUsers = false;
          _usersWithUsername = [];
          _error = e.toString();
        });
      }
    }
  }

  /// Wraps _loadUsersWithUsername so errors (e.g. network) clear loading state and show error.
  Future<void> _loadUsersWithUsernameSafe() async {
    try {
      await _loadUsersWithUsername();
    } catch (e) {
      if (mounted) {
        setState(() {
          _loadingUsers = false;
          _usersWithUsername = [];
          _error = e.toString();
        });
      }
    }
  }

  Future<void> _loadUsersWithUsername() async {
    if (!mounted) return;
    setState(() {
      _loadingUsers = true;
      _error = null;
    });
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
        setState(() {
          _usersWithUsername = withUsername;
          _loadingUsers = false;
          if (_selectedUsername == null && withUsername.isNotEmpty) {
            _selectedUsername = (withUsername.first['username'] as String?)?.trim();
          }
        });
        _checkConnection();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _loadingUsers = false;
          _usersWithUsername = [];
          _error = e.toString();
        });
      }
    }
  }

  Future<void> _checkConnection() async {
    if (!mounted) return;
    setState(() => _connectionChecking = true);
    final connected = await widget.coreService.checkConnection();
    if (mounted) {
      setState(() {
        _connectionChecking = false;
        _connectionStatus = connected;
      });
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
    final username = _selectedUsername?.trim();
    final password = _passwordController.text;
    if (username == null || username.isEmpty) {
      setState(() => _error = 'Please select a user');
      return;
    }
    if (password.isEmpty) {
      setState(() => _error = 'Please enter password');
      return;
    }
    await _saveUrlAndApiKey();
    setState(() {
      _loadingLogin = true;
      _error = null;
    });
    try {
      await widget.coreService.login(username: username, password: password);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (context) => FriendListScreen(coreService: widget.coreService),
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() {
          _loadingLogin = false;
          _error = e.toString();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Login')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('User', style: TextStyle(fontWeight: FontWeight.w500)),
            const SizedBox(height: 8),
            if (_loadingUsers)
              const Center(child: Padding(padding: EdgeInsets.all(16), child: CircularProgressIndicator()))
            else if (_usersWithUsername.isEmpty)
              const Padding(
                padding: EdgeInsets.all(8),
                child: Text('No users with username in Core. Add username in config/user.yml, then tap Refresh the connection below.'),
              )
            else
              DropdownButtonFormField<String>(
                value: _selectedUsername,
                decoration: const InputDecoration(border: OutlineInputBorder()),
                items: _usersWithUsername.map((u) {
                  final username = (u['username'] as String?)?.trim() ?? '';
                  return DropdownMenuItem(value: username, child: Text(username));
                }).toList(),
                onChanged: (v) => setState(() => _selectedUsername = v),
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
              onChanged: (_) => setState(() => _error = null),
            ),
            if (_error != null) ...[
              const SizedBox(height: 16),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
            const SizedBox(height: 24),
            FilledButton(
              onPressed: (_loadingLogin || _loadingUsers) ? null : _login,
              child: _loadingLogin
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
              onChanged: (_) => setState(() => _error = null),
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
              onChanged: (_) => setState(() => _error = null),
            ),
            const SizedBox(height: 12),
            _buildConnectionStatus(),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: _loadingUsers ? null : _connect,
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
    if (_error != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Connect failed: $_error'), backgroundColor: Theme.of(context).colorScheme.errorContainer),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Connection refreshed')));
    }
  }

  Widget _buildConnectionStatus() {
    final theme = Theme.of(context);
    if (_connectionChecking) {
      return Row(
        children: [
          SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: theme.colorScheme.primary)),
          const SizedBox(width: 10),
          Text('Checking connection…', style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
        ],
      );
    }
    if (_connectionStatus == true) {
      return Row(
        children: [
          Icon(Icons.check_circle, color: theme.colorScheme.primary, size: 20),
          const SizedBox(width: 10),
          Text('Connected', style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.primary, fontWeight: FontWeight.w500)),
        ],
      );
    }
    if (_connectionStatus == false) {
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
