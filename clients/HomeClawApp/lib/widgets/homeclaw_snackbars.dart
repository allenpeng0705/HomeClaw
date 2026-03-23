import 'package:flutter/material.dart';

/// Selectable error text on [ColorScheme.errorContainer] with [ColorScheme.onErrorContainer]
/// (readable; plain [ColorScheme.error] on white is often too faint).
class HomeClawInlineErrorCard extends StatelessWidget {
  final String message;
  final TextAlign textAlign;

  const HomeClawInlineErrorCard({
    super.key,
    required this.message,
    this.textAlign = TextAlign.start,
  });

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Material(
      color: t.colorScheme.errorContainer,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: SelectableText(
          message,
          textAlign: textAlign,
          style: t.textTheme.bodyMedium?.copyWith(
                color: t.colorScheme.onErrorContainer,
                fontWeight: FontWeight.w500,
              ),
        ),
      ),
    );
  }
}

/// Snackbar for failures: [ColorScheme.errorContainer] background with
/// [ColorScheme.onErrorContainer] text so messages stay readable (default
/// SnackBar text color assumes inverse surface and is often too faint on red).
SnackBar homeClawErrorSnackBar(
  BuildContext context,
  String message, {
  Duration duration = const Duration(seconds: 6),
}) {
  final cs = Theme.of(context).colorScheme;
  final base = Theme.of(context).textTheme.bodyLarge;
  return SnackBar(
    duration: duration,
    behavior: SnackBarBehavior.floating,
    backgroundColor: cs.errorContainer,
    content: Text(
      message,
      style: base?.copyWith(
            color: cs.onErrorContainer,
            fontWeight: FontWeight.w500,
            height: 1.35,
          ) ??
          TextStyle(
            color: cs.onErrorContainer,
            fontSize: 16,
            fontWeight: FontWeight.w500,
            height: 1.35,
          ),
    ),
  );
}
