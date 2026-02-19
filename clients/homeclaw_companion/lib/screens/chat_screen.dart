import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path/path.dart' as path;
import 'package:flutter_tts/flutter_tts.dart';
import 'package:homeclaw_native/homeclaw_native.dart';
import 'package:homeclaw_voice/homeclaw_voice.dart';
import 'package:file_picker/file_picker.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
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
  final List<String> _pendingFilePaths = [];
  static const String _keyTtsAutoSpeak = 'tts_auto_speak';
  bool _ttsAutoSpeak = false;
  static const String _keyVoiceInputLocale = 'voice_input_locale';
  String? _voiceInputLocale;
  bool _ttsSpeaking = false;
  bool? _coreConnected;
  bool _connectionChecking = false;
  Timer? _connectionCheckTimer;

  @override
  void initState() {
    super.initState();
    _loadTtsAutoSpeak();
    _loadVoiceInputLocale();
    _checkCoreConnection();
    _connectionCheckTimer = Timer.periodic(const Duration(seconds: 30), (_) => _checkCoreConnection());
    if (widget.initialMessage != null && widget.initialMessage!.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _inputController.text = widget.initialMessage!;
      });
    }
  }

  Future<void> _checkCoreConnection() async {
    if (_connectionChecking || !mounted) return;
    setState(() => _connectionChecking = true);
    final connected = await widget.coreService.checkConnection();
    if (mounted) setState(() {
      _coreConnected = connected;
      _connectionChecking = false;
    });
  }

  Future<void> _loadTtsAutoSpeak() async {
    final prefs = await SharedPreferences.getInstance();
    if (mounted) setState(() => _ttsAutoSpeak = prefs.getBool(_keyTtsAutoSpeak) ?? false);
  }

  Future<void> _loadVoiceInputLocale() async {
    final prefs = await SharedPreferences.getInstance();
    if (mounted) setState(() => _voiceInputLocale = prefs.getString(_keyVoiceInputLocale));
  }

  Future<void> _setVoiceInputLocale(String? localeId) async {
    setState(() => _voiceInputLocale = localeId?.isEmpty == true ? null : localeId);
    final prefs = await SharedPreferences.getInstance();
    if (localeId == null || localeId.isEmpty) {
      await prefs.remove(_keyVoiceInputLocale);
    } else {
      await prefs.setString(_keyVoiceInputLocale, localeId);
    }
  }

  Future<void> _setTtsAutoSpeak(bool value) async {
    setState(() => _ttsAutoSpeak = value);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyTtsAutoSpeak, value);
  }

  Future<void> _send() async {
    final text = _inputController.text.trim();
    final hasAttachments = _pendingImagePaths.isNotEmpty || _pendingVideoPaths.isNotEmpty || _pendingFilePaths.isNotEmpty;
    if ((text.isEmpty && !hasAttachments) || _loading) return;
    _inputController.clear();
    final imagesToSend = List<String>.from(_pendingImagePaths);
    final videosToSend = List<String>.from(_pendingVideoPaths);
    final filesToSend = List<String>.from(_pendingFilePaths);
    setState(() {
      _pendingImagePaths.clear();
      _pendingVideoPaths.clear();
      _pendingFilePaths.clear();
      _messages.add(MapEntry(text.isEmpty ? '(attachment)' : text, true));
      _loading = true;
    });
    try {
      List<String> imagePaths = [];
      List<String> videoPaths = [];
      List<String> filePaths = [];
      final allToUpload = [...imagesToSend, ...videosToSend, ...filesToSend];
      if (allToUpload.isNotEmpty) {
        try {
          final uploaded = await widget.coreService.uploadFiles(allToUpload);
          final nI = imagesToSend.length;
          final nV = videosToSend.length;
          imagePaths = uploaded.take(nI).toList();
          videoPaths = uploaded.skip(nI).take(nV).toList();
          filePaths = uploaded.skip(nI + nV).toList();
        } catch (_) {
          // Same fallback as web chat: if upload fails, send images as data URLs so message still goes through.
          final dataUrls = await _filePathsToImageDataUrls(imagesToSend);
          if (dataUrls.isNotEmpty) {
            imagePaths = dataUrls;
          }
          // Videos and documents not sent on upload failure to avoid huge payloads.
        }
      }
      final reply = await widget.coreService.sendMessage(
        text.isEmpty ? 'See attached.' : text,
        images: imagePaths.isEmpty ? null : imagePaths,
        videos: videoPaths.isEmpty ? null : videoPaths,
        files: filePaths.isEmpty ? null : filePaths,
      );
      if (mounted) {
        _lastReply = reply;
        setState(() {
          _messages.add(MapEntry(reply.isEmpty ? '(no reply)' : reply, false));
          _loading = false;
        });
        final preview = reply.isEmpty ? 'No reply' : (reply.length > 80 ? '${reply.substring(0, 80)}…' : reply);
        await _native.showNotification(title: 'HomeClaw', body: preview);
        if (_ttsAutoSpeak && reply.isNotEmpty) _speakReplyText(reply);
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

  /// Stop voice listening and send the current transcript.
  Future<void> _stopVoiceAndSend() async {
    if (!_voiceListening) return;
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
  }

  /// Stop voice listening and discard the transcript (do not send).
  Future<void> _cancelVoiceInput() async {
    if (!_voiceListening) return;
    await _voice.stopVoiceListening();
    _voiceSubscription?.cancel();
    _voiceSubscription = null;
    setState(() {
      _voiceListening = false;
      _voiceTranscript = '';
      _inputController.text = '';
    });
  }

  Future<void> _toggleVoice() async {
    if (_voiceListening) {
      await _stopVoiceAndSend();
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
      await _voice.startVoiceListening(locale: _voiceInputLocale);
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

  /// Copy a picked file (e.g. from Photos app) to a persistent temp file so preview and upload work.
  /// On macOS, the path from image_picker can be short-lived or security-scoped; we try path first, then readAsBytes.
  /// Returns (path, null) on success, (null, errorMessage) on failure.
  static Future<({String? path, String? error})> _copyPickedFileToTemp(XFile xFile, {String defaultExt = '.jpg'}) async {
    final dir = await getTemporaryDirectory();
    // Ensure subdir exists (macOS sandbox Caches path may not exist on first use).
    final picksDir = Directory('${dir.path}/homeclaw_picks');
    await picksDir.create(recursive: true);
    final ext = path.extension(xFile.name).isEmpty ? defaultExt : path.extension(xFile.name);
    final dest = File('${picksDir.path}/pick_${DateTime.now().millisecondsSinceEpoch}$ext');

    // 1) Try copy via path (works if path is still valid, e.g. camera or some galleries).
    final rawPath = xFile.path;
    if (rawPath != null && rawPath.isNotEmpty) {
      try {
        final srcPath = rawPath.startsWith('file://') ? Uri.parse(rawPath).path : rawPath;
        final src = File(srcPath);
        if (await src.exists()) {
          await src.copy(dest.path);
          if (await dest.exists()) return (path: dest.absolute.path, error: null);
        }
      } catch (_) {}
    }

    // 2) Read bytes from XFile (handles security-scoped / in-memory on macOS).
    try {
      final bytes = await xFile.readAsBytes();
      await dest.writeAsBytes(bytes);
      if (await dest.exists()) return (path: dest.absolute.path, error: null);
      return (path: null, error: 'File was written but not found at ${dest.path}');
    } catch (e) {
      return (path: null, error: e.toString());
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
      if (mounted) {
        showDialog(
          context: context,
          barrierDismissible: false,
          builder: (_) => AlertDialog(
            content: Row(
              children: [
                const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)),
                const SizedBox(width: 16),
                Expanded(child: Text(source == ImageSource.camera ? 'Opening camera…' : 'Choosing photo…', textAlign: TextAlign.start)),
              ],
            ),
          ),
        );
      }
      final xFile = await _imagePicker.pickImage(source: source);
      if (mounted) Navigator.of(context).pop();
      if (xFile == null || !mounted) return;
      // Copy to app temp so preview/upload work (macOS Photos returns short-lived paths).
      final result = await _copyPickedFileToTemp(xFile);
      if (result.path == null || !mounted) {
        setState(() => _messages.add(MapEntry('Photo error: ${result.error ?? "could not read or copy the image."}', false)));
        return;
      }
      final filePath = result.path!;
      final added = await _showMediaPreview(context, type: 'photo', filePath: filePath, label: 'Add this photo to your message?');
      if (added && mounted) {
        setState(() => _pendingImagePaths.add(filePath));
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
      if (mounted) {
        showDialog(
          context: context,
          barrierDismissible: false,
          builder: (_) => AlertDialog(
            content: Row(
              children: [
                const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)),
                const SizedBox(width: 16),
                Expanded(child: Text(source == ImageSource.camera ? 'Recording video…' : 'Choosing video…', textAlign: TextAlign.start)),
              ],
            ),
          ),
        );
      }
      final xFile = await _imagePicker.pickVideo(source: source, maxDuration: const Duration(seconds: 30));
      if (mounted) Navigator.of(context).pop();
      if (xFile == null || !mounted) return;
      // Copy to app temp when from gallery so path is stable (macOS Photos short-lived path).
      String? filePath;
      if (source == ImageSource.gallery) {
        final result = await _copyPickedFileToTemp(xFile, defaultExt: '.mp4');
        filePath = result.path;
        if (filePath == null || !mounted) {
          setState(() => _messages.add(MapEntry('Video error: ${result.error ?? "could not read or copy the video."}', false)));
          return;
        }
      } else {
        filePath = xFile.path;
      }
      if (filePath == null || !mounted) {
        setState(() => _messages.add(MapEntry('Video error: could not read or copy the video.', false)));
        return;
      }
      final added = await _showMediaPreview(context, type: 'video', filePath: filePath, label: 'Add this video to your message?');
      if (added && mounted) {
        setState(() => _pendingVideoPaths.add(filePath!));
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

  Future<void> _attachDocument() async {
    try {
      final result = await FilePicker.platform.pickFiles(
        allowMultiple: true,
        type: FileType.custom,
        allowedExtensions: ['pdf', 'txt', 'md', 'doc', 'docx', 'rtf', 'csv', 'xls', 'xlsx', 'odt', 'ods'],
      );
      if (result == null || result.files.isEmpty || !mounted) return;
      final paths = result.files.where((f) => f.path != null).map((f) => f.path!).toList();
      if (paths.isEmpty) return;
      setState(() => _pendingFilePaths.addAll(paths));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${paths.length} file(s) attached. Type a message and Send to include them.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Attach file error: $e')));
      }
    }
  }

  Future<bool> _showMediaPreview(BuildContext context, {required String type, required String filePath, required String label}) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(type == 'photo' ? 'Preview photo' : 'Preview video'),
        content: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 220, minWidth: 280, maxWidth: 560, maxHeight: 600),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
              if (type == 'photo')
                SizedBox(
                  height: 200,
                  width: 560,
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: Image.file(
                      File(filePath),
                      fit: BoxFit.contain,
                      height: 200,
                      width: 560,
                      frameBuilder: (_, child, frame, __) {
                        if (frame == null) {
                          return Container(
                            height: 200,
                            width: 560,
                            color: Theme.of(ctx).colorScheme.surfaceContainerHighest,
                            child: const Center(child: SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2))),
                          );
                        }
                        return child;
                      },
                      errorBuilder: (_, __, ___) => Center(
                        child: Icon(Icons.broken_image_outlined, size: 48, color: Theme.of(ctx).colorScheme.outline),
                      ),
                    ),
                  ),
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

  /// Speak a reply (filtered for TTS). Used for auto-speak and for "Speak last reply".
  /// Uses the same language as voice input when set (Voice input language in settings).
  Future<void> _speakReplyText(String raw) async {
    final text = _textForTts(raw.trim());
    if (text.isEmpty) return;
    if (mounted) setState(() => _ttsSpeaking = true);
    try {
      if (_voiceInputLocale != null && _voiceInputLocale!.isNotEmpty) {
        // Voice input locale is e.g. "en_US" or "zh_CN"; TTS often accepts "en-US" / "zh-CN".
        final ttsLocale = _voiceInputLocale!.replaceAll('_', '-');
        await _tts.setLanguage(ttsLocale);
      }
      await _tts.speak(text);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('TTS: $e')));
    } finally {
      if (mounted) setState(() => _ttsSpeaking = false);
    }
  }

  Future<void> _stopTts() async {
    try {
      await _tts.stop();
    } catch (_) {}
    if (mounted) setState(() => _ttsSpeaking = false);
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
    await _speakReplyText(raw);
  }

  Future<void> _showVoiceAndTtsLanguages() async {
    List<String> voiceLocales = [];
    List<String> ttsLanguages = [];
    try {
      voiceLocales = List<String>.from(await _voice.getAvailableLocales());
      final ttsList = await _tts.getLanguages;
      ttsLanguages = ttsList is List
          ? List<String>.from((ttsList as List).map((e) => e.toString()))
          : [];
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not load languages: $e')));
      }
      return;
    }
    if (!mounted) return;
    final voiceOptions = ['System default', ...voiceLocales];
    String currentVoiceDisplay = _voiceInputLocale == null
        ? 'System default'
        : voiceLocales.firstWhere((s) => s.startsWith(_voiceInputLocale!), orElse: () => _voiceInputLocale!);

    await showDialog<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('Voice input & TTS languages'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Voice input language', style: Theme.of(ctx).textTheme.titleSmall),
                const SizedBox(height: 4),
                DropdownButton<String>(
                  value: voiceOptions.contains(currentVoiceDisplay) ? currentVoiceDisplay : voiceOptions.first,
                  isExpanded: true,
                  items: voiceOptions.map((s) => DropdownMenuItem(value: s, child: Text(s))).toList(),
                  onChanged: (s) async {
                    if (s == null) return;
                    final localeId = s == 'System default' ? null : (s.contains(' (') ? s.substring(0, s.indexOf(' (')) : s);
                    await _setVoiceInputLocale(localeId);
                    currentVoiceDisplay = s;
                    setDialogState(() {});
                  },
                ),
                const SizedBox(height: 16),
                Text('Available voice locales (microphone)', style: Theme.of(ctx).textTheme.titleSmall),
                const SizedBox(height: 4),
                Text(
                  voiceLocales.isEmpty ? 'None detected' : voiceLocales.join(', '),
                  style: Theme.of(ctx).textTheme.bodySmall,
                ),
                const SizedBox(height: 16),
                Text('TTS (speak replies)', style: Theme.of(ctx).textTheme.titleSmall),
                const SizedBox(height: 4),
                Text(
                  ttsLanguages.isEmpty ? 'None detected' : ttsLanguages.join(', '),
                  style: Theme.of(ctx).textTheme.bodySmall,
                ),
                const SizedBox(height: 12),
                Text(
                  'Voice input and TTS (speak replies) both use the language selected above. Set it to the language you speak (e.g. 中文 for Chinese). Add more in system settings if needed.',
                  style: Theme.of(ctx).textTheme.bodySmall?.copyWith(color: Theme.of(ctx).colorScheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('OK')),
          ],
        ),
      ),
    );
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
    _connectionCheckTimer?.cancel();
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
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
            child: Center(
              child: Tooltip(
                message: _connectionChecking
                    ? 'Checking connection…'
                    : (_coreConnected == true
                        ? 'Connected to Core (tap to recheck)'
                        : (_coreConnected == false
                            ? 'Not connected to Core. Tap to recheck or open Settings.'
                            : 'Connection unknown')),
                child: Material(
                  type: MaterialType.transparency,
                  child: InkWell(
                    onTap: _checkCoreConnection,
                    borderRadius: BorderRadius.circular(12),
                    child: SizedBox(
                      width: 24,
                      height: 24,
                      child: Center(
                        child: Container(
                          width: 12,
                          height: 12,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: _connectionChecking
                                ? Theme.of(context).colorScheme.outline
                                : (_coreConnected == true
                                    ? Colors.green
                                    : (_coreConnected == false
                                        ? Theme.of(context).colorScheme.error
                                        : Theme.of(context).colorScheme.outline)),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
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
                case 'document':
                  await _attachDocument();
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
                case 'stop_tts':
                  await _stopTts();
                  break;
              }
            },
            itemBuilder: (context) => [
              const PopupMenuItem(value: 'photo', child: Text('Take photo')),
              const PopupMenuItem(value: 'video', child: Text('Record video')),
              const PopupMenuItem(value: 'document', child: Text('Attach file')),
              const PopupMenuItem(value: 'screen', child: Text('Record screen')),
              const PopupMenuItem(value: 'run', child: Text('Run command')),
              const PopupMenuItem(value: 'speak', child: Text('Speak last reply')),
              const PopupMenuItem(value: 'stop_tts', child: Text('Stop speaking')),
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
                        onPressed: _cancelVoiceInput,
                        icon: const Icon(Icons.cancel_outlined),
                        label: const Text('Cancel'),
                      ),
                      TextButton.icon(
                        onPressed: _stopVoiceAndSend,
                        icon: const Icon(Icons.stop_circle),
                        label: const Text('Stop'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          if (_ttsSpeaking)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              child: Material(
                color: Theme.of(context).colorScheme.secondaryContainer.withOpacity(0.5),
                borderRadius: BorderRadius.circular(12),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  child: Row(
                    children: [
                      Icon(
                        Icons.volume_up,
                        color: Theme.of(context).colorScheme.onSecondaryContainer,
                        size: 28,
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          'Speaking reply…',
                          style: Theme.of(context).textTheme.labelLarge?.copyWith(
                                color: Theme.of(context).colorScheme.onSecondaryContainer,
                              ),
                        ),
                      ),
                      TextButton.icon(
                        onPressed: _stopTts,
                        icon: const Icon(Icons.stop_circle),
                        label: const Text('Stop'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          if (_pendingImagePaths.isNotEmpty || _pendingVideoPaths.isNotEmpty || _pendingFilePaths.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      Text(
                        'Attached — add a message below (optional), then Send',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Theme.of(context).colorScheme.primary,
                        ),
                      ),
                      const Spacer(),
                      TextButton(
                        onPressed: () => setState(() {
                          _pendingImagePaths.clear();
                          _pendingVideoPaths.clear();
                          _pendingFilePaths.clear();
                        }),
                        child: const Text('Clear all'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        ..._pendingImagePaths.map((p) => Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: Stack(
                            clipBehavior: Clip.none,
                            children: [
                              SizedBox(
                                width: 64,
                                height: 64,
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(8),
                                  child: Image.file(
                                    File(p),
                                    fit: BoxFit.cover,
                                    width: 64,
                                    height: 64,
                                    frameBuilder: (_, child, frame, __) {
                                      if (frame == null) {
                                        return Container(
                                          width: 64,
                                          height: 64,
                                          color: Theme.of(context).colorScheme.surfaceContainerHighest,
                                          child: const Center(child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))),
                                        );
                                      }
                                      return child;
                                    },
                                    errorBuilder: (_, __, ___) => Container(
                                      width: 64,
                                      height: 64,
                                      color: Theme.of(context).colorScheme.surfaceContainerHighest,
                                      child: Icon(Icons.broken_image_outlined, color: Theme.of(context).colorScheme.outline),
                                    ),
                                  ),
                                ),
                              ),
                              Positioned(
                                top: -4,
                                right: -4,
                                child: Material(
                                  color: Theme.of(context).colorScheme.errorContainer,
                                  shape: const CircleBorder(),
                                  child: InkWell(
                                    onTap: () => setState(() => _pendingImagePaths.remove(p)),
                                    customBorder: const CircleBorder(),
                                    child: const SizedBox(width: 22, height: 22, child: Icon(Icons.close, size: 16)),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        )),
                        ..._pendingVideoPaths.map((p) => Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: _AttachmentChip(
                            icon: Icons.videocam,
                            label: path.basename(p),
                            onRemove: () => setState(() => _pendingVideoPaths.remove(p)),
                          ),
                        )),
                        ..._pendingFilePaths.map((p) => Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: _AttachmentChip(
                            icon: Icons.insert_drive_file,
                            label: path.basename(p),
                            onRemove: () => setState(() => _pendingFilePaths.remove(p)),
                          ),
                        )),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8.0, vertical: 4.0),
            child: Row(
              children: [
                Icon(Icons.volume_up, size: 20, color: Theme.of(context).colorScheme.onSurfaceVariant),
                const SizedBox(width: 6),
                Text('Speak replies', style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(width: 8),
                Switch(
                  value: _ttsAutoSpeak,
                  onChanged: (value) => _setTtsAutoSpeak(value),
                ),
                if (_ttsSpeaking)
                  Padding(
                    padding: const EdgeInsets.only(left: 8.0),
                    child: FilledButton.tonalIcon(
                      onPressed: _stopTts,
                      icon: const Icon(Icons.stop_circle, size: 20),
                      label: const Text('Stop speaking'),
                    ),
                  ),
                IconButton(
                  icon: const Icon(Icons.info_outline, size: 20),
                  tooltip: 'Voice input & TTS supported languages',
                  onPressed: _showVoiceAndTtsLanguages,
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
                    decoration: InputDecoration(
                      hintText: (_pendingImagePaths.isNotEmpty || _pendingVideoPaths.isNotEmpty || _pendingFilePaths.isNotEmpty)
                          ? 'Add a message (optional)'
                          : 'Message',
                      border: const OutlineInputBorder(),
                    ),
                    onSubmitted: (_) => _send(),
                  ),
                ),
                if (_ttsSpeaking) ...[
                  const SizedBox(width: 4),
                  IconButton(
                    onPressed: _stopTts,
                    icon: const Icon(Icons.stop_circle),
                    tooltip: 'Stop speaking',
                    style: IconButton.styleFrom(
                      foregroundColor: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ],
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

/// Chip showing one attached video or document with remove button.
class _AttachmentChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onRemove;

  const _AttachmentChip({required this.icon, required this.label, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SizedBox(
      height: 64,
      child: Material(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          onTap: null,
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: const EdgeInsets.only(left: 10, right: 4, top: 8, bottom: 8),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, size: 28, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 120),
                  child: Text(
                    label,
                    style: theme.textTheme.bodySmall,
                    overflow: TextOverflow.ellipsis,
                    maxLines: 2,
                  ),
                ),
                const SizedBox(width: 4),
                Material(
                  color: theme.colorScheme.errorContainer,
                  shape: const CircleBorder(),
                  child: InkWell(
                    onTap: onRemove,
                    customBorder: const CircleBorder(),
                    child: const SizedBox(width: 22, height: 22, child: Icon(Icons.close, size: 16)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
