import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:video_player/video_player.dart';

/// Full-screen video player: data URL, local file, http(s), or Core `/files/...`.
class FullScreenVideoPage extends StatefulWidget {
  final String videoRef;
  final String coreBaseUrl;
  final Map<String, String>? httpHeaders;

  const FullScreenVideoPage({
    super.key,
    required this.videoRef,
    required this.coreBaseUrl,
    this.httpHeaders,
  });

  @override
  State<FullScreenVideoPage> createState() => FullScreenVideoPageState();
}

class FullScreenVideoPageState extends State<FullScreenVideoPage> {
  VideoPlayerController? _controller;
  String? _error;

  @override
  void initState() {
    super.initState();
    _initPlayer();
  }

  Future<void> _initPlayer() async {
    final ref = widget.videoRef.trim();
    if (ref.isEmpty) {
      if (mounted) setState(() => _error = 'Invalid video');
      return;
    }
    try {
      if (ref.startsWith('data:video/') && ref.contains(',')) {
        final b64 = ref.split(',').last;
        final bytes = base64Decode(b64);
        final dir = await getTemporaryDirectory();
        final ext = ref.contains('webm') ? 'webm' : 'mp4';
        final file = File(path.join(
            dir.path, 'video_${DateTime.now().millisecondsSinceEpoch}.$ext'));
        await file.writeAsBytes(bytes);
        if (!mounted) return;
        _controller = VideoPlayerController.file(file);
      } else if (ref.startsWith('/files/') || ref.startsWith('/files/out')) {
        final base = widget.coreBaseUrl.replaceFirst(RegExp(r'/$'), '');
        final url = '$base$ref';
        _controller = VideoPlayerController.networkUrl(
          Uri.parse(url),
          httpHeaders: widget.httpHeaders ?? const {},
        );
      } else if (ref.startsWith('http://') || ref.startsWith('https://')) {
        _controller = VideoPlayerController.networkUrl(Uri.parse(ref));
      } else if (await File(ref).exists()) {
        _controller = VideoPlayerController.file(File(ref));
      } else {
        if (mounted) setState(() => _error = 'Video file not found');
        return;
      }
      await _controller!.initialize();
      if (mounted) setState(() {});
      _controller!.play();
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not play: $e');
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: const Text('Video'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: _error != null
          ? Center(
              child: Text(_error!, style: const TextStyle(color: Colors.white)))
          : _controller == null || !_controller!.value.isInitialized
              ? const Center(
                  child: CircularProgressIndicator(color: Colors.white))
              : Center(
                  child: AspectRatio(
                    aspectRatio: _controller!.value.aspectRatio,
                    child: VideoPlayer(_controller!),
                  ),
                ),
    );
  }
}
