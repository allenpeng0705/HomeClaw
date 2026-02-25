import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:speech_to_text/speech_to_text.dart';

import 'vosk_script.dart';

/// Voice input for HomeClaw companion.
///
/// Uses [speech_to_text] on Android, iOS, macOS, Windows, Web. On Linux uses
/// Vosk via a small Python helper (requires: python3, pip install vosk sounddevice,
/// and VOSK_MODEL or --model path).
class HomeclawVoice {
  final SpeechToText _speech = SpeechToText();
  final StreamController<Map<String, dynamic>> _eventController =
      StreamController<Map<String, dynamic>>.broadcast();

  bool _initialized = false;
  bool _listening = false;
  bool? _linuxVoskAvailable;
  Process? _voskProcess;
  File? _voskScriptFile;
  Directory? _voskTempDir;

  /// Stream of voice events. Maps contain "partial" and/or "final" (String transcript).
  Stream<Map<String, dynamic>> get voiceEventStream => _eventController.stream;

  /// Available voice-input locales (language codes / names). Empty on Linux (Vosk uses model language).
  Future<List<String>> getAvailableLocales() async {
    if (Platform.isLinux) {
      final modelPath = Platform.environment['VOSK_MODEL'];
      if (modelPath == null || modelPath.isEmpty) return [];
      return ['Vosk model language (see VOSK_MODEL)'];
    }
    if (!_initialized) {
      _initialized = await _speech.initialize(onError: (_) {}, onStatus: (_) {});
    }
    final list = await _speech.locales();
    return list.map((l) => l.localeId + (l.name.isNotEmpty ? ' (${l.name})' : '')).toList();
  }

  /// Whether speech recognition is available on this platform.
  Future<bool> get isAvailable async {
    if (Platform.isLinux) {
      if (_linuxVoskAvailable != null) return _linuxVoskAvailable!;
      _linuxVoskAvailable = await _checkLinuxVosk();
      return _linuxVoskAvailable!;
    }
    if (!_initialized) {
      _initialized = await _speech.initialize(
        onError: (_) {},
        onStatus: (_) {},
      );
    }
    return _speech.isAvailable;
  }

  Future<bool> _checkLinuxVosk() async {
    final modelPath = Platform.environment['VOSK_MODEL'];
    if (modelPath == null || modelPath.isEmpty) return false;
    try {
      final result = await Process.run('which', ['python3']);
      if (result.exitCode != 0) return false;
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Start voice listening. Subscribe to [voiceEventStream] first to receive events.
  ///
  /// [locale] e.g. "en_US". Omit for system default. (Ignored on Linux/Vosk.)
  Future<void> startVoiceListening({String? locale}) async {
    if (_listening) return;

    if (Platform.isLinux) {
      await _startVoskListening();
      return;
    }

    if (!_initialized) {
      _initialized = await _speech.initialize(
        onError: (e) => _eventController.addError(Exception(e.errorMsg)),
        onStatus: (_) {},
      );
    }
    if (!_speech.isAvailable) {
      _eventController.addError(Exception('Speech recognition not available'));
      return;
    }
    _listening = true;
    await _speech.listen(
      onResult: (result) {
        final text = result.recognizedWords;
        if (text.isEmpty) return;
        if (result.finalResult) {
          _eventController.add({'final': text});
        } else {
          _eventController.add({'partial': text});
        }
      },
      localeId: locale,
      listenOptions: SpeechListenOptions(
        partialResults: true,
        listenMode: ListenMode.dictation,
      ),
    );
  }

  Future<void> _startVoskListening() async {
    final modelPath = Platform.environment['VOSK_MODEL'];
    if (modelPath == null || modelPath.isEmpty) {
      _eventController.addError(Exception(
        'On Linux set VOSK_MODEL to the path of a Vosk model (e.g. ~/vosk-model-small-en-us-0.15). '
        'Install: pip install vosk sounddevice',
      ));
      return;
    }
    // Use embedded script (not an asset) so .py is never in the app bundle (iOS signing).
    const scriptContent = voskListenScript;
    try {
      _voskTempDir = Directory.systemTemp.createTempSync('vosk_');
      _voskScriptFile = File('${_voskTempDir!.path}/vosk_listen.py');
      await _voskScriptFile!.writeAsString(scriptContent);
    } catch (e) {
      _eventController.addError(Exception('Failed to write Vosk script: $e'));
      return;
    }
    try {
      _voskProcess = await Process.start(
        'python3',
        [_voskScriptFile!.path, '--model', modelPath],
        environment: {...Platform.environment, 'VOSK_MODEL': modelPath},
        runInShell: false,
      );
    } catch (e) {
      _eventController.addError(Exception('Failed to start Vosk: $e'));
      _voskScriptFile?.deleteSync();
      _voskTempDir?.deleteSync(recursive: true);
      _voskTempDir = null;
      return;
    }
    _listening = true;
    _voskProcess!.stderr.listen((_) {});
    _voskProcess!.stdout
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen((line) {
      line = line.trim();
      if (line.isEmpty) return;
      try {
        final map = jsonDecode(line) as Map<String, dynamic>;
        final partial = map['partial'] as String?;
        final finalText = map['final'] as String?;
        if (finalText != null && finalText.isNotEmpty) {
          _eventController.add({'final': finalText});
        } else if (partial != null && partial.isNotEmpty) {
          _eventController.add({'partial': partial});
        }
      } catch (_) {}
    });
    _voskProcess!.exitCode.then((_) {
      _listening = false;
      _voskProcess = null;
      _voskScriptFile?.deleteSync();
      _voskScriptFile = null;
      _voskTempDir?.deleteSync(recursive: true);
      _voskTempDir = null;
    });
  }

  /// Stop voice listening.
  Future<void> stopVoiceListening() async {
    if (!_listening) return;

    if (Platform.isLinux && _voskProcess != null) {
      _voskProcess!.kill(ProcessSignal.sigterm);
      _voskProcess = null;
      _voskScriptFile?.deleteSync();
      _voskScriptFile = null;
      _voskTempDir?.deleteSync(recursive: true);
      _voskTempDir = null;
      _listening = false;
      return;
    }

    _listening = false;
    await _speech.stop();
  }

  /// Release resources. Call when done (e.g. app dispose).
  void dispose() {
    if (_voskProcess != null) {
      _voskProcess!.kill(ProcessSignal.sigterm);
      _voskProcess = null;
    }
    _voskScriptFile?.deleteSync();
    _voskScriptFile = null;
    _voskTempDir?.deleteSync(recursive: true);
    _voskTempDir = null;
    _eventController.close();
  }
}
