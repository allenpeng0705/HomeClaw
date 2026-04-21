import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../core_service.dart';
import '../providers/finder_files_providers.dart';
import '../utils/file_preview_utils.dart';

/// Path relative to user sandbox for LLM tools (strip scope prefix from list API paths).
String finderModelPathFromFullRel(String fullRelPath, String scope) {
  final prefix = '$scope/';
  if (fullRelPath.startsWith(prefix)) {
    return fullRelPath.substring(prefix.length);
  }
  return fullRelPath;
}

String finderParentPath(String currentPath) {
  if (currentPath == '.' || currentPath.isEmpty) return '.';
  final parts = currentPath.split('/').where((s) => s.isNotEmpty).toList();
  if (parts.isEmpty) return '.';
  parts.removeLast();
  return parts.isEmpty ? '.' : parts.join('/');
}

/// Finder preset: browse Core sandbox (GET /api/sandbox/list), preview, insert path, attach for next send.
class FinderFilesExplorer extends ConsumerStatefulWidget {
  final CoreService coreService;
  final String sandboxScope;
  final String initialPath;
  final void Function(String modelRelativePath) onInsertPathForModel;
  final void Function(String modelRelativePath)? onAskAboutFile;
  final Future<void> Function(String fullRelPathFromBase) onAttachFile;

  const FinderFilesExplorer({
    super.key,
    required this.coreService,
    required this.sandboxScope,
    this.initialPath = '.',
    required this.onInsertPathForModel,
    this.onAskAboutFile,
    required this.onAttachFile,
  });

  @override
  ConsumerState<FinderFilesExplorer> createState() => _FinderFilesExplorerState();
}

class _FinderFilesExplorerState extends ConsumerState<FinderFilesExplorer> {
  String _currentPath = '.';
  SandboxListEntry? _selected;

  bool _isMobilePreviewMode(BuildContext context) =>
      MediaQuery.of(context).size.shortestSide < 600;

  Future<void> _openMobilePreviewPage(SandboxListEntry entry) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => _FinderFilePreviewPage(
          coreService: widget.coreService,
          sandboxScope: widget.sandboxScope,
          entry: entry,
          onInsertPathForModel: widget.onInsertPathForModel,
          onAskAboutFile: widget.onAskAboutFile,
          onAttachFile: widget.onAttachFile,
        ),
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    final p = widget.initialPath.trim();
    _currentPath = p.isEmpty ? '.' : p;
    _load();
  }

  Future<void> _load() async {
    final notifier = ref.read(finderFilesProvider(widget.sandboxScope).notifier);
    notifier.setLoading(true);
    try {
      final r = await widget.coreService.fetchSandboxList(
        scope: widget.sandboxScope,
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
    final p = finderParentPath(_currentPath);
    setState(() => _currentPath = p);
    _load();
  }

  bool get _isImageName => isDisplayableImageName(_selected?.name ?? '');
  bool get _isTextPreviewName => isTextPreviewName(_selected?.name ?? '');
  bool get _isMarkdownName => isMarkdownName(_selected?.name ?? '');
  bool get _isPdfName => isPdfName(_selected?.name ?? '');

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final state = ref.watch(finderFilesProvider(widget.sandboxScope));
    final mobilePreviewMode = _isMobilePreviewMode(context);
    if (state.error != null && state.result == null && !state.loading) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline,
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
                      '${widget.sandboxScope} / ${_currentPath == '.' ? '(root)' : _currentPath}',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleSmall,
                    ),
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
                    final sel = _selected?.path == e.path;
                    return ListTile(
                      selected: sel,
                      leading: Icon(isDir
                          ? Icons.folder_outlined
                          : Icons.insert_drive_file_outlined),
                      title: Text(e.name),
                      subtitle: isDir ? const Text('Folder') : null,
                      onTap: () {
                        if (isDir) {
                          _openDir(e.name);
                        } else {
                          if (mobilePreviewMode) {
                            _openMobilePreviewPage(e);
                          } else {
                            setState(() => _selected = e);
                          }
                        }
                      },
                      onLongPress: () {
                        if (!isDir) {
                          widget.onInsertPathForModel(
                              finderModelPathFromFullRel(
                                  e.path, widget.sandboxScope));
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                                content: Text(
                                    'Inserted path: ${finderModelPathFromFullRel(e.path, widget.sandboxScope)}')),
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
    final e = _selected!;
    final state = ref.watch(finderFilesProvider(widget.sandboxScope));
    final attachBusy = state.attachBusy;
    final openBrowserBusy = state.openBrowserBusy;
    final modelPath = finderModelPathFromFullRel(e.path, widget.sandboxScope);
    final theme = Theme.of(context);
    final uri = widget.coreService.sandboxFileUri(e.path);
    final headers = widget.coreService.coreMediaFetchHeaders;
    Widget body;
    if (_isImageName) {
      body = SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: Image.network(
            uri.toString(),
            headers: headers,
            fit: BoxFit.contain,
            errorBuilder: (_, __, ___) => const Text('Could not load image'),
          ),
        ),
      );
    } else if (_isPdfName) {
      body = Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        child: FutureBuilder<String>(
          future: widget.coreService.fetchSandboxFileViewUrl(e.path),
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
      body = FutureBuilder<String>(
        future: widget.coreService.fetchSandboxFileBytes(e.path).then((b) {
          try {
            var s = utf8.decode(b, allowMalformed: true);
            if (s.length > 48000) s = '${s.substring(0, 48000)}…';
            return s;
          } catch (_) {
            return '(binary or unsupported encoding)';
          }
        }),
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          final text = snap.data ?? '';
          return SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: _isMarkdownName
                ? MarkdownBody(selectable: true, data: text)
                : SelectableText(text,
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
          Text('Tool path: $modelPath',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.tonalIcon(
                onPressed: () {
                  widget.onInsertPathForModel(modelPath);
                  ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text('Inserted: $modelPath')));
                },
                icon: const Icon(Icons.text_fields, size: 18),
                label: const Text('Insert path'),
              ),
              if (widget.onAskAboutFile != null)
                FilledButton.tonal(
                  onPressed: () {
                    widget.onAskAboutFile!(modelPath);
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                          content: Text('Added file to question: $modelPath')),
                    );
                  },
                  child: const Text('Ask about this file'),
                ),
              FilledButton.icon(
                onPressed: attachBusy
                    ? null
                    : () async {
                        ref.read(finderFilesProvider(widget.sandboxScope).notifier).setAttachBusy(true);
                        try {
                          await widget.onAttachFile(e.path);
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                  content: Text(
                                      'Attached — add a message if needed, then Send')),
                            );
                          }
                        } catch (err) {
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(content: Text('Attach failed: $err')),
                            );
                          }
                        } finally {
                          ref.read(finderFilesProvider(widget.sandboxScope).notifier).setAttachBusy(false);
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
                        ref.read(finderFilesProvider(widget.sandboxScope).notifier).setOpenBrowserBusy(true);
                        try {
                          final viewUrl = await widget.coreService
                              .fetchSandboxFileViewUrl(e.path);
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
                          ref.read(finderFilesProvider(widget.sandboxScope).notifier).setOpenBrowserBusy(false);
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

class _FinderFilePreviewPage extends ConsumerStatefulWidget {
  final CoreService coreService;
  final String sandboxScope;
  final SandboxListEntry entry;
  final void Function(String modelRelativePath) onInsertPathForModel;
  final void Function(String modelRelativePath)? onAskAboutFile;
  final Future<void> Function(String fullRelPathFromBase) onAttachFile;

  const _FinderFilePreviewPage({
    required this.coreService,
    required this.sandboxScope,
    required this.entry,
    required this.onInsertPathForModel,
    this.onAskAboutFile,
    required this.onAttachFile,
  });

  @override
  ConsumerState<_FinderFilePreviewPage> createState() => _FinderFilePreviewPageState();
}

class _FinderFilePreviewPageState extends ConsumerState<_FinderFilePreviewPage> {
  bool get _attachBusy =>
      ref.watch(finderFilePreviewAttachBusyProvider(widget.sandboxScope));
  bool get _openBrowserBusy =>
      ref.watch(finderFilePreviewBrowserBusyProvider(widget.sandboxScope));

  bool get _isImageName => isDisplayableImageName(widget.entry.name);
  bool get _isTextPreviewName => isTextPreviewName(widget.entry.name);
  bool get _isMarkdownName => isMarkdownName(widget.entry.name);
  bool get _isPdfName => isPdfName(widget.entry.name);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final e = widget.entry;
    final modelPath = finderModelPathFromFullRel(e.path, widget.sandboxScope);
    final uri = widget.coreService.sandboxFileUri(e.path);
    final headers = widget.coreService.coreMediaFetchHeaders;

    Widget body;
    if (_isImageName) {
      body = SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: Image.network(
            uri.toString(),
            headers: headers,
            fit: BoxFit.contain,
            errorBuilder: (_, __, ___) => const Text('Could not load image'),
          ),
        ),
      );
    } else if (_isPdfName) {
      body = Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
        child: FutureBuilder<String>(
          future: widget.coreService.fetchSandboxFileViewUrl(e.path),
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
      body = FutureBuilder<String>(
        future: widget.coreService.fetchSandboxFileBytes(e.path).then((b) {
          try {
            var s = utf8.decode(b, allowMalformed: true);
            if (s.length > 48000) s = '${s.substring(0, 48000)}…';
            return s;
          } catch (_) {
            return '(binary or unsupported encoding)';
          }
        }),
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          final text = snap.data ?? '';
          return SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: _isMarkdownName
                ? MarkdownBody(selectable: true, data: text)
                : SelectableText(text,
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

    return Scaffold(
      appBar: AppBar(
          title: Text(e.name, maxLines: 1, overflow: TextOverflow.ellipsis)),
      body: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Tool path: $modelPath',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.tonalIcon(
                  onPressed: () {
                    widget.onInsertPathForModel(modelPath);
                    ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('Inserted: $modelPath')));
                  },
                  icon: const Icon(Icons.text_fields, size: 18),
                  label: const Text('Insert path'),
                ),
                if (widget.onAskAboutFile != null)
                  FilledButton.tonal(
                    onPressed: () {
                      widget.onAskAboutFile!(modelPath);
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                            content:
                                Text('Added file to question: $modelPath')),
                      );
                    },
                    child: const Text('Ask about this file'),
                  ),
                FilledButton.icon(
                  onPressed: _attachBusy
                      ? null
                      : () async {
                          final notifier = ref.read(finderFilePreviewAttachBusyProvider(widget.sandboxScope).notifier);
                          notifier.state = true;
                          try {
                            await widget.onAttachFile(e.path);
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                    content: Text(
                                        'Attached — add a message if needed, then Send')),
                              );
                            }
                          } catch (err) {
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(content: Text('Attach failed: $err')),
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
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.attach_file, size: 18),
                  label: Text(_attachBusy ? '…' : 'Attach to next send'),
                ),
                OutlinedButton.icon(
                  onPressed: _openBrowserBusy
                      ? null
                      : () async {
                          final notifier = ref.read(finderFilePreviewBrowserBusyProvider(widget.sandboxScope).notifier);
                          notifier.state = true;
                          try {
                            final viewUrl = await widget.coreService
                                .fetchSandboxFileViewUrl(e.path);
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
                            notifier.state = false;
                          }
                        },
                  icon: _openBrowserBusy
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2))
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
