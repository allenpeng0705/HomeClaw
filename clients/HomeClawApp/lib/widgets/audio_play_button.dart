import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

/// Play button for a voice message (data URL, local path, http(s), or Core `/files/...`).
class AudioPlayButton extends StatefulWidget {
  final String audioRef;
  final String coreBaseUrl;
  final Map<String, String>? coreMediaHeaders;

  const AudioPlayButton({
    super.key,
    required this.audioRef,
    required this.coreBaseUrl,
    this.coreMediaHeaders,
  });

  @override
  State<AudioPlayButton> createState() => _AudioPlayButtonState();
}

class _AudioPlayButtonState extends State<AudioPlayButton> {
  final AudioPlayer _player = AudioPlayer();
  bool _playing = false;
  StreamSubscription<void>? _completeSub;

  @override
  void dispose() {
    _completeSub?.cancel();
    _player.dispose();
    super.dispose();
  }

  Future<void> _play() async {
    final ref = widget.audioRef.trim();
    if (ref.isEmpty) return;
    try {
      Source source;
      if (ref.startsWith('data:audio/') && ref.contains(',')) {
        final b64 = ref.split(',').last;
        final bytes = base64Decode(b64);
        final dir = await getTemporaryDirectory();
        final mime = ref.startsWith('data:')
            ? ref.split(';').first.replaceFirst('data:', '')
            : 'audio';
        final ext = mime == 'audio/webm'
            ? 'webm'
            : (mime == 'audio/ogg'
                ? 'ogg'
                : (mime == 'audio/mp4' ? 'm4a' : 'webm'));
        final file = File(path.join(
            dir.path, 'voice_${DateTime.now().millisecondsSinceEpoch}.$ext'));
        await file.writeAsBytes(bytes);
        source = DeviceFileSource(file.path);
      } else if (ref.startsWith('/files/') || ref.startsWith('/files/out')) {
        final base = widget.coreBaseUrl.replaceFirst(RegExp(r'/$'), '');
        final url = '$base$ref';
        final h = widget.coreMediaHeaders;
        if (h != null && h.isNotEmpty) {
          final resp = await http.get(Uri.parse(url), headers: h);
          if (resp.statusCode < 200 || resp.statusCode >= 300) {
            throw Exception('HTTP ${resp.statusCode}');
          }
          final dir = await getTemporaryDirectory();
          final file = File(path.join(dir.path,
              'hc_audio_${DateTime.now().millisecondsSinceEpoch}.m4a'));
          await file.writeAsBytes(resp.bodyBytes);
          source = DeviceFileSource(file.path);
        } else {
          source = UrlSource(url);
        }
      } else if (ref.startsWith('http://') || ref.startsWith('https://')) {
        source = UrlSource(ref);
      } else if (await File(ref).exists()) {
        source = DeviceFileSource(ref);
      } else {
        if (mounted) {
          ScaffoldMessenger.maybeOf(context)?.showSnackBar(
              const SnackBar(content: Text('Audio file not found')));
        }
        return;
      }
      _completeSub?.cancel();
      _completeSub = _player.onPlayerComplete.listen((_) {
        if (mounted) setState(() => _playing = false);
      });
      await _player.play(source);
      if (mounted) setState(() => _playing = true);
    } catch (_) {
      if (mounted)
        ScaffoldMessenger.maybeOf(context)?.showSnackBar(
            const SnackBar(content: Text('Could not play audio')));
    }
  }

  Future<void> _stop() async {
    await _player.stop();
    if (mounted) setState(() => _playing = false);
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          icon: Icon(_playing ? Icons.stop : Icons.play_arrow),
          onPressed: _playing ? _stop : _play,
          tooltip: _playing ? 'Stop' : 'Play voice message',
        ),
        Text('Voice message', style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
