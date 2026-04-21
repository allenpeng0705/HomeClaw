import 'package:flutter/material.dart';
import '../providers/clawcode_providers.dart';

/// Chip showing Clawcode run state (idle / running / approval pending / error).
class CcRunChip extends StatelessWidget {
  const CcRunChip({super.key, required this.state});

  final CcRunState state;

  @override
  Widget build(BuildContext context) {
    late final String label;
    Color? bg;
    switch (state) {
      case CcRunState.idle:
        label = 'idle';
        break;
      case CcRunState.running:
        label = 'running';
        bg = Colors.blue.shade100;
        break;
      case CcRunState.approvalPending:
        label = 'approval pending';
        bg = Colors.orange.shade100;
        break;
      case CcRunState.error:
        label = 'error';
        bg = Theme.of(context).colorScheme.errorContainer;
        break;
    }
    return Chip(
      visualDensity: VisualDensity.compact,
      backgroundColor: bg,
      label: Text(label, style: const TextStyle(fontSize: 12)),
    );
  }
}
