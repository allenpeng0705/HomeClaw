import 'package:flutter/material.dart';
import 'full_screen_video_page.dart';

/// Chip that opens full-screen video (data URL, local path, http(s), or Core `/files/...`).
class VideoPlayChip extends StatelessWidget {
  final String videoRef;
  final String coreBaseUrl;
  final Map<String, String>? httpHeaders;

  const VideoPlayChip({
    super.key,
    required this.videoRef,
    required this.coreBaseUrl,
    this.httpHeaders,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        onTap: () {
          Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (ctx) => FullScreenVideoPage(
                videoRef: videoRef,
                coreBaseUrl: coreBaseUrl,
                httpHeaders: httpHeaders,
              ),
            ),
          );
        },
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.videocam,
                  color: Theme.of(context).colorScheme.primary),
              const SizedBox(width: 8),
              Text('Video', style: Theme.of(context).textTheme.labelLarge),
              const SizedBox(width: 4),
              const Icon(Icons.play_circle_fill, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}
