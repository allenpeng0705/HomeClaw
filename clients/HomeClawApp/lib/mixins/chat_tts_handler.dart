import 'package:flutter_tts/flutter_tts.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// TtsHandler mixin — text-to-speech playback.
///
/// State fields mixed in: ttsAutoSpeak, ttsSpeaking, tts.
///
/// Initialize by calling `initTtsHandler(...)` from the constructor.
mixin TtsHandler {
  static const String _keyTtsAutoSpeak = 'tts_auto_speak';
  bool ttsAutoSpeak = false;
  bool ttsSpeaking = false;
  late final FlutterTts tts;

  // --- Callbacks (set by initTtsHandler) ---

  void Function(bool ttsAutoSpeak)? _onTtsAutoSpeakChanged;
  void Function()? _onTtsStateChanged;
  void Function(String text)? _onTtsError;
  bool Function()? _mountedGetter;
  String? Function()? _lastReplyGetter;
  String? Function()? _voiceInputLocaleGetter;

  // --- Initializer ---

  void initTtsHandler({
    required FlutterTts ttsInstance,
    void Function(bool ttsAutoSpeak)? onTtsAutoSpeakChanged,
    void Function()? onTtsStateChanged,
    void Function(String text)? onTtsError,
    required bool Function() mountedGetter,
    required String? Function() lastReplyGetter,
    required String? Function() voiceInputLocaleGetter,
  }) {
    tts = ttsInstance;
    _onTtsAutoSpeakChanged = onTtsAutoSpeakChanged;
    _onTtsStateChanged = onTtsStateChanged;
    _onTtsError = onTtsError;
    _mountedGetter = mountedGetter;
    _lastReplyGetter = lastReplyGetter;
    _voiceInputLocaleGetter = voiceInputLocaleGetter;
  }

  // --- Public (called from UI) ---

  Future<void> loadTtsAutoSpeak() async {
    final prefs = await SharedPreferences.getInstance();
    if (_mountedGetter?.call() == true) {
      _onTtsAutoSpeakChanged?.call(prefs.getBool(_keyTtsAutoSpeak) ?? false);
    }
  }

  Future<void> setTtsAutoSpeak(bool value) async {
    _onTtsAutoSpeakChanged?.call(value);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyTtsAutoSpeak, value);
  }

  Future<void> speakReplyText(String raw) async {
    final text = _textForTts(raw.trim());
    if (text.isEmpty) return;
    _onTtsStateChanged?.call();
    try {
      final locale = _voiceInputLocaleGetter?.call();
      if (locale != null && locale.isNotEmpty) {
        final ttsLocale = locale.replaceAll('_', '-');
        await tts.setLanguage(ttsLocale);
      }
      await tts.speak(text);
    } catch (e) {
      _onTtsError?.call('TTS: $e');
    } finally {
      _onTtsStateChanged?.call();
    }
  }

  Future<void> stopTts() async {
    try {
      await tts.stop();
    } catch (_) {}
    _onTtsStateChanged?.call();
  }

  Future<void> speakLastReply() async {
    final raw = _lastReplyGetter?.call()?.trim();
    if (raw == null || raw.isEmpty) return;
    final text = _textForTts(raw);
    if (text.isEmpty) return;
    await speakReplyText(raw);
  }

  // --- Static helpers ---

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
        rune == 0x2014 ||
        rune == 0x2018 ||
        rune == 0x2019 ||
        rune == 0x201C ||
        rune == 0x201D;
  }
}
