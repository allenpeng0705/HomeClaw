import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core_service.dart';
import '../envoy/relay_client.dart';
import '../providers/envoy_providers.dart';
import '../providers/login_providers.dart';
import '../widgets/homeclaw_snackbars.dart';
import 'envoy_pairing_screen.dart';
import 'friend_list_screen.dart';

/// How Companion reaches Core UI modes (routing still follows Core URL heuristic + relay state).
enum _LoginConnectionRoute {
  envoyHomeCore,
  directFromPhone,
}

/// Login screen: choose connection route, Core URL/API key, optional Envoy pairing, credentials.
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
  late TextEditingController _usernameController;
  late final LoginNotifier _notifier;
  late _LoginConnectionRoute _connectionRoute;

  _LoginConnectionRoute _defaultRouteFromCoreSettings() =>
      widget.coreService.companionUsesEnvoyForConfiguredCoreWhenRelayConnected
          ? _LoginConnectionRoute.envoyHomeCore
          : _LoginConnectionRoute.directFromPhone;

  @override
  void initState() {
    super.initState();
    _notifier = ref.read(loginProvider.notifier);
    _urlController = TextEditingController(text: widget.coreService.baseUrl);
    _apiKeyController = TextEditingController(text: widget.coreService.apiKey ?? '');
    _passwordController = TextEditingController();
    _usernameController = TextEditingController();
    _connectionRoute = _defaultRouteFromCoreSettings();
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
    _usernameController.dispose();
    super.dispose();
  }

  Future<void> _openEnvoyPairingScanner() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (context) => EnvoyPairingScreen(
          coreService: widget.coreService,
        ),
      ),
    );
    if (!mounted) return;
    await _reloadConfigUsersAfterEnvoyIfNeeded();
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
      await _reloadConfigUsersAfterEnvoyIfNeeded();
    } catch (e) {
      if (mounted) {
        _notifier.setError(e.toString());
      }
    }
  }

  /// When Core is LAN-only, [getConfigUsers] needs the Envoy relay; reload after pairing or reconnect.
  Future<void> _reloadConfigUsersAfterEnvoyIfNeeded() async {
    if (!mounted) return;
    if (!widget.coreService.companionUsesEnvoyForConfiguredCoreWhenRelayConnected) return;
    if (!ref.read(envoyMeshProvider).isConnected) return;
    final st = ref.read(loginProvider);
    if (st.usersWithUsername.isNotEmpty && st.error == null) return;
    await _loadUsersWithUsername();
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
          final u = (withUsername.first['username'] as String?)?.trim() ?? '';
          _notifier.setSelectedUsername(u);
          if (_usernameController.text.trim().isEmpty && u.isNotEmpty) {
            _usernameController.text = u;
          }
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
    final username = _usernameController.text.trim();
    final password = _passwordController.text;
    if (username.isEmpty) {
      _notifier.setError('Enter your user name');
      return;
    }
    if (password.isEmpty) {
      _notifier.setError('Please enter your password');
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
    } finally {
      if (mounted) {
        _notifier.setLoadingLogin(false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(envoyMeshProvider, (previous, next) {
      final was = previous?.isConnected ?? false;
      if (!was && next.isConnected) {
        unawaited(_reloadConfigUsersAfterEnvoyIfNeeded());
      }
    });

    final state = ref.watch(loginProvider);
    final envoyState = ref.watch(envoyMeshProvider);
    final scheme = Theme.of(context).colorScheme;
    final routeTip = _buildRouteAlignmentTip();

    final coreUrlSubtitle = _connectionRoute == _LoginConnectionRoute.envoyHomeCore
        ? 'What Core listens on at home (often http://127.0.0.1:9000). Your phone normally does not open this URL directly—the Envoy node uses it after the relay connects.'
        : 'Must resolve from this phone: public HTTPS hostname, or LAN IP when you are on the same Wi‑Fi.';

    return Scaffold(
      appBar: AppBar(title: const Text('Login')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Connect to Core',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 6),
            Text(
              'Pick how Companion reaches Core. You can change this any time—the choice only groups this screen.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant, height: 1.35),
            ),
            const SizedBox(height: 14),
            SizedBox(
              width: double.infinity,
              child: SegmentedButton<_LoginConnectionRoute>(
                segments: const [
                  ButtonSegment<_LoginConnectionRoute>(
                    value: _LoginConnectionRoute.envoyHomeCore,
                    label: Text('Envoy tunnel'),
                  ),
                  ButtonSegment<_LoginConnectionRoute>(
                    value: _LoginConnectionRoute.directFromPhone,
                    label: Text('Direct URL'),
                  ),
                ],
                selected: <_LoginConnectionRoute>{_connectionRoute},
                onSelectionChanged: (Set<_LoginConnectionRoute> s) {
                  if (s.isEmpty) return;
                  setState(() {
                    _connectionRoute = s.first;
                  });
                },
              ),
            ),
            const SizedBox(height: 12),
            Text(
              _connectionRoute == _LoginConnectionRoute.envoyHomeCore
                  ? 'Core stays on your home network—pair EnvoyMesh once below so HTTPS-style API traffic can tunnel from here.'
                  : 'This phone calls Core HTTP without going through Envoy first. EnvoyMesh pairing (mesh chat / optional tunnel) stays under Settings.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(height: 1.35, color: scheme.onSurfaceVariant),
            ),
            if (routeTip != null) ...[
              const SizedBox(height: 12),
              routeTip,
            ],
            const Divider(height: 36),
            Text(
              'Core server',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 10),
            Text(
              'Core base URL',
              style: TextStyle(fontWeight: FontWeight.w500, fontSize: 13, color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 6),
            Text(
              coreUrlSubtitle,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant, height: 1.35),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _urlController,
              decoration: const InputDecoration(
                hintText: 'http://127.0.0.1:9000',
                border: OutlineInputBorder(),
              ),
              keyboardType: TextInputType.url,
              autocorrect: false,
              onChanged: (_) {
                _notifier.clearError();
                setState(() {});
              },
            ),
            const SizedBox(height: 16),
            Text(
              'API key (optional)',
              style: TextStyle(fontWeight: FontWeight.w500, fontSize: 13, color: scheme.onSurfaceVariant),
            ),
            Text(
              'Leave empty if Core auth is disabled.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _apiKeyController,
              decoration: const InputDecoration(hintText: 'API key', border: OutlineInputBorder()),
              obscureText: true,
              autocorrect: false,
              onChanged: (_) {
                _notifier.clearError();
                setState(() {});
              },
            ),
            if (_connectionRoute == _LoginConnectionRoute.envoyHomeCore) ...[
              const SizedBox(height: 24),
              _buildEnvoyRelayPanel(context, envoyState),
            ] else ...[
              const SizedBox(height: 16),
              Text(
                'Optional: EnvoyMesh for mesh/chat still lives under Settings — it is not needed for reaching a public HTTPS Core.',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      height: 1.35,
                      color: scheme.onSurfaceVariant,
                    ),
              ),
            ],
            const Divider(height: 36),
            Text(
              'Sign in',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 16),
            Text(
              'User name',
              style: TextStyle(
                fontWeight: FontWeight.w500,
                fontSize: 13,
                color: scheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 8),
            if (state.loadingUsers)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Row(
                  children: [
                    SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: scheme.primary,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'Loading choices from Core…',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                      ),
                    ),
                  ],
                ),
              ),
            if (!state.loadingUsers && state.usersWithUsername.isNotEmpty) ...[
              Text(
                'Pick from Core (optional)',
                style: TextStyle(
                  fontWeight: FontWeight.w500,
                  fontSize: 13,
                  color: scheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 8),
              Builder(
                builder: (context) {
                  final names = state.usersWithUsername
                      .map((u) => (u['username'] as String?)?.trim() ?? '')
                      .where((s) => s.isNotEmpty)
                      .toList();
                  final selected = state.selectedUsername?.trim();
                  final value = selected != null && names.contains(selected) ? selected : null;
                  return DropdownButtonFormField<String>(
                    key: ValueKey<String>(names.join('|')),
                    initialValue: value,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      hintText: 'Select a Core user…',
                    ),
                    items: names.map((n) => DropdownMenuItem<String>(value: n, child: Text(n))).toList(),
                    onChanged: (v) {
                      _notifier.setSelectedUsername(v);
                      if (v != null && v.trim().isNotEmpty) {
                        _usernameController.text = v.trim();
                      }
                      setState(() {});
                    },
                  );
                },
              ),
              const SizedBox(height: 12),
              Text(
                'Or enter manually below',
                style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant),
              ),
              const SizedBox(height: 8),
            ],
            TextField(
              controller: _usernameController,
              decoration: InputDecoration(
                hintText:
                    _connectionRoute == _LoginConnectionRoute.envoyHomeCore ? 'Core username' : 'User name on your Core server',
                border: const OutlineInputBorder(),
              ),
              autocorrect: false,
              textInputAction: TextInputAction.next,
              onChanged: (_) {
                final t = _usernameController.text.trim();
                _notifier.setSelectedUsername(t.isEmpty ? null : t);
                _notifier.clearError();
              },
            ),
            if (!state.loadingUsers && state.usersWithUsername.isEmpty) ...[
              const SizedBox(height: 10),
              Text(
                _emptyUserListHint(envoyState),
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                      height: 1.35,
                    ),
              ),
            ],
            const SizedBox(height: 16),
            Text(
              'Password',
              style: TextStyle(
                fontWeight: FontWeight.w500,
                fontSize: 13,
                color: scheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _passwordController,
              decoration: const InputDecoration(
                hintText: 'Enter password',
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
              onPressed: state.loadingLogin ? null : _login,
              child: state.loadingLogin
                  ? const SizedBox(
                      height: 24,
                      width: 24,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Login'),
            ),
            const SizedBox(height: 28),
            Text(
              'Check connection',
              style: TextStyle(
                fontWeight: FontWeight.w500,
                fontSize: 13,
                color: scheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 8),
            _buildConnectionStatus(state, envoyState),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: state.loadingUsers ? null : _connect,
              icon: const Icon(Icons.refresh, size: 20),
              label: const Text('Verify Core & reload users'),
            ),
          ],
        ),
      ),
    );
  }

  bool _typedUrlLooksGloballyReachable() {
    final raw = _urlController.text.trim().replaceFirst(RegExp(r'/$'), '');
    if (raw.isEmpty) return false;
    return CoreService.heuristicCompanionCoreUrlGloballyReachable(raw);
  }

  bool _typedUrlLooksLikeHomeOrPrivate() {
    final raw = _urlController.text.trim().replaceFirst(RegExp(r'/$'), '');
    if (raw.isEmpty) return false;
    return !CoreService.heuristicCompanionCoreUrlGloballyReachable(raw);
  }

  Widget? _buildRouteAlignmentTip() {
    final raw = _urlController.text.trim().replaceFirst(RegExp(r'/$'), '');
    if (raw.isEmpty) return null;
    final scheme = Theme.of(context).colorScheme;
    if (_connectionRoute == _LoginConnectionRoute.directFromPhone &&
        CoreService.heuristicCompanionCoreBaseHostIsLoopback(raw)) {
      return Card(
        margin: EdgeInsets.zero,
        color: scheme.errorContainer.withValues(alpha: 0.35),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.warning_amber_rounded, color: scheme.error, size: 22),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'localhost / 127.0.0.1 cannot be reached from this phone directly. Switch to Envoy tunnel—or enter a LAN IP or HTTPS URL.',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: scheme.onErrorContainer,
                        height: 1.35,
                      ),
                ),
              ),
            ],
          ),
        ),
      );
    }
    if (_connectionRoute == _LoginConnectionRoute.directFromPhone &&
        _typedUrlLooksLikeHomeOrPrivate()) {
      return Card(
        margin: EdgeInsets.zero,
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.6),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.info_outline, color: scheme.primary, size: 22),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'This URL looks “at home”. Companion tunnels through EnvoyMesh when the relay is connected. Use Envoy tunnel for pairing—or stay here if you already use Settings → EnvoyMesh Connect.',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        height: 1.35,
                      ),
                ),
              ),
            ],
          ),
        ),
      );
    }
    if (_connectionRoute == _LoginConnectionRoute.envoyHomeCore &&
        _typedUrlLooksGloballyReachable()) {
      return Card(
        margin: EdgeInsets.zero,
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.6),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.lightbulb_outline, color: scheme.primary, size: 22),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'This host is usually reachable from the phone without the mesh—Direct mode may be simpler. Stay on Envoy tunnel if that is how your home setup works.',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        height: 1.35,
                      ),
                ),
              ),
            ],
          ),
        ),
      );
    }
    return null;
  }

  /// Empty user-picker hint reconciles typed URL heuristic with chosen route.
  String _emptyUserListHint(EnvoyMeshState envoyState) {
    if (!widget.coreService.companionUsesEnvoyForConfiguredCoreWhenRelayConnected) {
      return 'No user list loaded from Core. Type your user name above, or add usernames to config/user.yml and tap Verify below.';
    }
    if (_connectionRoute == _LoginConnectionRoute.directFromPhone) {
      return 'No user list yet—home-style Core URLs often need the Envoy relay. Switch to Envoy tunnel and connect—or type your Core username manually.';
    }
    if (envoyState.connectionStatus == RelayClientState.reconnectBackoff) {
      return 'Envoy relay is backing off between automatic retries (up to ~1 minute apart). Tap Settings → EnvoyMesh → Connect to reconnect sooner.';
    }
    if (!envoyState.isConnected) {
      return 'Relay not connected; user list stays empty until Envoy reconnects (Settings → EnvoyMesh → Connect—you rarely need to scan QR again).';
    }
    return 'Could not load users from Core. Type your Core username manually, then check URL / Verify below.';
  }

  Widget _buildEnvoyRelayPanel(BuildContext context, EnvoyMeshState envoyState) {
    final theme = Theme.of(context);

    Widget statusInner;
    if (envoyState.isConnected) {
      final url = envoyState.homeNodeUrl;
      statusInner = Card(
        elevation: 0,
        color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.55),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: theme.colorScheme.outlineVariant),
        ),
        margin: EdgeInsets.zero,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Home node reachable',
                style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Icon(Icons.circle, size: 10, color: theme.colorScheme.primary),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Relay connected — API calls can tunnel through Envoy when Core is LAN-only.',
                      style: theme.textTheme.bodySmall?.copyWith(
                        height: 1.35,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                ],
              ),
              if (url != null && url.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  'Node WebSocket URL',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 4),
                SelectableText(
                  url,
                  style: theme.textTheme.bodySmall?.copyWith(fontFamily: 'monospace'),
                ),
              ],
            ],
          ),
        ),
      );
    } else if (envoyState.connectionStatus == RelayClientState.reconnectBackoff) {
      statusInner = Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.hourglass_bottom_rounded,
            size: 22,
            color: Colors.amber.shade800,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              'Between EnvoyMesh reconnect tries (delay caps near 1 minute). '
              'Open Settings → EnvoyMesh → Connect to dial immediately—or wait for the background retry.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
                height: 1.35,
              ),
            ),
          ),
        ],
      );
    } else if (envoyState.connectionStatus == RelayClientState.connecting) {
      statusInner = Row(
        children: [
          SizedBox(
            width: 22,
            height: 22,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              color: theme.colorScheme.primary,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              'Connecting to EnvoyMesh relay (handshake)…',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
        ],
      );
    } else if (envoyState.connectionStatus == RelayClientState.error) {
      statusInner = Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.error_outline, color: theme.colorScheme.error, size: 22),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              envoyState.error?.trim().isNotEmpty == true
                  ? envoyState.error!.trim()
                  : 'Could not reach the EnvoyMesh relay from this attempt. Tap Settings → EnvoyMesh → Connect to retry sooner—pairing is saved—and the app also keeps reconnecting in the '
                      'background (up to ~1 minute between retries). Restart or scan QR only if pairing was lost.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.error,
                height: 1.35,
              ),
            ),
          ),
        ],
      );
    } else {
      statusInner = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Relay offline',
            style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 8),
          Text(
            'Scan the Envoy pairing QR once (shown on Social → Settings → Node on your home PC); '
            'after that reconnect from Settings → EnvoyMesh → Connect.',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              height: 1.35,
            ),
          ),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'EnvoyMesh pairing',
          style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 12),
        statusInner,
        const SizedBox(height: 16),
        OutlinedButton.icon(
          onPressed: _openEnvoyPairingScanner,
          icon: const Icon(Icons.qr_code_scanner),
          label: const Text('Scan Envoy pairing QR'),
        ),
        const SizedBox(height: 6),
        Text(
          'Scan once — pairing persists. Use EnvoyMesh Connect in Settings later.',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
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

  Widget _buildConnectionStatus(LoginState state, EnvoyMeshState envoyState) {
    final theme = Theme.of(context);
    if (state.connectionChecking) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: theme.colorScheme.primary,
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Checking Core (/ready)…',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
                height: 1.35,
              ),
            ),
          ),
        ],
      );
    }
    if (state.connectionStatus == true) {
      final lanCore = widget.coreService.companionUsesEnvoyForConfiguredCoreWhenRelayConnected;
      final relayOn = envoyState.isConnected;
      final detail = lanCore && relayOn
          ? 'Core replied OK (via Envoy relay or direct fallback, depending on the request).'
          : 'Core replied OK at your base URL.';
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(
              Icons.check_circle,
              color: theme.colorScheme.primary,
              size: 20,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              detail,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.primary,
                fontWeight: FontWeight.w500,
                height: 1.35,
              ),
            ),
          ),
        ],
      );
    }
    if (state.connectionStatus == false) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(Icons.cancel, color: theme.colorScheme.error, size: 20),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              widget.coreService.companionUsesEnvoyForConfiguredCoreWhenRelayConnected &&
                      _connectionRoute == _LoginConnectionRoute.envoyHomeCore &&
                      !envoyState.isConnected
                  ? 'Could not reach Core. Finish Envoy pairing/connect the relay in the Envoy tunnel section, then tap Verify.'
                  : widget.coreService.companionUsesEnvoyForConfiguredCoreWhenRelayConnected
                      ? 'Could not reach Core. Check Envoy status, Core URL (as configured at home), and API key, then tap Verify.'
                      : 'Could not reach Core at this URL from the phone. Check URL and API key, then tap Verify.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.error,
                height: 1.35,
              ),
            ),
          ),
        ],
      );
    }
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          Icons.help_outline,
          size: 20,
          color: theme.colorScheme.onSurfaceVariant,
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            'Tap Verify & reload users to ping Core (/ready).',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              height: 1.35,
            ),
          ),
        ),
      ],
    );
  }
}
