import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/widgets/message_file_chip.dart';

void main() {
  group('MessageFileChip', () {
    testWidgets('displays file name', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MessageFileChip(
              name: 'document.pdf',
              ref: '/files/doc.pdf',
              onTap: () {},
            ),
          ),
        ),
      );
      expect(find.text('document.pdf'), findsOneWidget);
    });

    testWidgets('shows file icon', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MessageFileChip(
              name: 'file.txt',
              ref: '/files/file.txt',
              onTap: () {},
            ),
          ),
        ),
      );
      expect(find.byIcon(Icons.insert_drive_file_outlined), findsOneWidget);
    });

    testWidgets('onTap is called when tapped', (tester) async {
      bool tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MessageFileChip(
              name: 'file.txt',
              ref: '/files/file.txt',
              onTap: () => tapped = true,
            ),
          ),
        ),
      );
      await tester.tap(find.byType(MessageFileChip));
      expect(tapped, true);
    });

    testWidgets('onTap is null when ref is empty', (tester) async {
      bool tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MessageFileChip(
              name: 'file.txt',
              ref: '',
              onTap: () => tapped = true,
            ),
          ),
        ),
      );
      // InkWell is still tappable but onTap is null-safe
      await tester.tap(find.byType(InkWell));
      expect(tapped, false);
    });
  });

  group('MessageFileChips', () {
    testWidgets('renders multiple chips', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MessageFileChips(
              fileLabels: ['a.txt', 'b.txt', 'c.pdf'],
              fileRefs: ['/files/a.txt', '/files/b.txt', '/files/c.pdf'],
              onTapRef: (_) {},
            ),
          ),
        ),
      );
      expect(find.text('a.txt'), findsOneWidget);
      expect(find.text('b.txt'), findsOneWidget);
      expect(find.text('c.pdf'), findsOneWidget);
      expect(find.byType(MessageFileChip), findsNWidgets(3));
    });

    testWidgets('onTapRef is called with correct ref', (tester) async {
      String? tappedRef;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MessageFileChips(
              fileLabels: ['a.txt', 'b.txt'],
              fileRefs: ['/files/a.txt', '/files/b.txt'],
              onTapRef: (ref) => tappedRef = ref,
            ),
          ),
        ),
      );
      await tester.tap(find.text('b.txt'));
      expect(tappedRef, '/files/b.txt');
    });

    testWidgets('handles null fileRefs', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MessageFileChips(
              fileLabels: ['a.txt'],
              fileRefs: null,
              onTapRef: (_) {},
            ),
          ),
        ),
      );
      expect(find.text('a.txt'), findsOneWidget);
    });
  });
}
