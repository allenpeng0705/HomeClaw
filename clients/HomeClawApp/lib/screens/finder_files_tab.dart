import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../core_service.dart';

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
class FinderFilesExplorer extends StatefulWidget {
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
  State<FinderFilesExplorer> createState() => _FinderFilesExplorerState();
}

class _FinderFilesExplorerState extends State<FinderFilesExplorer> {
  String _currentPath = '.';
  SandboxListResult? _result;
  String? _error;
  bool _loading = true;
  SandboxListEntry? _selected;
  bool _attachBusy = false;
  bool _openBrowserBusy = false;

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
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final r = await widget.coreService.fetchSandboxList(
        scope: widget.sandboxScope,
        path: _currentPath,
      );
      if (!mounted) return;
      setState(() {
        _result = r;
        _loading = false;
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
    final p = finderParentPath(_currentPath);
    setState(() => _currentPath = p);
    _load();
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
        n.endsWith('.html') ||
        n.endsWith('.htm') ||
        n.endsWith('.css') ||
        n.endsWith('.dart') ||
        n.endsWith('.py') ||
        n.endsWith('.ts') ||
        n.endsWith('.tsx') ||
        n.endsWith('.js') ||
        n.endsWith('.jsx') ||
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
    final mobilePreviewMode = _isMobilePreviewMode(context);
    if (_error != null && _result == null && !_loading) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.error_outline,
                  size: 48, color: theme.colorScheme.error),
              const SizedBox(height: 12),
              Text(_error!, textAlign: TextAlign.center),
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
                onPressed: _attachBusy
                    ? null
                    : () async {
                        setState(() => _attachBusy = true);
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
                          if (mounted) setState(() => _attachBusy = false);
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
                        setState(() => _openBrowserBusy = true);
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
                          if (mounted) setState(() => _openBrowserBusy = false);
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
    );
  }
}

class _FinderFilePreviewPage extends StatefulWidget {
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
  State<_FinderFilePreviewPage> createState() => _FinderFilePreviewPageState();
}

class _FinderFilePreviewPageState extends State<_FinderFilePreviewPage> {
  bool _attachBusy = false;
  bool _openBrowserBusy = false;

  bool get _isImageName {
    final n = widget.entry.name.toLowerCase();
    return n.endsWith('.png') ||
        n.endsWith('.jpg') ||
        n.endsWith('.jpeg') ||
        n.endsWith('.gif') ||
        n.endsWith('.webp');
  }

  bool get _isTextPreviewName {
    final n = widget.entry.name.toLowerCase();
    return n.endsWith('.txt') ||
        n.endsWith('.md') ||
        n.endsWith('.csv') ||
        n.endsWith('.json') ||
        n.endsWith('.log') ||
        n.endsWith('.yml') ||
        n.endsWith('.yaml') ||
        n.endsWith('.xml') ||
        n.endsWith('.html') ||
        n.endsWith('.htm') ||
        n.endsWith('.css') ||
        n.endsWith('.dart') ||
        n.endsWith('.py') ||
        n.endsWith('.ts') ||
        n.endsWith('.tsx') ||
        n.endsWith('.js') ||
        n.endsWith('.jsx') ||
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
    final n = widget.entry.name.toLowerCase();
    return n.endsWith('.md') || n.endsWith('.markdown');
  }

  bool get _isPdfName {
    final n = widget.entry.name.toLowerCase();
    return n.endsWith('.pdf');
  }

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
                          setState(() => _attachBusy = true);
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
                            if (mounted) setState(() => _attachBusy = false);
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
                          setState(() => _openBrowserBusy = true);
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
                            if (mounted) {
                              setState(() => _openBrowserBusy = false);
                            }
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
