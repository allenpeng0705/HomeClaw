import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

/// Renders chat message text as Markdown (bold, lists, code, links, etc.) with selectable text and tappable links.
class ChatMessageText extends StatelessWidget {
  final String text;
  final bool isUser;
  final bool plainText;
  final ThemeData theme;

  /// High-contrast text on [ColorScheme.errorContainer] bubbles (e.g. connection errors).
  final bool isErrorMessage;

  /// Called when a vmprint preview link is tapped and the user has native preview enabled.
  /// If null, vmprint preview navigation is skipped.
  final void Function(String url)? onVmprintPreview;

  const ChatMessageText({
    super.key,
    required this.text,
    required this.isUser,
    required this.plainText,
    required this.theme,
    this.isErrorMessage = false,
    this.onVmprintPreview,
  });

  /// File extensions that should open with system default app (e.g. PPT, PDF, DOC).
  static const List<String> _fileExtensions = [
    'ppt',
    'pptx',
    'pdf',
    'doc',
    'docx',
    'xls',
    'xlsx',
    'odt',
    'ods',
    'odp',
    'rtf',
    'txt',
    'csv',
    'zip',
    'png',
    'jpg',
    'jpeg',
    'gif',
    'webp',
    'mp4',
    'mp3',
  ];

  static bool _isFileLink(String href) {
    final lower = href.toLowerCase().trim();
    if (lower.startsWith('file:')) return true;
    if (lower.startsWith('http:') || lower.startsWith('https:')) {
      final path = Uri.tryParse(href)?.path ?? '';
      final ext = path.contains('.') ? path.split('.').last.toLowerCase() : '';
      return ext.isNotEmpty && _fileExtensions.contains(ext);
    }
    return false;
  }

  static bool _isVmprintPreviewLink(String href) {
    final u = Uri.tryParse(href);
    if (u == null) return false;
    final p = (u.queryParameters['path'] ?? u.path).toLowerCase();
    return p.contains('preview.html') ||
        p.endsWith('.preview.html') ||
        p.endsWith('.ast.json');
  }

  Future<String> _fetchVmprintUiHint(Uri uri) async {
    try {
      final resp = await http.get(uri).timeout(const Duration(seconds: 4));
      if (resp.statusCode < 200 || resp.statusCode >= 300) return 'link';
      final body = resp.body;
      final m = RegExp(
        "<meta\\s+name=[\"']homeclaw-vmprint-ui-hint[\"']\\s+content=[\"'](inline|link)[\"']",
        caseSensitive: false,
      ).firstMatch(body);
      final hint = (m?.group(1) ?? '').toLowerCase();
      if (hint == 'inline' || hint == 'link') return hint;
    } catch (_) {}
    return 'link';
  }

  Future<void> _onTapLink(
      BuildContext context, String text, String? href, String title) async {
    if (href == null || href.isEmpty) return;
    Uri? uri = Uri.tryParse(href);
    if (uri == null) return;
    try {
      final isFile = _isFileLink(href);
      if (isFile && uri.scheme == 'file') {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
        return;
      }
      if ((uri.scheme == 'http' || uri.scheme == 'https') &&
          _isVmprintPreviewLink(href)) {
        final prefs = await SharedPreferences.getInstance();
        final enabled = prefs.getBool('vmprint_native_preview') ?? false;
        if (enabled) {
          final hint = await _fetchVmprintUiHint(uri);
          if (hint != 'inline') {
            await launchUrl(uri, mode: LaunchMode.externalApplication);
            return;
          }
          if (!context.mounted) return;
          if (onVmprintPreview != null) {
            onVmprintPreview!(href);
          }
          return;
        }
      }
      if (isFile && (uri.scheme == 'http' || uri.scheme == 'https')) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
        return;
      }
      if (uri.scheme == 'http' || uri.scheme == 'https') {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
        return;
      }
      if (uri.scheme.isEmpty &&
          (RegExp(r'^[A-Za-z]:[/\\]').hasMatch(href) || href.startsWith('/'))) {
        final fileUri = Uri.file(href);
        if (await canLaunchUrl(fileUri)) {
          await launchUrl(fileUri, mode: LaunchMode.externalApplication);
        }
        return;
      }
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      }
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final effectiveText = text.isEmpty ? '\u200B' : text;
    final errorFg = isErrorMessage ? theme.colorScheme.onErrorContainer : null;
    if (plainText) {
      return SelectableText(
        effectiveText,
        style: theme.textTheme.bodyLarge?.copyWith(color: errorFg),
      );
    }
    final bodyLarge = theme.textTheme.bodyLarge;
    final bodyMedium = theme.textTheme.bodyMedium;
    final pStyle =
        errorFg != null ? bodyLarge?.copyWith(color: errorFg) : bodyLarge;
    final styleSheet = MarkdownStyleSheet.fromTheme(theme).copyWith(
      p: pStyle,
      listBullet: pStyle,
      h1: errorFg != null
          ? theme.textTheme.headlineSmall?.copyWith(color: errorFg)
          : theme.textTheme.headlineSmall,
      h2: errorFg != null
          ? theme.textTheme.titleLarge?.copyWith(color: errorFg)
          : theme.textTheme.titleLarge,
      h3: errorFg != null
          ? theme.textTheme.titleMedium?.copyWith(color: errorFg)
          : theme.textTheme.titleMedium,
      code: bodyMedium?.copyWith(
        fontFamily: 'monospace',
        color: errorFg ?? bodyMedium.color,
        backgroundColor: theme.colorScheme.surfaceContainerHighest,
      ),
      codeblockDecoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
      ),
      blockquote: theme.textTheme.bodyMedium?.copyWith(
        color: errorFg ?? theme.colorScheme.onSurfaceVariant,
      ),
      blockquoteDecoration: BoxDecoration(
        border: Border(
          left: BorderSide(
            color: errorFg ?? theme.colorScheme.primary,
            width: 4,
          ),
        ),
      ),
    );
    return MarkdownBody(
      data: effectiveText,
      selectable: true,
      styleSheet: styleSheet,
      onTapLink: (text, href, title) => _onTapLink(context, text, href, title),
      softLineBreak: true,
      shrinkWrap: true,
      fitContent: true,
    );
  }
}
