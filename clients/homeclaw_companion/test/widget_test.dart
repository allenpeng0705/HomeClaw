import 'package:flutter_test/flutter_test.dart';
import 'package:homeclaw_companion/core_service.dart';
import 'package:homeclaw_companion/main.dart';

void main() {
  testWidgets('App loads and shows HomeClaw title', (WidgetTester tester) async {
    await tester.pumpWidget(HomeClawCompanionApp(coreService: CoreService()));
    await tester.pumpAndSettle();
    expect(find.text('HomeClaw'), findsOneWidget);
  });
}
