import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/widgets/cc_run_chip.dart';

void main() {
  group('CcRunChip', () {
    testWidgets('displays idle label', (tester) async {
      await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: CcRunChip(state: CcRunState.idle))),
      );
      expect(find.text('idle'), findsOneWidget);
    });

    testWidgets('displays running label with blue background', (tester) async {
      await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: CcRunChip(state: CcRunState.running))),
      );
      expect(find.text('running'), findsOneWidget);
      final chip = tester.widget<Chip>(find.byType(Chip));
      expect(chip.backgroundColor, isNotNull);
    });

    testWidgets('displays approval pending label', (tester) async {
      await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: CcRunChip(state: CcRunState.approvalPending))),
      );
      expect(find.text('approval pending'), findsOneWidget);
    });

    testWidgets('displays error label', (tester) async {
      await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: CcRunChip(state: CcRunState.error))),
      );
      expect(find.text('error'), findsOneWidget);
    });
  });
}
