import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path/path.dart' as path;
import 'package:flutter_tts/flutter_tts.dart';
import 'package:homeclaw_native/homeclaw_native.dart';
import 'package:homeclaw_voice/homeclaw_voice.dart';
import 'package:image_picker/image_picker.dart';
import '../core_service.dart';
import 'canvas_screen.dart';
import 'settings_screen.dart';

class ChatScreen extends StatefulWidget {
  final CoreService coreService;
  final String? initialMessage;

  const ChatScreen({super.key, required this.coreService, this.initialMessage});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final List<MapEntry<String, bool>> _messages = [];
  final TextEditingController _inputController = TextEditingController();
  bool _loading = false;
  bool _voiceListening = false;
  String _voiceTranscript = '';
  StreamSubscription<Map<String, dynamic>>? _voiceSubscription;
  final _native = HomeclawNative();
  final _voice = HomeclawVoice();
  final _tts = FlutterTts();
  final _imagePicker = ImagePicker();
  String? _lastReply;
  final List<String> _pendingImagePaths = [];
  final List<String> _pendingVideoPaths = [];

  @override
  void initState() {
    super.initState();
    if (widget.initialMessage != null && widget.initialMessage!.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _inputController.text = widget.initialMessage!;
      });
    }
  }

  Future<void> _send() async {
    final text = _inputController.text.trim();
    final hasAttachments = _pendingImagePaths.isNotEmpty || _pendingVideoPaths.isNotEmpty;
    if ((text.isEmpty && !hasAttachments) || _loading) return;
    _inputController.clear();
    final imagesToSend = List<String>.from(_pendingImagePaths);
    final videosToSend = List<String>.from(_pendingVideoPaths);
    setState(() {
      _pendingImagePaths.clear();
      _pendingVideoPaths.clear();
      _messages.add(MapEntry(text.isEmpty ? '(attachment)' : text, true));
      _loading = true;
    });
    try {
      List<String> imagePaths = [];
      List<String> videoPaths = [];
      if (imagesToSend.isNotEmpty || videosToSend.isNotEmpty) {
        try {
          final uploaded = await widget.coreService.uploadFiles([...imagesToSend, ...videosToSend]);
          final n = imagesToSend.length;
          imagePaths = uploaded.take(n).toList();
          videoPaths = uploaded.skip(n).toList();
        } catch (_) {
          // Same fallback as web chat: if upload fails, send images as data URLs so message still goes through.
          final dataUrls = await _filePathsToImageDataUrls(imagesToSend);
          if (dataUrls.isNotEmpty) {
            imagePaths = dataUrls;
            // Videos not sent as data URLs on fallback to avoid huge payloads.
          }
        }
      }
      final reply = await widget.coreService.sendMessage(
        text.isEmpty ? 'See attached media.' : text,
        images: imagePaths.isEmpty ? null : imagePaths,
        videos: videoPaths.isEmpty ? null : videoPaths,
      );
      if (mounted) {
        _lastReply = reply;
        setState(() {
          _messages.add(MapEntry(reply.isEmpty ? '(no reply)' : reply, false));
          _loading = false;
        });
        final preview = reply.isEmpty ? 'No reply' : (reply.length > 80 ? '${reply.substring(0, 80)}…' : reply);
        await _native.showNotification(title: 'HomeClaw', body: preview);
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _messages.add(MapEntry('Error: $e', false));
          _loading = false;
        });
      }
    }
  }

  static const Map<String, String> _imageMime = {
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'webp': 'image/webp',
  };

  /// Build data URLs for image files (same fallback as web chat when upload fails).
  Future<List<String>> _filePathsToImageDataUrls(List<String> filePaths) async {
    final out = <String>[];
    for (final p in filePaths) {
      final ext = path.extension(p).toLowerCase().replaceFirst('.', '');
      if (!_imageMime.containsKey(ext)) continue;
      final file = File(p);
      if (!await file.exists()) continue;
      final bytes = await file.readAsBytes();
      final b64 = base64Encode(bytes);
      out.add('data:${_imageMime[ext]};base64,$b64');
    }
    return out;
  }

  Future<void> _toggleVoice() async {
    if (_voiceListening) {
      await _voice.stopVoiceListening();
      _voiceSubscription?.cancel();
      _voiceSubscription = null;
      final textToSend = _voiceTranscript.trim();
      setState(() {
        _voiceListening = false;
        if (textToSend.isNotEmpty) {
          _inputController.text = textToSend;
          _voiceTranscript = '';
        }
      });
      if (textToSend.isNotEmpty) _send();
      return;
    }
    setState(() {
      _voiceTranscript = '';
      _inputController.clear();
    });
    _voiceSubscription = _voice.voiceEventStream.listen(
        (event) {
        if (!mounted) return;
        final partial = event['partial'] as String?;
        final finalText = event['final'] as String?;
        if (finalText != null && finalText.isNotEmpty) {
          setState(() {
            _voiceTranscript = finalText;
            _inputController.text = finalText;
            _inputController.selection = TextSelection.collapsed(offset: finalText.length);
          });
          _send().then((_) {
            if (mounted) setState(() => _voiceTranscript = '');
          });
        } else if (partial != null && partial.isNotEmpty) {
          setState(() {
            _voiceTranscript = partial;
            _inputController.text = partial;
            _inputController.selection = TextSelection.collapsed(offset: partial.length);
          });
        }
      },
      onError: (e) {
        if (mounted) {
          setState(() => _voiceListening = false);
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Voice error: $e')),
          );
        }
      },
    );
    try {
      await _voice.startVoiceListening();
      if (mounted) setState(() => _voiceListening = true);
    } catch (e) {
      if (mounted) {
        setState(() => _voiceListening = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Voice failed: $e. On macOS, allow Microphone in System Settings > Privacy.')),
        );
      }
    }
  }

  Future<void> _takePhoto() async {
    await Future<void>.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;
    final source = await showDialog<ImageSource>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Take photo'),
        content: const Text('Use camera to take a new photo, or choose an existing image from your device.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(ImageSource.camera), child: const Text('Use camera')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(ImageSource.gallery), child: const Text('Choose from device')),
        ],
      ),
    );
    if (source == null || !mounted) return;
    try {
      if (mounted) showDialog(context: context, barrierDismissible: false, builder: (_) => AlertDialog(content: Row(children: [const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)), const SizedBox(width: 16), Expanded(child: Text(source == ImageSource.camera ? 'Opening camera…' : 'Choosing photo…', textAlign: TextAlign.start))]));
      final xFile = await _imagePicker.pickImage(source: source);
      if (mounted) Navigator.of(context).pop();
      if (xFile == null || !mounted) return;
      final added = await _showMediaPreview(context, type: 'photo', filePath: xFile.path, label: 'Add this photo to your message?');
      if (added && mounted) {
        setState(() => _pendingImagePaths.add(xFile.path));
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Photo attached. Type a message and Send to include it.')));
      }
    } catch (e) {
      if (mounted) {
        try { Navigator.of(context).pop(); } catch (_) {}
        setState(() => _messages.add(MapEntry('Photo error: $e', false)));
      }
    }
  }

  Future<void> _recordVideo() async {
    await Future<void>.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;
    final source = await showDialog<ImageSource>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Record video'),
        content: const Text('Use camera to record a new video, or choose an existing video from your device.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(ImageSource.camera), child: const Text('Use camera')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(ImageSource.gallery), child: const Text('Choose from device')),
        ],
      ),
    );
    if (source == null || !mounted) return;
    try {
      if (mounted) showDialog(context: context, barrierDismissible: false, builder: (_) => AlertDialog(content: Row(children: [const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)), const SizedBox(width: 16), Expanded(child: Text(source == ImageSource.camera ? 'Recording video…' : 'Choosing video…', textAlign: TextAlign.start))]));
      final xFile = await _imagePicker.pickVideo(source: source, maxDuration: const Duration(seconds: 30));
      if (mounted) Navigator.of(context).pop();
      if (xFile == null || !mounted) return;
      final added = await _showMediaPreview(context, type: 'video', filePath: xFile.path, label: 'Add this video to your message?');
      if (added && mounted) {
        setState(() => _pendingVideoPaths.add(xFile.path));
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Video attached. Type a message and Send to include it.')));
      }
    } catch (e) {
      if (mounted) {
        try { Navigator.of(context).pop(); } catch (_) {}
        setState(() => _messages.add(MapEntry('Video error: $e', false)));
      }
    }
  }

  Future<void> _recordScreen() async {
    await Future<void>.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;
    try {
      if (mounted) showDialog(context: context, barrierDismissible: false, builder: (_) => const AlertDialog(content: Column(mainAxisSize: MainAxisSize.min, children: [SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)), SizedBox(height: 12), Text('Recording screen… (about 10 seconds)')])));
      final recordPath = await _native.startScreenRecord(durationSec: 10, includeAudio: false);
      if (mounted) Navigator.of(context).pop();
      if (recordPath == null || recordPath.isEmpty) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                Platform.isMacOS
                    ? 'Screen recording failed. Allow Screen Recording in System Settings → Privacy & Security, then try again.'
                    : 'Screen recording not available on this platform',
              ),
              duration: const Duration(seconds: 5),
            ),
          );
        }
        return;
      }
      final added = await _showMediaPreview(context, type: 'video', filePath: recordPath, label: 'Add this screen recording to your message?');
      if (added && mounted) {
        setState(() => _pendingVideoPaths.add(recordPath));
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Screen recording attached. Send to include it.')));
      }
    } catch (e) {
      if (mounted) {
        try { Navigator.of(context).pop(); } catch (_) {}
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Screen record error: $e')));
      }
    }
  }

  Future<bool> _showMediaPreview(BuildContext context, {required String type, required String filePath, required String label}) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(type == 'photo' ? 'Preview photo' : 'Preview video'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (type == 'photo')
                ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: Image.file(File(filePath), fit: BoxFit.contain, height: 200, width: double.infinity),
                )
              else
                Row(
                  children: [
                    Icon(Icons.videocam, size: 48, color: Theme.of(ctx).colorScheme.primary),
                    const SizedBox(width: 12),
                    Expanded(child: Text(path.basename(filePath), style: Theme.of(ctx).textTheme.bodySmall, overflow: TextOverflow.ellipsis)),
                  ],
                ),
              const SizedBox(height: 12),
              Text(label, style: Theme.of(ctx).textTheme.bodyMedium),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Reject')),
          FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text('Confirm')),
        ],
      ),
    );
    return result == true;
  }

  /// For TTS only: strip emoji and punctuation so speech sounds clean. Does not change chat text.
  static String _textForTts(String text) {
    final buffer = StringBuffer();
    for (final rune in text.runes) {
      if (_isEmojiRune(rune)) continue;
      if (_isPunctuationRune(rune)) {
        buffer.write(' ');
        continue;
      }
      buffer.write(String.fromCharCode(rune));
    }
    return buffer.toString().replaceAll(RegExp(r'\s+'), ' ').trim();
  }

  static bool _isEmojiRune(int rune) {
    return (rune >= 0x1F300 && rune <= 0x1F9FF) ||
        (rune >= 0x2600 && rune <= 0x26FF) ||
        (rune >= 0x2700 && rune <= 0x27BF) ||
        (rune >= 0x1F600 && rune <= 0x1F64F) ||
        (rune >= 0x1F1E0 && rune <= 0x1F1FF) ||
        (rune >= 0x1F900 && rune <= 0x1F9FF);
  }

  static bool _isPunctuationRune(int rune) {
    return (rune >= 0x21 && rune <= 0x2F) ||
        (rune >= 0x3A && rune <= 0x40) ||
        (rune >= 0x5B && rune <= 0x60) ||
        (rune >= 0x7B && rune <= 0x7E) ||
        rune == 0x2014 || rune == 0x2013 || rune == 0x2026 || rune == 0x2022;
  }

  Future<void> _speakLastReply() async {
    final raw = _lastReply?.trim();
    if (raw == null || raw.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No reply to speak')),
      );
      return;
    }
    final text = _textForTts(raw);
    if (text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Nothing to speak after removing emoji and punctuation')),
      );
      return;
    }
    try {
      await _tts.speak(text);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('TTS: $e')));
    }
  }

  /// (category label, example commands). Add these executables in Settings → Exec allowlist first.
  static List<MapEntry<String, List<String>>> _runCommandExamplesByCategory() {
    if (Platform.isMacOS) {
      return [
        const MapEntry('System', ['ls', 'ls -la', 'pwd', 'whoami', 'date', 'say "hello"']),
        const MapEntry('Files & folders', ['open .', 'open ~/Desktop', 'open ~/Downloads']),
        const MapEntry('Browser', ['open https://example.com', 'open -a Safari https://example.com']),
        const MapEntry('Applications', ['open -a Safari', 'open -a Notes', 'open -a "Visual Studio Code"']),
      ];
    }
    if (Platform.isWindows) {
      return [
        const MapEntry('System', ['whoami', 'hostname', 'tasklist', 'where', 'cmd /c dir', 'cmd /c echo hello']),
        const MapEntry('Files & folders', ['explorer .', 'cmd /c start "" "%USERPROFILE%\\Desktop"']),
        const MapEntry('Browser', ['cmd /c start https://example.com']),
        const MapEntry('Applications', ['cmd /c start notepad', 'cmd /c start calc']),
      ];
    }
    if (Platform.isLinux) {
      return [
        const MapEntry('System', ['ls', 'ls -la', 'pwd', 'whoami', 'date', 'uname -a', 'df -h', 'free -h']),
        const MapEntry('Files & folders', ['xdg-open .', 'nautilus .', 'cat /etc/os-release']),
        const MapEntry('Browser', ['xdg-open https://example.com']),
        const MapEntry('Applications', ['xdg-open .']),
      ];
    }
    return [];
  }

  Future<void> _runCommand() async {
    final isDesktop = Platform.isMacOS || Platform.isWindows || Platform.isLinux;
    if (!isDesktop) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Run command is only available on desktop')),
      );
      return;
    }
    if (widget.coreService.execAllowlist.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Add allowed commands in Settings first')),
      );
      return;
    }
    final cmdController = TextEditingController();
    final exampleCategories = _runCommandExamplesByCategory();
    final cmd = await showDialog<String>(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: const Text('Run command'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ExpansionTile(
                  title: Text('How to use', style: Theme.of(ctx).textTheme.titleSmall),
                  initiallyExpanded: true,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(
                        '1. Open Settings → Exec allowlist and add the executable name (e.g. open, ls, cmd) or a regex (e.g. ^/usr/bin/.*).\n'
                        '2. Here, enter the full command and tap Run. Output appears in chat.\n'
                        '3. Tap an example below to fill the field; edit if needed, then Run.',
                        style: Theme.of(ctx).textTheme.bodySmall,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: cmdController,
                  autofocus: true,
                  decoration: InputDecoration(
                    hintText: Platform.isWindows ? 'e.g. cmd /c dir' : 'e.g. ls -la, open .',
                    border: const OutlineInputBorder(),
                  ),
                  onSubmitted: (v) => Navigator.of(ctx).pop(v),
                ),
                ...exampleCategories.expand((entry) => [
                  const SizedBox(height: 10),
                  Text(entry.key, style: Theme.of(ctx).textTheme.labelMedium),
                  const SizedBox(height: 4),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: entry.value.map((ex) => ActionChip(
                      label: Text(ex, style: const TextStyle(fontFamily: 'monospace', fontSize: 11)),
                      onPressed: () => cmdController.text = ex,
                    )).toList(),
                  ),
                ]),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(cmdController.text.trim()),
              child: const Text('Run'),
            ),
          ],
        );
      },
    );
    if (cmd == null || cmd.trim().isEmpty) return;
    if (!widget.coreService.isExecAllowed(cmd)) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Command not in allowlist. Add exact name or regex in Settings.')),
        );
      }
      return;
    }
    final parts = cmd.trim().split(RegExp(r'\s+'));
    final executable = parts.first;
    try {
      final result = await Process.run(
        executable,
        parts.length > 1 ? parts.sublist(1) : [],
        runInShell: false,
      ).timeout(const Duration(seconds: 30));
      final out = (result.stdout is String
          ? (result.stdout as String)
          : utf8.decode(result.stdout as List<int>)).trim();
      final err = (result.stderr is String
          ? (result.stderr as String)
          : utf8.decode(result.stderr as List<int>)).trim();
      final line = 'Exit ${result.exitCode}${out.isNotEmpty ? '\n$out' : ''}${err.isNotEmpty ? '\n$err' : ''}';
      if (mounted) setState(() => _messages.add(MapEntry('Run: $cmd\n$line', false)));
    } catch (e) {
      if (mounted) setState(() => _messages.add(MapEntry('Run error: $e', false)));
    }
  }

  @override
  void dispose() {
    _voiceSubscription?.cancel();
    _voice.dispose();
    _inputController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('HomeClaw'),
        actions: [
          IconButton(
            icon: const Icon(Icons.dashboard_customize),
            tooltip: 'Canvas',
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => CanvasScreen(coreService: widget.coreService),
                ),
              );
            },
          ),
          PopupMenuButton<String>(
            icon: const Icon(Icons.more_vert),
            tooltip: 'More',
            onSelected: (value) async {
              switch (value) {
                case 'photo':
                  await _takePhoto();
                  break;
                case 'video':
                  await _recordVideo();
                  break;
                case 'screen':
                  await _recordScreen();
                  break;
                case 'run':
                  await _runCommand();
                  break;
                case 'speak':
                  await _speakLastReply();
                  break;
              }
            },
            itemBuilder: (context) => [
              const PopupMenuItem(value: 'photo', child: Text('Take photo')),
              const PopupMenuItem(value: 'video', child: Text('Record video')),
              const PopupMenuItem(value: 'screen', child: Text('Record screen')),
              const PopupMenuItem(value: 'run', child: Text('Run command')),
              const PopupMenuItem(value: 'speak', child: Text('Speak last reply')),
            ],
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => SettingsScreen(coreService: widget.coreService),
                ),
              );
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(8),
              itemCount: _messages.length,
              itemBuilder: (context, i) {
                final entry = _messages[i];
                final isUser = entry.value;
                return Align(
                  alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                      color: isUser ? Theme.of(context).colorScheme.primaryContainer : Theme.of(context).colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: SelectableText(
                      entry.key,
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                  ),
                );
              },
            ),
          ),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(8.0),
              child: LinearProgressIndicator(),
            ),
          if (_voiceListening)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              child: Material(
                color: Theme.of(context).colorScheme.primaryContainer.withOpacity(0.5),
                borderRadius: BorderRadius.circular(12),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  child: Row(
                    children: [
                      Icon(
                        Icons.mic,
                        color: Theme.of(context).colorScheme.primary,
                        size: 28,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              _voiceTranscript.isEmpty ? 'Listening...' : 'Speaking',
                              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                                    color: Theme.of(context).colorScheme.primary,
                                  ),
                            ),
                            if (_voiceTranscript.isNotEmpty)
                              Padding(
                                padding: const EdgeInsets.only(top: 4),
                                child: Text(
                                  _voiceTranscript,
                                  style: Theme.of(context).textTheme.bodyMedium,
                                ),
                              ),
                          ],
                        ),
                      ),
                      TextButton.icon(
                        onPressed: _toggleVoice,
                        icon: const Icon(Icons.stop_circle),
                        label: const Text('Stop'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          if (_pendingImagePaths.isNotEmpty || _pendingVideoPaths.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              child: Row(
                children: [
                  Text(
                    'Attached: ${_pendingImagePaths.length} image(s), ${_pendingVideoPaths.length} video(s)',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(width: 8),
                  TextButton(
                    onPressed: () => setState(() {
                      _pendingImagePaths.clear();
                      _pendingVideoPaths.clear();
                    }),
                    child: const Text('Clear'),
                  ),
                ],
              ),
            ),
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Row(
              children: [
                IconButton(
                  onPressed: _loading ? null : _toggleVoice,
                  icon: Icon(
                    _voiceListening ? Icons.mic : Icons.mic_none,
                    color: _voiceListening ? Theme.of(context).colorScheme.primary : null,
                  ),
                  tooltip: _voiceListening ? 'Stop voice input' : 'Voice input',
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: TextField(
                    controller: _inputController,
                    decoration: const InputDecoration(
                      hintText: 'Message',
                      border: OutlineInputBorder(),
                    ),
                    onSubmitted: (_) => _send(),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filled(
                  onPressed: _loading
                      ? null
                      : () => _send(),
                  icon: const Icon(Icons.send),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
