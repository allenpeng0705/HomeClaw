import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/widgets/video_play_chip.dart';

void main() {
  group('VideoPlayChip', () {
    testWidgets('displays video label with play icon', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: VideoPlayChip(
              videoRef: '/files/video.mp4',
              coreBaseUrl: 'http://localhost:8080',
            ),
          ),
        ),
      );
      expect(find.text('Video'), findsOneWidget);
      expect(find.byIcon(Icons.videocam), findsOneWidget);
      expect(find.byIcon(Icons.play_circle_fill), findsOneWidget);
    });

    testWidgets('tapping opens FullScreenVideoPage', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: VideoPlayChip(
              videoRef: '/files/video.mp4',
              coreBaseUrl: 'http://localhost:8080',
            ),
          ),
        ),
      );
      await tester.tap(find.byType(VideoPlayChip));
      await tester.pumpAndSettle();
      // Should navigate to FullScreenVideoPage
      expect(find.byType(MaterialPageRoute), findsOneWidget);
    });
  });
}
