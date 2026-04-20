import 'package:flutter/material.dart';

/// A single file attachment chip shown inside a chat message bubble.
/// Opens [onTap] when tapped.
class MessageFileChip extends StatelessWidget {
  final String name;
  final String? ref;
  final VoidCallback? onTap;

  const MessageFileChip({
    super.key,
    required this.name,
    this.ref,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        onTap: ref == null || ref!.isEmpty ? null : onTap,
        borderRadius: BorderRadius.circular(8),
        child: Chip(
          avatar: Icon(
            Icons.insert_drive_file_outlined,
            size: 18,
            color: Theme.of(context).colorScheme.primary,
          ),
          label: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 220),
            child: Text(
              name,
              overflow: TextOverflow.ellipsis,
              maxLines: 2,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
          visualDensity: VisualDensity.compact,
          side: BorderSide(
              color: Theme.of(context).colorScheme.outlineVariant),
        ),
      ),
    );
  }
}

/// Renders a list of file attachment chips wrapped in a Padding.
class MessageFileChips extends StatelessWidget {
  final List<String> fileLabels;
  final List<String>? fileRefs;
  final void Function(String ref) onTapRef;

  const MessageFileChips({
    super.key,
    required this.fileLabels,
    this.fileRefs,
    required this.onTapRef,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Wrap(
        spacing: 6,
        runSpacing: 6,
        children: List<Widget>.generate(fileLabels.length, (fi) {
          final name = fileLabels[fi];
          final ref = (fileRefs != null && fi < fileRefs!.length)
              ? fileRefs![fi]
              : '';
          return MessageFileChip(
            name: name,
            ref: ref,
            onTap: ref.isEmpty ? null : () => onTapRef(ref),
          );
        }),
      ),
    );
  }
}
