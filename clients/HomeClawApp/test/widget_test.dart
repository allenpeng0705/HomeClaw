import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/core_service.dart';
import 'package:home_claw_app/main.dart';

void main() {
  testWidgets('App loads and shows HomeClaw title', (WidgetTester tester) async {
    await tester.pumpWidget(HomeClawCompanionApp(coreService: CoreService()));
    await tester.pumpAndSettle();
    expect(find.text('HomeClaw'), findsOneWidget);
  });
}
