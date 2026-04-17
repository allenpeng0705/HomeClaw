import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../core_service.dart';

/// Parent of [currentPath] for Dev Bridge project listing (`'.'` = project root).
String bridgeProjectParentPath(String currentPath) {
  if (currentPath == '.' || currentPath.isEmpty) return '.';
  final parts = currentPath.split('/').where((s) => s.isNotEmpty).toList();
  if (parts.isEmpty) return '.';
  parts.removeLast();
  return parts.isEmpty ? '.' : parts.join('/');
}

/// Cursor / Claude Code: browse active Dev Bridge project (GET /api/cursor-bridge/project-list).
class BridgeProjectFilesExplorer extends StatefulWidget {
  final CoreService coreService;
  /// `cursor` or `claude` (maps to API backend).
  final String bridgeBackend;
  final void Function(String absolutePathOnDevMachine) onInsertPath;
  final void Function(String absolutePathOnDevMachine) onAttachForNextSend;

  const BridgeProjectFilesExplorer({
    super.key,
    required this.coreService,
    required this.bridgeBackend,
    required this.onInsertPath,
    required this.onAttachForNextSend,
  });

  @override
  State<BridgeProjectFilesExplorer> createState() => _BridgeProjectFilesExplorerState();
}

class _BridgeProjectFilesExplorerState extends State<BridgeProjectFilesExplorer> {
  String _currentPath = '.';
  BridgeProjectListResult? _result;
  String? _error;
  bool _loading = true;
  BridgeProjectListEntry? _selected;
  bool _attachBusy = false;
  bool _openBrowserBusy = false;
  bool _openFromRootBusy = false;

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
      final r = await widget.coreService.fetchBridgeProjectList(
        backend: widget.bridgeBackend,
        path: _currentPath,
      );
      if (!mounted) return;
      setState(() {
        _result = r;
        _loading = false;
        _error = r.error;
        _selected = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString().replaceFirst(RegExp(r'^Exception:\s*'), '');
        _loading = false;
        _result = null;
      });
    }
  }

  void _openDir(String name) {
    final next = _currentPath == '.' ? name : '$_currentPath/$name';
    setState(() => _currentPath = next);
    _load();
  }

  void _goUp() {
    final p = bridgeProjectParentPath(_currentPath);
    setState(() => _currentPath = p);
    _load();
  }

  Future<void> _showRootBrowserDialog() async {
    if (_openFromRootBusy) return;
    setState(() => _openFromRootBusy = true);
    try {
      await showDialog<void>(
        context: context,
        builder: (ctx) => _BridgeRootBrowserDialog(
          coreService: widget.coreService,
          backend: widget.bridgeBackend,
          onSelectFolder: (absPath) async {
            if (!mounted) return;
            final activeRoot = (_result?.root ?? '').trim().replaceAll('\\', '/');
            if (activeRoot.isEmpty) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('No active project yet. Open one from the top active-project chip.')),
              );
              return;
            }
            final r = absPath.trim().replaceAll('\\', '/');
            final rootNorm = activeRoot.endsWith('/') ? activeRoot.substring(0, activeRoot.length - 1) : activeRoot;
            final rel = (r == rootNorm)
                ? '.'
                : (r.startsWith('$rootNorm/') ? r.substring(rootNorm.length + 1) : '');
            if (rel.isEmpty && r != rootNorm) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('That folder is outside the active project. Use the top active-project chip to switch project.'),
                ),
              );
              return;
            }
            setState(() => _currentPath = rel.isEmpty ? '.' : rel);
            await _load();
          },
        ),
      );
    } finally {
      if (mounted) setState(() => _openFromRootBusy = false);
    }
  }

  bool get _isImageName {
    final n = _selected?.name.toLowerCase() ?? '';
    return n.endsWith('.png') ||
        n.endsWith('.jpg') ||
        n.endsWith('.jpeg') ||
        n.endsWith('.gif') ||
        n.endsWith('.webp');
  }

  bool get _isTextPreviewName {
    final n = _selected?.name.toLowerCase() ?? '';
    return n.endsWith('.txt') ||
        n.endsWith('.md') ||
        n.endsWith('.csv') ||
        n.endsWith('.json') ||
        n.endsWith('.log') ||
        n.endsWith('.yml') ||
        n.endsWith('.yaml') ||
        n.endsWith('.xml') ||
        n.endsWith('.dart') ||
        n.endsWith('.py') ||
        n.endsWith('.ts') ||
        n.endsWith('.tsx') ||
        n.endsWith('.js') ||
        n.endsWith('.jsx') ||
        n.endsWith('.css') ||
        n.endsWith('.html') ||
        n.endsWith('.htm') ||
        n.endsWith('.rs') ||
        n.endsWith('.go') ||
        n.endsWith('.java') ||
        n.endsWith('.kt') ||
        n.endsWith('.swift') ||
        n.endsWith('.c') ||
        n.endsWith('.h') ||
        n.endsWith('.cpp') ||
        n.endsWith('.sh') ||
        n.endsWith('.toml') ||
        n.endsWith('.gradle') ||
        n.endsWith('.properties');
  }

  bool get _isMarkdownName {
    final n = _selected?.name.toLowerCase() ?? '';
    return n.endsWith('.md') || n.endsWith('.markdown');
  }

  bool get _isPdfName {
    final n = _selected?.name.toLowerCase() ?? '';
    return n.endsWith('.pdf');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (_error != null && _error!.isNotEmpty && !_loading) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.folder_off_outlined, size: 48, color: theme.colorScheme.error),
              const SizedBox(height: 12),
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    final rootLabel = _result?.root.isNotEmpty == true ? _result!.root : '(no project)';

    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 720;
        final listPane = Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
              child: Row(
                children: [
                  IconButton(
                    tooltip: 'Up',
                    onPressed: _currentPath == '.' ? null : _goUp,
                    icon: const Icon(Icons.arrow_upward),
                  ),
                  Expanded(
                    child: Text(
                      '$rootLabel\n${_currentPath == '.' ? '(root)' : _currentPath}',
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleSmall,
                    ),
                  ),
                  IconButton(
                    tooltip: 'Choose review folder',
                    onPressed: _loading ? null : _showRootBrowserDialog,
                    icon: _openFromRootBusy
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.folder_open),
                  ),
                  IconButton(
                    tooltip: 'Refresh',
                    onPressed: _loading ? null : _load,
                    icon: const Icon(Icons.refresh),
                  ),
                ],
              ),
            ),
            if (_loading)
              const Expanded(
                child: Center(child: CircularProgressIndicator()),
              )
            else
              Expanded(
                child: ListView.builder(
                  itemCount: _result?.entries.length ?? 0,
                  itemBuilder: (context, i) {
                    final e = _result!.entries[i];
                    final isDir = e.type == 'dir';
                    final sel = _selected?.relPath == e.relPath;
                    return ListTile(
                      selected: sel,
                      leading: Icon(isDir ? Icons.folder_outlined : Icons.insert_drive_file_outlined),
                      title: Text(e.name),
                      subtitle: isDir
                          ? const Text('Folder')
                          : Text(e.size != null ? '${e.size} bytes' : 'File'),
                      onTap: () {
                        if (isDir) {
                          _openDir(e.name);
                        } else {
                          setState(() => _selected = e);
                        }
                      },
                      onLongPress: () {
                        if (!isDir && e.absPath.isNotEmpty) {
                          widget.onInsertPath(e.absPath);
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text('Inserted path: ${e.absPath}')),
                          );
                        }
                      },
                    );
                  },
                ),
              ),
          ],
        );

        final previewPane = _selected == null || _selected!.type == 'dir'
            ? Center(
                child: Text(
                  'Select a file for preview and actions',
                  style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
              )
            : _buildPreview(context);

        if (wide) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(width: constraints.maxWidth * 0.42, child: listPane),
              VerticalDivider(width: 1, color: theme.colorScheme.outlineVariant),
              Expanded(child: previewPane),
            ],
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(height: constraints.maxHeight * 0.45, child: listPane),
            const Divider(height: 1),
            Expanded(child: previewPane),
          ],
        );
      },
    );
  }

  Widget _buildPreview(BuildContext context) {
    final e = _selected!;
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(e.name, style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          SelectableText(
            e.absPath,
            style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.tonalIcon(
                onPressed: () {
                  widget.onInsertPath(e.absPath);
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Inserted: ${e.absPath}')));
                },
                icon: const Icon(Icons.text_fields, size: 18),
                label: const Text('Insert path'),
              ),
              FilledButton.icon(
                onPressed: _attachBusy
                    ? null
                    : () async {
                        setState(() => _attachBusy = true);
                        try {
                          widget.onAttachForNextSend(e.absPath);
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Attached — add a message if needed, then Send')),
                            );
                          }
                        } finally {
                          if (mounted) setState(() => _attachBusy = false);
                        }
                      },
                icon: _attachBusy
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.attach_file, size: 18),
                label: Text(_attachBusy ? '…' : 'Attach to next send'),
              ),
              OutlinedButton.icon(
                onPressed: _openBrowserBusy
                    ? null
                    : () async {
                        setState(() => _openBrowserBusy = true);
                        try {
                          final viewUrl = await widget.coreService.fetchBridgeProjectBrowserUrl(
                            backend: widget.bridgeBackend,
                            relativePath: e.relPath,
                          );
                          final uri = Uri.parse(viewUrl);
                          if (!context.mounted) return;
                          final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
                          if (!context.mounted) return;
                          if (!ok) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Could not open browser')),
                            );
                          }
                        } catch (err) {
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(content: Text('Open in browser failed: $err')),
                            );
                          }
                        } finally {
                          if (mounted) setState(() => _openBrowserBusy = false);
                        }
                      },
                icon: _openBrowserBusy
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.open_in_browser, size: 18),
                label: Text(_openBrowserBusy ? '…' : 'Open in browser'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (_isImageName)
            FutureBuilder<String>(
              future: widget.coreService.fetchBridgeProjectBrowserUrl(
                backend: widget.bridgeBackend,
                relativePath: e.relPath,
              ),
              builder: (context, snap) {
                if (snap.connectionState != ConnectionState.done) {
                  return const Padding(
                    padding: EdgeInsets.all(24),
                    child: Center(child: CircularProgressIndicator()),
                  );
                }
                if (snap.hasError || (snap.data?.isEmpty ?? true)) {
                  return Text(
                    snap.hasError ? snap.error.toString() : 'Could not get preview URL',
                    style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
                  );
                }
                return ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: Image.network(
                    snap.data!,
                    fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => const Text('Could not load image'),
                  ),
                );
              },
            )
          else if (_isPdfName)
            FutureBuilder<String>(
              future: widget.coreService.fetchBridgeProjectBrowserUrl(
                backend: widget.bridgeBackend,
                relativePath: e.relPath,
              ),
              builder: (context, snap) {
                if (snap.connectionState != ConnectionState.done) {
                  return const Padding(
                    padding: EdgeInsets.all(24),
                    child: Center(child: CircularProgressIndicator()),
                  );
                }
                if (snap.hasError || (snap.data?.isEmpty ?? true)) {
                  return Text(
                    snap.hasError ? snap.error.toString() : 'Could not get PDF preview URL',
                    style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
                  );
                }
                final ctrl = WebViewController()
                  ..setJavaScriptMode(JavaScriptMode.unrestricted)
                  ..loadRequest(Uri.parse(snap.data!));
                return SizedBox(
                  height: 520,
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: WebViewWidget(controller: ctrl),
                  ),
                );
              },
            )
          else if (_isTextPreviewName)
            FutureBuilder<BridgeProjectFilePreview>(
              future: widget.coreService.fetchBridgeProjectFilePreview(
                backend: widget.bridgeBackend,
                relativePath: e.relPath,
              ),
              builder: (context, snap) {
                if (snap.connectionState != ConnectionState.done) {
                  return const Padding(
                    padding: EdgeInsets.all(24),
                    child: Center(child: CircularProgressIndicator()),
                  );
                }
                final prev = snap.data;
                if (prev == null || (prev.error != null && prev.error!.isNotEmpty)) {
                  return Text(
                    prev?.error ?? 'Preview failed',
                    style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
                  );
                }
                var s = prev.content;
                if (s.length > 48000) s = '${s.substring(0, 48000)}…';
                if (_isMarkdownName) {
                  return MarkdownBody(selectable: true, data: s);
                }
                return SelectableText(s, style: theme.textTheme.bodySmall?.copyWith(fontFamily: 'monospace'));
              },
            )
          else
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                e.name.toLowerCase().endsWith('.pdf')
                    ? 'PDF is not previewed inline here. Tap Open in browser to view in Safari/Chrome, or Attach to next send.'
                    : 'Preview not available for this type. Try Open in browser (PDF, Office, etc.), or Insert path / Attach.',
                style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            ),
        ],
      ),
    );
  }
}

class _BridgeRootBrowserDialog extends StatefulWidget {
  final CoreService coreService;
  final String backend;
  final Future<void> Function(String absPath) onSelectFolder;

  const _BridgeRootBrowserDialog({
    required this.coreService,
    required this.backend,
    required this.onSelectFolder,
  });

  @override
  State<_BridgeRootBrowserDialog> createState() => _BridgeRootBrowserDialogState();
}

class _BridgeRootBrowserDialogState extends State<_BridgeRootBrowserDialog> {
  BridgeRootListResult? _data;
  String _path = '.';
  String? _error;
  bool _loading = true;
  String? _openingPath;
  String? _selectedDirAbsPath;

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
      final r = await widget.coreService.fetchBridgeRootList(backend: widget.backend, path: _path);
      if (!mounted) return;
      setState(() {
        _data = r;
        _loading = false;
        _error = r.error;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString().replaceFirst(RegExp(r'^Exception:\s*'), '');
      });
    }
  }

  void _goUp() {
    if (_path == '.' || _path.isEmpty) return;
    final parts = _path.split('/').where((s) => s.isNotEmpty).toList();
    if (parts.isNotEmpty) {
      parts.removeLast();
    }
    setState(() => _path = parts.isEmpty ? '.' : parts.join('/'));
    _load();
  }

  Future<void> _useSelectedFolder(String absPath) async {
    setState(() => _openingPath = absPath);
    try {
      await widget.onSelectFolder(absPath);
      if (!mounted) return;
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Review folder: $absPath')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Open failed: $e')));
    } finally {
      if (mounted) setState(() => _openingPath = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Choose folder to review'),
      content: SizedBox(
        width: 560,
        height: 420,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '${_data?.root ?? "(root unknown)"}\n${_path == "." ? "(root)" : _path}',
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                IconButton(onPressed: _path == '.' || _loading ? null : _goUp, icon: const Icon(Icons.arrow_upward)),
                IconButton(onPressed: _loading ? null : _load, icon: const Icon(Icons.refresh)),
              ],
            ),
            const Divider(height: 1),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : (_error != null && _error!.isNotEmpty)
                      ? Center(child: Text(_error!, textAlign: TextAlign.center))
                      : ListView.builder(
                          itemCount: _data?.entries.length ?? 0,
                          itemBuilder: (context, i) {
                            final e = _data!.entries[i];
                            final isDir = e.type == 'dir';
                            final selected = isDir && _selectedDirAbsPath == e.absPath;
                            return ListTile(
                              selected: selected,
                              leading: Icon(isDir ? Icons.folder_outlined : Icons.insert_drive_file_outlined),
                              title: Text(e.name),
                              subtitle: Text(e.relPath),
                              onTap: !isDir
                                  ? null
                                  : () {
                                      setState(() => _selectedDirAbsPath = e.absPath);
                                    },
                              trailing: !isDir
                                  ? null
                                  : TextButton.icon(
                                      onPressed: () {
                                        setState(() => _path = e.relPath);
                                        _load();
                                      },
                                      icon: const Icon(Icons.chevron_right, size: 16),
                                      label: const Text('Browse'),
                                    ),
                            );
                          },
                        ),
            ),
          ],
        ),
      ),
      actions: [
        FilledButton.icon(
          onPressed: (_openingPath != null || _selectedDirAbsPath == null)
              ? null
              : () => _useSelectedFolder(_selectedDirAbsPath!),
          icon: _openingPath == null
              ? const Icon(Icons.check, size: 16)
              : const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
          label: const Text('Use selected'),
        ),
        TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Close')),
      ],
    );
  }
}
