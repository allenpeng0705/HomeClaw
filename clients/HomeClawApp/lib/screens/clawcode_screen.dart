import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core_service.dart';
import '../widgets/cc_run_chip.dart';

String _formatClawcodeLastUsage(dynamic raw) {
  if (raw == null) return '—';
  if (raw is! Map) return raw.toString();
  final m = Map<String, dynamic>.from(raw);
  final tt = m['total_tokens'];
  final pt = m['prompt_tokens'];
  final ct = m['completion_tokens'];
  final r = m['rounds'];
  final est = m['estimated'] == true;
  final parts = <String>[];
  if (tt != null) parts.add('total=$tt');
  if (pt != null) parts.add('prompt=$pt');
  if (ct != null) parts.add('completion=$ct');
  if (r != null) parts.add('rounds=$r');
  if (est) parts.add('estimated');
  return parts.isEmpty ? '—' : parts.join(', ');
}

enum CcRunState { idle, running, approvalPending, error }

String _formatTaskPlanForEdit(dynamic raw) {
  if (raw == null) return '';
  if (raw is String) return raw;
  try {
    return const JsonEncoder.withIndent('  ').convert(raw);
  } catch (_) {
    return raw.toString();
  }
}

/// Claw-Code tools: sessions, approvals, workspace file list, optional browser UI at Core `/clawcode`.
/// Primary flow is the **main chat** (per-friend session binding). This screen is for approvals, files, and power-user tools.
class ClawcodeScreen extends StatefulWidget {
  final CoreService coreService;
  /// When set (e.g. from a push deep link), show a hint after load if this approval is still pending.
  final String? initialApprovalId;
  /// When opened from a friend chat, POST /inbound includes `friend_id` so Core scopes memory/session correctly.
  final String? chatFriendId;

  const ClawcodeScreen({super.key, required this.coreService, this.initialApprovalId, this.chatFriendId});

  @override
  State<ClawcodeScreen> createState() => _ClawcodeScreenState();
}

class _ClawcodeScreenState extends State<ClawcodeScreen> {
  late TextEditingController _webUrlController;
  late TextEditingController _composeController;
  Timer? _approvalPollTimer;
  bool _loading = false;
  String? _error;
  List<Map<String, dynamic>> _sessions = [];
  List<Map<String, dynamic>> _approvals = [];
  String? _filesSessionId;
  String _filesRel = '';
  List<Map<String, dynamic>> _fileEntries = [];
  bool _filesLoading = false;

  String? _activeSessionId;
  bool _sending = false;
  String _progressLine = '';
  String _lastReply = '';
  CcRunState _ccRunState = CcRunState.idle;

  String get _owner {
    final u = widget.coreService.sessionUserId?.trim();
    if (u != null && u.isNotEmpty) return u;
    return 'companion';
  }

  static String _prefActiveSessionKey(String owner) => 'clawcode_active_session_v1_${owner.trim()}';

  @override
  void initState() {
    super.initState();
    _webUrlController = TextEditingController(text: widget.coreService.resolvedClawcodeWebUrl());
    _composeController = TextEditingController();
    _approvalPollTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (!mounted || _sending) return;
      _lightPollApprovals();
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _refresh().then((approvals) {
        if (!mounted) return;
        final want = widget.initialApprovalId?.trim();
        if (want == null || want.isEmpty) return;
        final has = approvals.any((a) => (a['approval_id'] ?? '').toString() == want);
        if (has) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Approval pending — use Approve or Reject below.')),
          );
        }
      });
    });
  }

  @override
  void dispose() {
    _approvalPollTimer?.cancel();
    _webUrlController.dispose();
    _composeController.dispose();
    super.dispose();
  }

  Future<void> _lightPollApprovals() async {
    try {
      final a = await widget.coreService.fetchClawcodeApprovals(_owner);
      if (!mounted) return;
      setState(() {
        _approvals = a;
        if (_ccRunState == CcRunState.running && a.isNotEmpty) {
          _ccRunState = CcRunState.approvalPending;
        }
      });
    } catch (_) {}
  }

  Future<void> _selectSession(String? sid) async {
    final prefs = await SharedPreferences.getInstance();
    if (sid == null || sid.isEmpty) {
      await prefs.remove(_prefActiveSessionKey(_owner));
      if (!mounted) return;
      setState(() {
        _activeSessionId = null;
        _composeController.clear();
      });
      return;
    }
    await prefs.setString(_prefActiveSessionKey(_owner), sid);
    final draft = await widget.coreService.loadClawcodeComposeDraft(ownerUserId: _owner, sessionId: sid);
    if (!mounted) return;
    setState(() {
      _activeSessionId = sid;
      _composeController.text = draft ?? '';
    });
  }

  Future<void> _fixActiveSessionAfterRefresh(List<Map<String, dynamic>> sessions) async {
    final ids = sessions.map((s) => (s['clawcode_session_id'] ?? '').toString()).where((x) => x.isNotEmpty).toList();
    if (ids.isEmpty) {
      if (_activeSessionId != null) await _selectSession(null);
      return;
    }
    if (_activeSessionId != null && ids.contains(_activeSessionId)) return;
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_prefActiveSessionKey(_owner));
    if (saved != null && ids.contains(saved)) {
      await _selectSession(saved);
    } else {
      await _selectSession(ids.first);
    }
  }

  Future<void> _sendClawcodeInbound() async {
    final sid = _activeSessionId?.trim();
    if (sid == null || sid.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Select an active session first.')));
      }
      return;
    }
    final msg = _composeController.text.trim();
    if (msg.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Enter a message to send to Core.')));
      }
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() {
      _sending = true;
      _progressLine = '';
      _ccRunState = CcRunState.running;
    });
    try {
      await widget.coreService.saveClawcodeComposeDraft(ownerUserId: _owner, sessionId: sid, text: msg);
      final fid = widget.chatFriendId?.trim();
      final r = await widget.coreService.sendMessage(
        msg,
        userId: _owner,
        friendId: (fid != null && fid.isNotEmpty) ? fid : null,
        useStream: true,
        onProgress: (m) {
          if (mounted) setState(() => _progressLine = m);
        },
        clawcodeSessionId: sid,
      );
      if (!mounted) return;
      final text = r['text']?.toString() ?? '';
      setState(() {
        _lastReply = text;
        _ccRunState = CcRunState.idle;
      });
      await _refresh();
      if (!mounted) return;
      setState(() {
        _ccRunState = _approvals.isNotEmpty ? CcRunState.approvalPending : CcRunState.idle;
      });
    } catch (e) {
      final err = e.toString();
      try {
        await widget.coreService.patchClawcodeSession(
          sessionId: sid,
          ownerUserId: _owner,
          body: {'last_run_error': err.length > 2000 ? '${err.substring(0, 2000)}…' : err},
        );
      } catch (_) {}
      if (mounted) {
        setState(() => _ccRunState = CcRunState.error);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err)));
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _retryLastCompose() async {
    final sid = _activeSessionId?.trim();
    if (sid == null || sid.isEmpty) return;
    final t = await widget.coreService.loadClawcodeComposeDraft(ownerUserId: _owner, sessionId: sid);
    if (t == null || t.trim().isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No saved message for this session. Send once to enable retry.')),
        );
      }
      return;
    }
    setState(() => _composeController.text = t);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Restored last message — tap Send to run again.')),
      );
    }
  }

  Future<void> _showPlanRecoveryDialog(BuildContext screenContext) async {
    final sid = _activeSessionId?.trim();
    if (sid == null || sid.isEmpty) {
      ScaffoldMessenger.of(screenContext).showSnackBar(
        const SnackBar(content: Text('Select a session first.')),
      );
      return;
    }
    Map<String, dynamic> det = {};
    try {
      det = await widget.coreService.fetchClawcodeSessionDetail(sessionId: sid, ownerUserId: _owner);
    } catch (e) {
      if (screenContext.mounted) {
        ScaffoldMessenger.of(screenContext).showSnackBar(SnackBar(content: Text('$e')));
      }
      return;
    }
    final planCtrl = TextEditingController(text: _formatTaskPlanForEdit(det['task_plan']));
    final checkpointCtrl = TextEditingController(text: (det['checkpoint'] ?? '').toString());
    final resumeCtrl = TextEditingController(text: (det['resume_hint'] ?? '').toString());
    var saving = false;

    if (!screenContext.mounted) return;
    try {
      await showDialog<void>(
        context: screenContext,
        builder: (dialogCtx) {
          return StatefulBuilder(
            builder: (ctx, setDlg) {
              return AlertDialog(
                title: const Text('Plan & recovery'),
                content: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        'task_plan must be a JSON array of objects: id, title, status (pending|running|done|blocked).',
                        style: Theme.of(ctx).textTheme.bodySmall,
                      ),
                      const SizedBox(height: 8),
                      TextField(
                        controller: planCtrl,
                        enabled: !saving,
                        decoration: const InputDecoration(
                          labelText: 'task_plan (JSON array)',
                          border: OutlineInputBorder(),
                        ),
                        maxLines: 8,
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: checkpointCtrl,
                        enabled: !saving,
                        decoration: const InputDecoration(
                          labelText: 'checkpoint',
                          border: OutlineInputBorder(),
                        ),
                        maxLines: 3,
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: resumeCtrl,
                        enabled: !saving,
                        decoration: const InputDecoration(
                          labelText: 'resume_hint',
                          border: OutlineInputBorder(),
                        ),
                        maxLines: 4,
                      ),
                    ],
                  ),
                ),
                actions: [
                  TextButton(
                    onPressed: saving
                        ? null
                        : () async {
                            setDlg(() => saving = true);
                            try {
                              await widget.coreService.patchClawcodeSession(
                                sessionId: sid,
                                ownerUserId: _owner,
                                body: {'last_run_error': ''},
                              );
                              if (!dialogCtx.mounted) return;
                              setDlg(() => saving = false);
                              ScaffoldMessenger.of(dialogCtx).showSnackBar(
                                const SnackBar(content: Text('Cleared last_run_error')),
                              );
                              await _refresh();
                            } catch (e) {
                              setDlg(() => saving = false);
                              if (dialogCtx.mounted) {
                                ScaffoldMessenger.of(dialogCtx).showSnackBar(SnackBar(content: Text('$e')));
                              }
                            }
                          },
                    child: const Text('Clear error'),
                  ),
                  TextButton(
                    onPressed: saving ? null : () => Navigator.pop(dialogCtx),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    onPressed: saving
                        ? null
                        : () async {
                            final body = <String, dynamic>{
                              'checkpoint': checkpointCtrl.text.trim(),
                              'resume_hint': resumeCtrl.text.trim(),
                            };
                            final rawPlan = planCtrl.text.trim();
                            if (rawPlan.isEmpty) {
                              body['task_plan'] = <dynamic>[];
                            } else {
                              try {
                                final dec = jsonDecode(rawPlan);
                                if (dec is! List) {
                                  if (dialogCtx.mounted) {
                                    ScaffoldMessenger.of(dialogCtx).showSnackBar(
                                      const SnackBar(content: Text('task_plan must be a JSON array')),
                                    );
                                  }
                                  return;
                                }
                                body['task_plan'] = dec;
                              } catch (e) {
                                if (dialogCtx.mounted) {
                                  ScaffoldMessenger.of(dialogCtx).showSnackBar(
                                    SnackBar(content: Text('Invalid JSON: $e')),
                                  );
                                }
                                return;
                              }
                            }
                            setDlg(() => saving = true);
                            try {
                              await widget.coreService.patchClawcodeSession(
                                sessionId: sid,
                                ownerUserId: _owner,
                                body: body,
                              );
                              if (!dialogCtx.mounted) return;
                              Navigator.pop(dialogCtx);
                              if (!screenContext.mounted) return;
                              ScaffoldMessenger.of(screenContext).showSnackBar(
                                const SnackBar(content: Text('Plan & recovery saved')),
                              );
                              await _refresh();
                            } catch (e) {
                              setDlg(() => saving = false);
                              if (dialogCtx.mounted) {
                                ScaffoldMessenger.of(dialogCtx).showSnackBar(SnackBar(content: Text('$e')));
                              }
                            }
                          },
                    child: saving
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Save'),
                  ),
                ],
              );
            },
          );
        },
      );
    } finally {
      planCtrl.dispose();
      checkpointCtrl.dispose();
      resumeCtrl.dispose();
    }
  }

  Future<void> _showMcpDiagnosticsSheet(BuildContext screenContext) async {
    await showModalBottomSheet<void>(
      context: screenContext,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) {
        return _ClawcodeMcpSheet(coreService: widget.coreService);
      },
    );
  }

  Future<List<Map<String, dynamic>>> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    List<Map<String, dynamic>> approvals = [];
    try {
      final sessions = await widget.coreService.fetchClawcodeSessions(_owner);
      try {
        approvals = await widget.coreService.fetchClawcodeApprovals(_owner);
      } catch (_) {
        // ignore if empty/error when feature off
      }
      if (!mounted) return approvals;
      setState(() {
        _sessions = sessions;
        _approvals = approvals;
        _loading = false;
        _filesSessionId = null;
        _fileEntries = [];
        _filesRel = '';
      });
      await _fixActiveSessionAfterRefresh(sessions);
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
    return approvals;
  }

  Future<void> _openWeb() async {
    final raw = _webUrlController.text.trim();
    final url = raw.isEmpty ? widget.coreService.resolvedClawcodeWebUrl() : raw.replaceFirst(RegExp(r'/$'), '');
    await widget.coreService.saveClawcodeWebUiUrl(raw.isEmpty ? null : raw);
    final u = Uri.tryParse(url);
    if (u == null || !u.hasScheme) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Invalid URL')));
      }
      return;
    }
    if (!await launchUrl(u, mode: LaunchMode.externalApplication)) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not open browser: $url')));
      }
    }
  }

  Future<void> _loadFiles(String sessionId, {String rel = ''}) async {
    setState(() {
      _filesLoading = true;
      _filesSessionId = sessionId;
      _filesRel = rel;
    });
    try {
      final entries = await widget.coreService.fetchClawcodeWorkspaceFiles(
        sessionId: sessionId,
        ownerUserId: _owner,
        relativePath: rel,
      );
      if (!mounted) return;
      setState(() {
        _fileEntries = entries;
        _filesLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _fileEntries = [];
        _filesLoading = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Files: $e')));
    }
  }

  Future<void> _resolveApproval(String id, String decision) async {
    try {
      await widget.coreService.resolveClawcodeApproval(
        approvalId: id,
        ownerUserId: _owner,
        decision: decision,
      );
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(decision == 'approve' ? 'Approved' : 'Rejected')));
      await _refresh();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  /// PATCH whitelisted session metadata (`git_remote_hint`, `main_llm_ref`, `tool_llm_ref`).
  Future<void> _editSessionHints(BuildContext screenContext, Map<String, dynamic> s) async {
    final sid = (s['clawcode_session_id'] ?? '').toString();
    if (sid.isEmpty) return;

    final gitCtrl = TextEditingController(text: (s['git_remote_hint'] ?? '').toString());
    final mainCtrl = TextEditingController(text: (s['main_llm_ref'] ?? '').toString());
    final toolCtrl = TextEditingController(text: (s['tool_llm_ref'] ?? '').toString());
    var modeVal = (s['mode']?.toString().toLowerCase().trim() == 'plan') ? 'plan' : 'agent';
    var saving = false;

    try {
      await showDialog<void>(
        context: screenContext,
        builder: (dialogCtx) {
          return StatefulBuilder(
            builder: (ctx, setDlg) {
              return AlertDialog(
                title: const Text('Session hints'),
                content: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      InputDecorator(
                        decoration: const InputDecoration(
                          labelText: 'mode',
                          border: OutlineInputBorder(),
                        ),
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<String>(
                            value: modeVal,
                            isExpanded: true,
                            items: const [
                              DropdownMenuItem(value: 'agent', child: Text('agent')),
                              DropdownMenuItem(value: 'plan', child: Text('plan')),
                            ],
                            onChanged: saving
                                ? null
                                : (v) {
                                    if (v != null) setDlg(() => modeVal = v);
                                  },
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: gitCtrl,
                        enabled: !saving,
                        decoration: const InputDecoration(
                          labelText: 'git_remote_hint',
                          border: OutlineInputBorder(),
                        ),
                        maxLines: 2,
                        textInputAction: TextInputAction.next,
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: mainCtrl,
                        enabled: !saving,
                        decoration: const InputDecoration(
                          labelText: 'main_llm_ref',
                          border: OutlineInputBorder(),
                        ),
                        textInputAction: TextInputAction.next,
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: toolCtrl,
                        enabled: !saving,
                        decoration: const InputDecoration(
                          labelText: 'tool_llm_ref',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ],
                  ),
                ),
                actions: [
                  TextButton(
                    onPressed: saving ? null : () => Navigator.pop(dialogCtx),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    onPressed: saving
                        ? null
                        : () async {
                            final body = <String, dynamic>{
                              'git_remote_hint': gitCtrl.text.trim(),
                              'main_llm_ref': mainCtrl.text.trim(),
                              'tool_llm_ref': toolCtrl.text.trim(),
                              'mode': modeVal,
                            };
                            setDlg(() => saving = true);
                            try {
                              await widget.coreService.patchClawcodeSession(
                                sessionId: sid,
                                ownerUserId: _owner,
                                body: body,
                              );
                              if (!dialogCtx.mounted) return;
                              Navigator.pop(dialogCtx);
                              if (!screenContext.mounted) return;
                              ScaffoldMessenger.of(screenContext).showSnackBar(
                                const SnackBar(content: Text('Session hints saved')),
                              );
                              await _refresh();
                            } catch (e) {
                              setDlg(() => saving = false);
                              if (dialogCtx.mounted) {
                                ScaffoldMessenger.of(dialogCtx).showSnackBar(
                                  SnackBar(content: Text('$e')),
                                );
                              }
                            }
                          },
                    child: saving
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Save'),
                  ),
                ],
              );
            },
          );
        },
      );
    } finally {
      gitCtrl.dispose();
      mainCtrl.dispose();
      toolCtrl.dispose();
    }
  }

  /// POST /api/clawcode/sessions/{id}/rebind — new absolute cwd (Core validates allowed_roots).
  Future<void> _rebindSessionCwd(BuildContext screenContext, Map<String, dynamic> s) async {
    final sid = (s['clawcode_session_id'] ?? '').toString();
    if (sid.isEmpty) return;

    final cwdCtrl = TextEditingController(text: (s['cwd'] ?? '').toString());
    var saving = false;

    try {
      await showDialog<void>(
        context: screenContext,
        builder: (dialogCtx) {
          return StatefulBuilder(
            builder: (ctx, setDlg) {
              return AlertDialog(
                title: const Text('Rebind working directory'),
                content: SingleChildScrollView(
                  child: TextField(
                    controller: cwdCtrl,
                    enabled: !saving,
                    decoration: const InputDecoration(
                      labelText: 'cwd (absolute path on Core host)',
                      border: OutlineInputBorder(),
                    ),
                    maxLines: 4,
                    textInputAction: TextInputAction.done,
                  ),
                ),
                actions: [
                  TextButton(
                    onPressed: saving ? null : () => Navigator.pop(dialogCtx),
                    child: const Text('Cancel'),
                  ),
                  FilledButton(
                    onPressed: saving
                        ? null
                        : () async {
                            setDlg(() => saving = true);
                            try {
                              await widget.coreService.rebindClawcodeSession(
                                sessionId: sid,
                                ownerUserId: _owner,
                                cwd: cwdCtrl.text.trim(),
                              );
                              if (!dialogCtx.mounted) return;
                              Navigator.pop(dialogCtx);
                              if (!screenContext.mounted) return;
                              ScaffoldMessenger.of(screenContext).showSnackBar(
                                const SnackBar(content: Text('Session cwd updated')),
                              );
                              await _refresh();
                            } catch (e) {
                              setDlg(() => saving = false);
                              if (dialogCtx.mounted) {
                                ScaffoldMessenger.of(dialogCtx).showSnackBar(
                                  SnackBar(content: Text('$e')),
                                );
                              }
                            }
                          },
                    child: saving
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Rebind'),
                  ),
                ],
              );
            },
          );
        },
      );
    } finally {
      cwdCtrl.dispose();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Claw-Code'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _loading ? null : _refresh, tooltip: 'Refresh'),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextField(
              controller: _webUrlController,
              decoration: const InputDecoration(
                labelText: 'Claw-Code web URL (optional)',
                hintText: 'http://host:9000/clawcode',
                border: OutlineInputBorder(),
                helperText: 'Core serves /clawcode on the same port as the API. Override only if you use a different URL.',
              ),
              keyboardType: TextInputType.url,
              autocorrect: false,
            ),
            const SizedBox(height: 8),
            FilledButton.icon(
              onPressed: _openWeb,
              icon: const Icon(Icons.open_in_browser),
              label: const Text('Open Claw-Code in browser'),
            ),
            const SizedBox(height: 8),
            Text('Owner (Core user id): $_owner', style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 20),
            Text('Run from this screen (optional)', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              widget.chatFriendId != null && widget.chatFriendId!.trim().isNotEmpty
                  ? 'Tip: you can also use the main chat with this friend — terminal icon or More → Claw-Code. Below sends /inbound with clawcode_session_id and friend_id.'
                  : 'Tip: use the main chat — terminal icon or More → Claw-Code — bind a session, then message as usual. Below is an extra compose box on this screen.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            if (_loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Center(child: SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2))),
              )
            else if (_sessions.isEmpty)
              Text(
                'No sessions yet. Create one on the Core host, then pull to refresh.',
                style: Theme.of(context).textTheme.bodySmall,
              )
            else
              DropdownButtonFormField<String>(
                // Controlled selection updates after refresh; initialValue does not track state.
                // ignore: deprecated_member_use
                value: _activeSessionId != null &&
                        _sessions.any((s) => (s['clawcode_session_id'] ?? '').toString() == _activeSessionId)
                    ? _activeSessionId
                    : null,
                decoration: const InputDecoration(
                  labelText: 'Active session',
                  border: OutlineInputBorder(),
                ),
                hint: const Text('Select session'),
                items: _sessions
                    .map((s) => (s['clawcode_session_id'] ?? '').toString())
                    .where((id) => id.isNotEmpty)
                    .map(
                      (id) => DropdownMenuItem<String>(
                        value: id,
                        child: Text(
                          id.length > 20 ? '${id.substring(0, 16)}…' : id,
                          style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
                        ),
                      ),
                    )
                    .toList(),
                onChanged: _sending
                    ? null
                    : (v) {
                        if (v != null) _selectSession(v);
                      },
              ),
            const SizedBox(height: 12),
            TextField(
              controller: _composeController,
              enabled: !_sending,
              decoration: const InputDecoration(
                labelText: 'Message to Claw-Code',
                border: OutlineInputBorder(),
                alignLabelWithHint: true,
              ),
              minLines: 3,
              maxLines: 8,
              textInputAction: TextInputAction.newline,
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.icon(
                  onPressed: _sending ? null : _sendClawcodeInbound,
                  icon: _sending
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.send),
                  label: Text(_sending ? 'Running…' : 'Send'),
                ),
                OutlinedButton.icon(
                  onPressed: _sending ? null : _retryLastCompose,
                  icon: const Icon(Icons.replay),
                  label: const Text('Retry (load last)'),
                ),
                OutlinedButton.icon(
                  onPressed: _sending ? null : () => _showPlanRecoveryDialog(context),
                  icon: const Icon(Icons.flag_outlined),
                  label: const Text('Plan & recovery'),
                ),
                OutlinedButton.icon(
                  onPressed: _sending ? null : () => _showMcpDiagnosticsSheet(context),
                  icon: const Icon(Icons.health_and_safety_outlined),
                  label: const Text('MCP'),
                ),
              ],
            ),
            if (_progressLine.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(_progressLine, style: Theme.of(context).textTheme.bodySmall),
            ],
            const SizedBox(height: 8),
            Row(
              children: [
                Text('Run state: ', style: Theme.of(context).textTheme.bodySmall),
                _CcRunChip(state: _ccRunState),
              ],
            ),
            if (_lastReply.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text('Last reply', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 4),
              SelectableText(_lastReply, style: const TextStyle(fontSize: 13)),
            ],
            const SizedBox(height: 16),
            if (widget.coreService.apiKey == null || widget.coreService.apiKey!.isEmpty)
              Card(
                color: Theme.of(context).colorScheme.errorContainer,
                child: const Padding(
                  padding: EdgeInsets.all(12),
                  child: Text('Set an API key in Settings if Core has auth_enabled — Claw-Code REST uses the same key as /inbound.'),
                ),
              ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
            const SizedBox(height: 16),
            Text('Pending approvals', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (_approvals.isEmpty)
              Text('None', style: Theme.of(context).textTheme.bodySmall)
            else
              ..._approvals.map((a) {
                final id = (a['approval_id'] ?? '').toString();
                final tool = (a['tool_name'] ?? '').toString();
                final sum = (a['summary'] ?? '').toString();
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(tool, style: const TextStyle(fontWeight: FontWeight.bold)),
                        if (sum.isNotEmpty) Text(sum, style: Theme.of(context).textTheme.bodySmall),
                        Row(
                          children: [
                            TextButton(onPressed: id.isEmpty ? null : () => _resolveApproval(id, 'approve'), child: const Text('Approve')),
                            TextButton(onPressed: id.isEmpty ? null : () => _resolveApproval(id, 'reject'), child: const Text('Reject')),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              }),
            const SizedBox(height: 24),
            Text('Sessions', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (_loading)
              const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator()))
            else if (_sessions.isEmpty)
              Text('No sessions for this owner. Create one with: python3 -m main clawcode session new', style: Theme.of(context).textTheme.bodySmall)
            else
              ..._sessions.map((s) {
                final sid = (s['clawcode_session_id'] ?? '').toString();
                final cwd = (s['cwd'] ?? '').toString();
                final mode = (s['mode'] ?? 'agent').toString();
                final lr = (s['last_run_id'] ?? '').toString();
                final st = (s['status'] ?? '').toString();
                final lu = _formatClawcodeLastUsage(s['last_usage']);
                return Card(
                  child: ExpansionTile(
                    title: Text(sid.length > 12 ? '${sid.substring(0, 8)}…' : sid, style: const TextStyle(fontFamily: 'monospace', fontSize: 13)),
                    subtitle: Text('$mode · $cwd', maxLines: 2, overflow: TextOverflow.ellipsis),
                    children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                        child: SelectableText(
                          'mode: $mode\nlast_run: ${lr.isEmpty ? '—' : lr}\nstatus: $st\nlast_usage: $lu\n\n$cwd',
                          style: const TextStyle(fontSize: 12),
                        ),
                      ),
                      if (sid.isNotEmpty) ...[
                        ListTile(
                          leading: const Icon(Icons.edit_note),
                          title: const Text('Edit session hints'),
                          subtitle: const Text('mode, git remote, main/tool LLM refs (PATCH)'),
                          onTap: () => _editSessionHints(context, s),
                        ),
                        ListTile(
                          leading: const Icon(Icons.drive_file_move_outline),
                          title: const Text('Rebind cwd'),
                          subtitle: const Text('Change session working directory on Core'),
                          onTap: () => _rebindSessionCwd(context, s),
                        ),
                        ListTile(
                          leading: const Icon(Icons.folder_open),
                          title: const Text('Load workspace files'),
                          onTap: () => _loadFiles(sid, rel: ''),
                        ),
                      ],
                      if (_filesSessionId == sid) ...[
                        if (_filesRel.isNotEmpty)
                          ListTile(
                            dense: true,
                            leading: const Icon(Icons.arrow_upward),
                            title: const Text('Up'),
                            onTap: () {
                              final parts = _filesRel.split('/')..removeWhere((e) => e.isEmpty);
                              parts.removeLast();
                              _loadFiles(sid, rel: parts.join('/'));
                            },
                          ),
                        if (_filesLoading)
                          const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator()))
                        else
                          ..._fileEntries.map((e) {
                            final name = (e['name'] ?? '').toString();
                            final t = (e['type'] ?? '').toString();
                            final isDir = t == 'directory';
                            return ListTile(
                              dense: true,
                              leading: Icon(isDir ? Icons.folder : Icons.insert_drive_file),
                              title: Text(name, style: const TextStyle(fontFamily: 'monospace', fontSize: 13)),
                              onTap: isDir
                                  ? () {
                                      final next = _filesRel.isEmpty ? name : '$_filesRel/$name';
                                      _loadFiles(sid, rel: next);
                                    }
                                  : null,
                            );
                          }),
                      ],
                    ],
                  ),
                );
              }),
          ],
        ),
      ),
    );
  }
}

class _CcRunChip extends StatelessWidget {
  const _CcRunChip({required this.state});

  final CcRunState state;

  @override
  Widget build(BuildContext context) => CcRunChip(state: state);
}

class _ClawcodeMcpSheet extends StatefulWidget {
  const _ClawcodeMcpSheet({required this.coreService});

  final CoreService coreService;

  @override
  State<_ClawcodeMcpSheet> createState() => _ClawcodeMcpSheetState();
}

class _ClawcodeMcpSheetState extends State<_ClawcodeMcpSheet> {
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _servers = [];
  bool _mcpEnabled = false;
  bool _healthBusy = false;
  List<Map<String, dynamic>> _healthResults = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final m = await widget.coreService.fetchClawcodeMcpServers();
      final list = m['servers'];
      final servers = <Map<String, dynamic>>[];
      if (list is List) {
        for (final e in list) {
          if (e is Map<String, dynamic>) {
            servers.add(e);
          } else if (e is Map) {
            servers.add(Map<String, dynamic>.from(e));
          }
        }
      }
      if (!mounted) return;
      setState(() {
        _mcpEnabled = m['mcp_enabled'] == true;
        _servers = servers;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _health() async {
    setState(() {
      _healthBusy = true;
      _healthResults = [];
    });
    try {
      final m = await widget.coreService.postClawcodeMcpHealth();
      final list = m['results'];
      final out = <Map<String, dynamic>>[];
      if (list is List) {
        for (final e in list) {
          if (e is Map<String, dynamic>) {
            out.add(e);
          } else if (e is Map) {
            out.add(Map<String, dynamic>.from(e));
          }
        }
      }
      if (!mounted) return;
      setState(() {
        _healthResults = out;
        _healthBusy = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _healthBusy = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final h = MediaQuery.sizeOf(context).height * 0.55;
    return SafeArea(
      child: SizedBox(
        height: h,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('MCP diagnostics', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              if (_loading)
                const Expanded(child: Center(child: CircularProgressIndicator()))
              else ...[
                Text('mcp_enabled: $_mcpEnabled', style: Theme.of(context).textTheme.bodySmall),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error, fontSize: 12)),
                  ),
                Row(
                  children: [
                    TextButton(onPressed: _load, child: const Text('Refresh list')),
                    const Spacer(),
                    FilledButton(
                      onPressed: _healthBusy ? null : _health,
                      child: _healthBusy
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Check health (all)'),
                    ),
                  ],
                ),
                Expanded(
                  child: ListView(
                    children: [
                      ..._servers.map((s) {
                        final id = (s['server_id'] ?? '').toString();
                        final t = (s['transport'] ?? '').toString();
                        final cmd = (s['command'] ?? '').toString();
                        return ListTile(
                          dense: true,
                          title: Text(id, style: const TextStyle(fontFamily: 'monospace', fontSize: 13)),
                          subtitle: Text(
                            '$t${cmd.isNotEmpty ? ' · $cmd' : ''}',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        );
                      }),
                      if (_healthResults.isNotEmpty) ...[
                        const Divider(height: 24),
                        Text('Health', style: Theme.of(context).textTheme.titleSmall),
                        ..._healthResults.map((r) {
                          final ok = r['ok'] == true;
                          final sid = (r['server_id'] ?? '').toString();
                          final err = (r['error'] ?? '').toString();
                          final n = r['tool_count'];
                          return ListTile(
                            dense: true,
                            leading: Icon(
                              ok ? Icons.check_circle_outline : Icons.error_outline,
                              color: ok ? Colors.green : Theme.of(context).colorScheme.error,
                            ),
                            title: Text(sid, style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
                            subtitle: Text(ok ? 'list_tools count: $n' : err),
                          );
                        }),
                      ],
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
