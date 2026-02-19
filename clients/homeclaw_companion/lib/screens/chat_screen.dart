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
    try {
      // Let the popup menu close before opening the picker (avoids dialog behind window on macOS).
      await Future<void>.delayed(const Duration(milliseconds: 300));
      if (!mounted) return;
      // On macOS, image_picker camera requires a cameraDelegate; use gallery to pick a photo.
      final source = Platform.isMacOS ? ImageSource.gallery : ImageSource.camera;
      final xFile = await _imagePicker.pickImage(source: source);
      if (xFile == null || !mounted) return;
      setState(() {
        _pendingImagePaths.add(xFile.path);
      });
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Photo attached. Type a message and Send to include it.')));
    } catch (e) {
      if (mounted) setState(() => _messages.add(MapEntry('Camera error: $e', false)));
    }
  }

  Future<void> _recordVideo() async {
    try {
      await Future<void>.delayed(const Duration(milliseconds: 300));
      if (!mounted) return;
      // On macOS, image_picker camera requires a cameraDelegate; use gallery to pick a video.
      final source = Platform.isMacOS ? ImageSource.gallery : ImageSource.camera;
      final xFile = await _imagePicker.pickVideo(
        source: source,
        maxDuration: const Duration(seconds: 30),
      );
      if (xFile == null || !mounted) return;
      setState(() {
        _pendingVideoPaths.add(xFile.path);
      });
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Video attached. Type a message and Send to include it.')));
    } catch (e) {
      if (mounted) setState(() => _messages.add(MapEntry('Video error: $e', false)));
    }
  }

  Future<void> _recordScreen() async {
    try {
      await Future<void>.delayed(const Duration(milliseconds: 300));
      if (!mounted) return;
      final path = await _native.startScreenRecord(durationSec: 10, includeAudio: false);
      if (!mounted) return;
      if (path != null && path.isNotEmpty) {
        setState(() {
          _pendingVideoPaths.add(path);
        });
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Screen recording attached. Send to include it.')));
      } else {
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
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Screen record error: $e')));
    }
  }

  Future<void> _speakLastReply() async {
    final text = _lastReply?.trim();
    if (text == null || text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No reply to speak')),
      );
      return;
    }
    try {
      await _tts.speak(text);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('TTS: $e')));
    }
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
    final cmd = await showDialog<String>(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: const Text('Run command'),
          content: TextField(
            controller: cmdController,
            autofocus: true,
            decoration: const InputDecoration(
              hintText: 'e.g. ls -la or use regex in Settings',
              border: OutlineInputBorder(),
            ),
            onSubmitted: (v) => Navigator.of(ctx).pop(v),
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
