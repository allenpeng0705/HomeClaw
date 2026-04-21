import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../core_service.dart';
import '../providers/bridge_project_providers.dart';
import '../utils/file_preview_utils.dart';

/// Parent of [currentPath] for Dev Bridge project listing (`'.'` = project root).
String bridgeProjectParentPath(String currentPath) {
  if (currentPath == '.' || currentPath.isEmpty) return '.';
  final parts = currentPath.split('/').where((s) => s.isNotEmpty).toList();
  if (parts.isEmpty) return '.';
  parts.removeLast();
  return parts.isEmpty ? '.' : parts.join('/');
}

/// Cursor / Claude Code: browse active Dev Bridge project (GET /api/cursor-bridge/project-list).
class BridgeProjectFilesExplorer extends ConsumerStatefulWidget {
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
  ConsumerState<BridgeProjectFilesExplorer> createState() =>
      _BridgeProjectFilesExplorerState();
}

class _BridgeProjectFilesExplorerState extends ConsumerState<BridgeProjectFilesExplorer> {
  String _currentPath = '.';

  bool _isMobilePreviewMode(BuildContext context) =>
      MediaQuery.of(context).size.shortestSide < 600;

  Future<void> _openMobilePreviewPage(BridgeProjectListEntry entry) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => _BridgeFilePreviewPage(
          coreService: widget.coreService,
          bridgeBackend: widget.bridgeBackend,
          entry: entry,
          onInsertPath: widget.onInsertPath,
          onAttachForNextSend: widget.onAttachForNextSend,
        ),
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final notifier = ref.read(bridgeProjectProvider(widget.bridgeBackend).notifier);
    notifier.setLoading(true);
    try {
      final r = await widget.coreService.fetchBridgeProjectList(
        backend: widget.bridgeBackend,
        path: _currentPath,
      );
      if (!mounted) return;
      notifier.setResult(r);
    } catch (e) {
      if (!mounted) return;
      notifier.setError(e.toString().replaceFirst(RegExp(r'^Exception:\s*'), ''));
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
    final state = ref.read(bridgeProjectProvider(widget.bridgeBackend));
    if (state.openFromRootBusy) return;
    ref.read(bridgeProjectProvider(widget.bridgeBackend).notifier).setOpenFromRootBusy(true);
    try {
      await showDialog<void>(
        context: context,
        builder: (ctx) => _BridgeRootBrowserDialog(
          coreService: widget.coreService,
          backend: widget.bridgeBackend,
          onSelectFolder: (absPath) async {
            if (!mounted) return;
            final activeRoot =
                (state.result?.root ?? '').trim().replaceAll('\\', '/');
            if (activeRoot.isEmpty) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                    content: Text(
                        'No active project yet. Open one from the top active-project chip.')),
              );
              return;
            }
            final r = absPath.trim().replaceAll('\\', '/');
            final rootNorm = activeRoot.endsWith('/')
                ? activeRoot.substring(0, activeRoot.length - 1)
                : activeRoot;
            final rel = (r == rootNorm)
                ? '.'
                : (r.startsWith('$rootNorm/')
                    ? r.substring(rootNorm.length + 1)
                    : '');
            if (rel.isEmpty && r != rootNorm) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text(
                      'That folder is outside the active project. Use the top active-project chip to switch project.'),
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
      ref.read(bridgeProjectProvider(widget.bridgeBackend).notifier).setOpenFromRootBusy(false);
    }
  }

  BridgeProjectState get _cs => ref.watch(bridgeProjectProvider(widget.bridgeBackend));

  bool get _isImageName => isDisplayableImageName(_cs.selected?.name ?? '');
  bool get _isTextPreviewName => isTextPreviewName(_cs.selected?.name ?? '');
  bool get _isMarkdownName => isMarkdownName(_cs.selected?.name ?? '');
  bool get _isPdfName => isPdfName(_cs.selected?.name ?? '');

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final state = _cs;
    final mobilePreviewMode = _isMobilePreviewMode(context);
    if (state.error != null && state.error!.isNotEmpty && !state.loading) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.folder_off_outlined,
                  size: 48, color: theme.colorScheme.error),
              const SizedBox(height: 12),
              Text(state.error!, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    final rootLabel =
        state.result?.root.isNotEmpty == true ? state.result!.root : '(no project)';

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
                    onPressed: state.loading ? null : _showRootBrowserDialog,
                    icon: state.openFromRootBusy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.folder_open),
                  ),
                  IconButton(
                    tooltip: 'Refresh',
                    onPressed: state.loading ? null : _load,
                    icon: const Icon(Icons.refresh),
                  ),
                ],
              ),
            ),
            if (state.loading)
              const Expanded(
                child: Center(child: CircularProgressIndicator()),
              )
            else
              Expanded(
                child: ListView.builder(
                  itemCount: state.result?.entries.length ?? 0,
                  itemBuilder: (context, i) {
                    final e = state.result!.entries[i];
                    final isDir = e.type == 'dir';
                    final sel = state.selected?.relPath == e.relPath;
                    return ListTile(
                      selected: sel,
                      leading: Icon(isDir
                          ? Icons.folder_outlined
                          : Icons.insert_drive_file_outlined),
                      title: Text(e.name),
                      subtitle: isDir
                          ? const Text('Folder')
                          : Text(e.size != null ? '${e.size} bytes' : 'File'),
                      onTap: () {
                        if (isDir) {
                          _openDir(e.name);
                        } else {
                          if (mobilePreviewMode) {
                            _openMobilePreviewPage(e);
                          } else {
                            setState(() {
                              ref.read(bridgeProjectProvider(widget.bridgeBackend).notifier).setSelected(e);
                            });
                          }
                        }
                      },
                      onLongPress: () {
                        if (!isDir && e.absPath.isNotEmpty) {
                          widget.onInsertPath(e.absPath);
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                                content: Text('Inserted path: ${e.absPath}')),
                          );
                        }
                      },
                    );
                  },
                ),
              ),
          ],
        );

        final previewPane = state.selected == null || state.selected!.type == 'dir'
            ? Center(
                child: Text(
                  'Select a file for preview and actions',
                  style: theme.textTheme.bodyMedium
                      ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
              )
            : _buildPreview(context);

        if (wide) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(width: constraints.maxWidth * 0.42, child: listPane),
              VerticalDivider(
                  width: 1, color: theme.colorScheme.outlineVariant),
              Expanded(child: previewPane),
            ],
          );
        }
        if (mobilePreviewMode) {
          return listPane;
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
    final state = ref.watch(bridgeProjectProvider(widget.bridgeBackend));
    final e = state.selected!;
    final attachBusy = state.attachBusy;
    final openBrowserBusy = state.openBrowserBusy;
    final theme = Theme.of(context);
    Widget body;
    if (_isImageName) {
      body = FutureBuilder<String>(
        future: widget.coreService.fetchBridgeProjectBrowserUrl(
          backend: widget.bridgeBackend,
          relativePath: e.relPath,
        ),
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError || (snap.data?.isEmpty ?? true)) {
            return Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
              child: Text(
                snap.hasError
                    ? snap.error.toString()
                    : 'Could not get preview URL',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              ),
            );
          }
          return SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.network(
                snap.data!,
                fit: BoxFit.contain,
                errorBuilder: (_, __, ___) =>
                    const Text('Could not load image'),
              ),
            ),
          );
        },
      );
    } else if (_isPdfName) {
      body = Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        child: FutureBuilder<String>(
          future: widget.coreService.fetchBridgeProjectBrowserUrl(
            backend: widget.bridgeBackend,
            relativePath: e.relPath,
          ),
          builder: (context, snap) {
            if (snap.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snap.hasError || (snap.data?.isEmpty ?? true)) {
              return Text(
                snap.hasError
                    ? snap.error.toString()
                    : 'Could not get PDF preview URL',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              );
            }
            final ctrl = WebViewController()
              ..setJavaScriptMode(JavaScriptMode.unrestricted)
              ..loadRequest(Uri.parse(snap.data!));
            return ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: WebViewWidget(controller: ctrl),
            );
          },
        ),
      );
    } else if (_isTextPreviewName) {
      body = FutureBuilder<BridgeProjectFilePreview>(
        future: widget.coreService.fetchBridgeProjectFilePreview(
          backend: widget.bridgeBackend,
          relativePath: e.relPath,
        ),
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          final prev = snap.data;
          if (prev == null || (prev.error != null && prev.error!.isNotEmpty)) {
            return Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
              child: Text(
                prev?.error ?? 'Preview failed',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              ),
            );
          }
          var s = prev.content;
          if (s.length > 48000) s = '${s.substring(0, 48000)}…';
          return SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: _isMarkdownName
                ? MarkdownBody(selectable: true, data: s)
                : SelectableText(s,
                    style: theme.textTheme.bodySmall
                        ?.copyWith(fontFamily: 'monospace')),
          );
        },
      );
    } else {
      body = SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Text(
            e.name.toLowerCase().endsWith('.pdf')
                ? 'PDF is not previewed inline here. Tap Open in browser to view in Safari/Chrome, or Attach to next send.'
                : 'Preview not available for this type. Try Open in browser (PDF, Office, etc.), or Insert path / Attach.',
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(e.name, style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          SelectableText(
            e.absPath,
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.tonalIcon(
                onPressed: () {
                  widget.onInsertPath(e.absPath);
                  ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text('Inserted: ${e.absPath}')));
                },
                icon: const Icon(Icons.text_fields, size: 18),
                label: const Text('Insert path'),
              ),
              FilledButton.icon(
                onPressed: attachBusy
                    ? null
                    : () async {
                        ref.read(bridgeProjectProvider(widget.bridgeBackend).notifier).setAttachBusy(true);
                        try {
                          widget.onAttachForNextSend(e.absPath);
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                  content: Text(
                                      'Attached — add a message if needed, then Send')),
                            );
                          }
                        } finally {
                          ref.read(bridgeProjectProvider(widget.bridgeBackend).notifier).setAttachBusy(false);
                        }
                      },
                icon: attachBusy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.attach_file, size: 18),
                label: Text(attachBusy ? '…' : 'Attach to next send'),
              ),
              OutlinedButton.icon(
                onPressed: openBrowserBusy
                    ? null
                    : () async {
                        ref.read(bridgeProjectProvider(widget.bridgeBackend).notifier).setOpenBrowserBusy(true);
                        try {
                          final viewUrl = await widget.coreService
                              .fetchBridgeProjectBrowserUrl(
                            backend: widget.bridgeBackend,
                            relativePath: e.relPath,
                          );
                          final uri = Uri.parse(viewUrl);
                          if (!context.mounted) return;
                          final ok = await launchUrl(uri,
                              mode: LaunchMode.externalApplication);
                          if (!context.mounted) return;
                          if (!ok) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                  content: Text('Could not open browser')),
                            );
                          }
                        } catch (err) {
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                  content:
                                      Text('Open in browser failed: $err')),
                            );
                          }
                        } finally {
                          ref.read(bridgeProjectProvider(widget.bridgeBackend).notifier).setOpenBrowserBusy(false);
                        }
                      },
                icon: openBrowserBusy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.open_in_browser, size: 18),
                label: Text(openBrowserBusy ? '…' : 'Open in browser'),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Expanded(child: body),
        ],
      ),
    );
  }
}

class _BridgeFilePreviewPage extends ConsumerStatefulWidget {
  final CoreService coreService;
  final String bridgeBackend;
  final BridgeProjectListEntry entry;
  final void Function(String absolutePathOnDevMachine) onInsertPath;
  final void Function(String absolutePathOnDevMachine) onAttachForNextSend;

  const _BridgeFilePreviewPage({
    required this.coreService,
    required this.bridgeBackend,
    required this.entry,
    required this.onInsertPath,
    required this.onAttachForNextSend,
  });

  @override
  ConsumerState<_BridgeFilePreviewPage> createState() => _BridgeFilePreviewPageState();
}

class _BridgeFilePreviewPageState extends ConsumerState<_BridgeFilePreviewPage> {
  bool get _attachBusy =>
      ref.watch(bridgeFilePreviewAttachBusyProvider(widget.bridgeBackend));
  bool get _openBrowserBusy =>
      ref.watch(bridgeFilePreviewBrowserBusyProvider(widget.bridgeBackend));

  bool get _isImageName => isDisplayableImageName(widget.entry.name);
  bool get _isTextPreviewName => isTextPreviewName(widget.entry.name);
  bool get _isMarkdownName => isMarkdownName(widget.entry.name);
  bool get _isPdfName => isPdfName(widget.entry.name);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final e = widget.entry;

    Widget body;
    if (_isImageName) {
      body = FutureBuilder<String>(
        future: widget.coreService.fetchBridgeProjectBrowserUrl(
          backend: widget.bridgeBackend,
          relativePath: e.relPath,
        ),
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError || (snap.data?.isEmpty ?? true)) {
            return Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
              child: Text(
                snap.hasError
                    ? snap.error.toString()
                    : 'Could not get preview URL',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              ),
            );
          }
          return SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.network(
                snap.data!,
                fit: BoxFit.contain,
                errorBuilder: (_, __, ___) =>
                    const Text('Could not load image'),
              ),
            ),
          );
        },
      );
    } else if (_isPdfName) {
      body = Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        child: FutureBuilder<String>(
          future: widget.coreService.fetchBridgeProjectBrowserUrl(
            backend: widget.bridgeBackend,
            relativePath: e.relPath,
          ),
          builder: (context, snap) {
            if (snap.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snap.hasError || (snap.data?.isEmpty ?? true)) {
              return Text(
                snap.hasError
                    ? snap.error.toString()
                    : 'Could not get PDF preview URL',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              );
            }
            final ctrl = WebViewController()
              ..setJavaScriptMode(JavaScriptMode.unrestricted)
              ..loadRequest(Uri.parse(snap.data!));
            return ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: WebViewWidget(controller: ctrl),
            );
          },
        ),
      );
    } else if (_isTextPreviewName) {
      body = FutureBuilder<BridgeProjectFilePreview>(
        future: widget.coreService.fetchBridgeProjectFilePreview(
          backend: widget.bridgeBackend,
          relativePath: e.relPath,
        ),
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          final prev = snap.data;
          if (prev == null || (prev.error != null && prev.error!.isNotEmpty)) {
            return Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
              child: Text(
                prev?.error ?? 'Preview failed',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error),
              ),
            );
          }
          var s = prev.content;
          if (s.length > 48000) s = '${s.substring(0, 48000)}…';
          return SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: _isMarkdownName
                ? MarkdownBody(selectable: true, data: s)
                : SelectableText(
                    s,
                    style: theme.textTheme.bodySmall
                        ?.copyWith(fontFamily: 'monospace'),
                  ),
          );
        },
      );
    } else {
      body = SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Text(
            e.name.toLowerCase().endsWith('.pdf')
                ? 'PDF is not previewed inline here. Tap Open in browser to view in Safari/Chrome, or Attach to next send.'
                : 'Preview not available for this type. Try Open in browser (PDF, Office, etc.), or Insert path / Attach.',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(e.name, maxLines: 1, overflow: TextOverflow.ellipsis),
      ),
      body: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SelectableText(
              e.absPath,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.tonalIcon(
                  onPressed: () {
                    widget.onInsertPath(e.absPath);
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text('Inserted: ${e.absPath}')),
                    );
                  },
                  icon: const Icon(Icons.text_fields, size: 18),
                  label: const Text('Insert path'),
                ),
                FilledButton.icon(
                  onPressed: _attachBusy
                      ? null
                      : () async {
                          final notifier = ref.read(bridgeFilePreviewAttachBusyProvider(widget.bridgeBackend).notifier);
                          notifier.state = true;
                          try {
                            widget.onAttachForNextSend(e.absPath);
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text(
                                    'Attached — add a message if needed, then Send',
                                  ),
                                ),
                              );
                            }
                          } finally {
                            notifier.state = false;
                          }
                        },
                  icon: _attachBusy
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.attach_file, size: 18),
                  label: Text(_attachBusy ? '…' : 'Attach to next send'),
                ),
                OutlinedButton.icon(
                  onPressed: _openBrowserBusy
                      ? null
                      : () async {
                          final notifier = ref.read(bridgeFilePreviewBrowserBusyProvider(widget.bridgeBackend).notifier);
                          notifier.state = true;
                          try {
                            final viewUrl = await widget.coreService
                                .fetchBridgeProjectBrowserUrl(
                              backend: widget.bridgeBackend,
                              relativePath: e.relPath,
                            );
                            final uri = Uri.parse(viewUrl);
                            if (!context.mounted) return;
                            final ok = await launchUrl(
                              uri,
                              mode: LaunchMode.externalApplication,
                            );
                            if (!context.mounted) return;
                            if (!ok) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('Could not open browser'),
                                ),
                              );
                            }
                          } catch (err) {
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text(
                                    'Open in browser failed: $err',
                                  ),
                                ),
                              );
                            }
                          } finally {
                            notifier.state = false;
                          }
                        },
                  icon: _openBrowserBusy
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.open_in_browser, size: 18),
                  label: Text(_openBrowserBusy ? '…' : 'Open in browser'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Expanded(child: body),
          ],
        ),
      ),
    );
  }
}

class _BridgeRootBrowserDialog extends ConsumerStatefulWidget {
  final CoreService coreService;
  final String backend;
  final Future<void> Function(String absPath) onSelectFolder;

  const _BridgeRootBrowserDialog({
    required this.coreService,
    required this.backend,
    required this.onSelectFolder,
  });

  @override
  ConsumerState<_BridgeRootBrowserDialog> createState() =>
      _BridgeRootBrowserDialogState();
}

class _BridgeRootBrowserDialogState extends ConsumerState<_BridgeRootBrowserDialog> {
  BridgeRootBrowserState get _cs =>
      ref.watch(bridgeRootBrowserProvider(widget.backend));
  BridgeRootBrowserNotifier get _notifier =>
      ref.read(bridgeRootBrowserProvider(widget.backend).notifier);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    _notifier.setLoading(true);
    try {
      final r = await widget.coreService
          .fetchBridgeRootList(backend: widget.backend, path: _cs.path);
      if (!mounted) return;
      _notifier.setData(r);
    } catch (e) {
      if (!mounted) return;
      _notifier.setError(e.toString().replaceFirst(RegExp(r'^Exception:\s*'), ''));
    }
  }

  void _goUp() {
    if (_cs.path == '.' || _cs.path.isEmpty) return;
    final parts = _cs.path.split('/').where((s) => s.isNotEmpty).toList();
    if (parts.isNotEmpty) {
      parts.removeLast();
    }
    final next = parts.isEmpty ? '.' : parts.join('/');
    _notifier.setPath(next);
    _load();
  }

  Future<void> _useSelectedFolder(String absPath) async {
    _notifier.setOpeningPath(absPath);
    try {
      await widget.onSelectFolder(absPath);
      if (!mounted) return;
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Review folder: $absPath')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Open failed: $e')));
    } finally {
      if (mounted) _notifier.clearOpeningPath();
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
              '${_cs.data?.root ?? "(root unknown)"}\n${_cs.path == "." ? "(root)" : _cs.path}',
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                IconButton(
                    onPressed: _cs.path == '.' || _cs.loading ? null : _goUp,
                    icon: const Icon(Icons.arrow_upward)),
                IconButton(
                    onPressed: _cs.loading ? null : _load,
                    icon: const Icon(Icons.refresh)),
              ],
            ),
            const Divider(height: 1),
            Expanded(
              child: _cs.loading
                  ? const Center(child: CircularProgressIndicator())
                  : (_cs.error != null && _cs.error!.isNotEmpty)
                      ? Center(
                          child: Text(_cs.error!, textAlign: TextAlign.center))
                      : ListView.builder(
                          itemCount: _cs.data?.entries.length ?? 0,
                          itemBuilder: (context, i) {
                            final e = _cs.data!.entries[i];
                            final isDir = e.type == 'dir';
                            final selected =
                                isDir && _cs.selectedDirAbsPath == e.absPath;
                            return ListTile(
                              selected: selected,
                              leading: Icon(isDir
                                  ? Icons.folder_outlined
                                  : Icons.insert_drive_file_outlined),
                              title: Text(e.name),
                              subtitle: Text(e.relPath),
                              onTap: !isDir
                                  ? null
                                  : () => _notifier.setSelectedDirAbsPath(e.absPath),
                              trailing: !isDir
                                  ? null
                                  : TextButton.icon(
                                      onPressed: () {
                                        _notifier.setPath(e.relPath);
                                        _load();
                                      },
                                      icon: const Icon(Icons.chevron_right,
                                          size: 16),
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
          onPressed: (_cs.openingPath != null || _cs.selectedDirAbsPath == null)
              ? null
              : () => _useSelectedFolder(_cs.selectedDirAbsPath!),
          icon: _cs.openingPath == null
              ? const Icon(Icons.check, size: 16)
              : const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2)),
          label: const Text('Use selected'),
        ),
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Close')),
      ],
    );
  }
}
