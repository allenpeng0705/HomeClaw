import 'dart:async';
import 'dart:io';

import 'package:homeclaw_voice/homeclaw_voice.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import '../core_service.dart';

/// VoiceHandler mixin — voice input, push-to-talk, and voice event stream handling.
///
/// State fields mixed in: voiceListening, voiceTranscript, voiceSubscription,
///   voiceInputCancelled, recordingPushToTalk, voiceRecorder, voice.
///
/// These are public fields (no _) so they're accessible from the using class.
/// Initialize by calling `initVoiceHandler(...)` from the constructor.
mixin VoiceHandler {
  // --- Public state fields (accessible from the using class) ---

  bool voiceListening = false;
  String voiceTranscript = '';
  StreamSubscription<Map<String, dynamic>>? voiceSubscription;
  bool voiceInputCancelled = false;
  bool recordingPushToTalk = false;
  final AudioRecorder voiceRecorder = AudioRecorder();
  final HomeclawVoice voice = HomeclawVoice();

  // --- Callbacks (set by initVoiceHandler) ---

  void Function(String text)? _onSendWithText;
  void Function()? _onScrollToBottom;
  void Function(String transcript)? _onTranscriptChanged;
  void Function(
      List<MapEntry<String, bool>> msgs,
      List<dynamic> imgs,
      List<dynamic> audios,
      List<dynamic> vids,
      List<dynamic> fileLabels,
      List<dynamic> fileRefs)? _onMessageAppend;
  bool Function()? _mountedGetter;
  bool Function()? _loadingGetter;

  // --- Dependencies (set by initVoiceHandler) ---

  CoreService? _coreSvc;
  String? _userId;
  String? _toUserId;
  String? _remotePeerInstanceId;

  // --- Initializer ---

  void initVoiceHandler({
    required CoreService coreService,
    required String userId,
    required String? toUserId,
    required String? remotePeerInstanceId,
    required void Function(String text) onSendWithText,
    required void Function() onScrollToBottom,
    required void Function(String transcript) onTranscriptChanged,
    required void Function(
        List<MapEntry<String, bool>> msgs,
        List<dynamic> imgs,
        List<dynamic> audios,
        List<dynamic> vids,
        List<dynamic> fileLabels,
        List<dynamic> fileRefs) onMessageAppend,
    required bool Function() mountedGetter,
    required bool Function() loadingGetter,
  }) {
    _onSendWithText = onSendWithText;
    _onScrollToBottom = onScrollToBottom;
    _onTranscriptChanged = onTranscriptChanged;
    _onMessageAppend = onMessageAppend;
    _mountedGetter = mountedGetter;
    _loadingGetter = loadingGetter;
    _coreSvc = coreService;
    _userId = userId;
    _toUserId = toUserId;
    _remotePeerInstanceId = remotePeerInstanceId;
  }

  // --- Public (called from UI) ---

  Future<void> toggleVoice() async {
    if (voiceListening) {
      await stopVoiceAndSend();
      return;
    }
    voiceInputCancelled = false;
    try {
      await voiceSubscription?.cancel();
      voiceSubscription = null;
      voiceSubscription = voice.voiceEventStream.listen(
        (event) {
          try {
            if (_mountedGetter?.call() != true) return;
            final partialRaw = event['partial'];
            final finalRaw = event['final'];
            final partial = partialRaw is String
                ? partialRaw
                : (partialRaw != null ? partialRaw.toString() : null);
            final finalText = finalRaw is String
                ? finalRaw
                : (finalRaw != null ? finalRaw.toString() : null);
            if (finalText != null && finalText.isNotEmpty) {
              if (_mountedGetter?.call() != true) return;
              _onTranscriptChanged?.call(finalText);
              if (!voiceInputCancelled && _loadingGetter?.call() != true) {
                _onSendWithText?.call(finalText);
              }
            } else if (partial != null && partial.isNotEmpty) {
              if (_mountedGetter?.call() != true) return;
              _onTranscriptChanged?.call(partial);
            }
          } catch (_) {}
        },
        onError: (e, st) {},
      );
      await voice.startVoiceListening();
      voiceListening = true;
    } catch (_) {
      voiceListening = false;
    }
  }

  Future<void> stopVoiceAndSend() async {
    if (!voiceListening) return;
    await voice.stopVoiceListening();
    voiceSubscription?.cancel();
    voiceSubscription = null;
    final textToSend = voiceTranscript.trim();
    voiceListening = false;
    _onTranscriptChanged?.call('');
    if (textToSend.isNotEmpty) {
      _onSendWithText?.call(textToSend);
    }
  }

  Future<void> startPushToTalk() async {
    final toUserId = _toUserId;
    if (toUserId == null || toUserId.trim().isEmpty) return;
    if (voiceListening) {
      await cancelVoiceInput();
    }
    final hasPermission = await voiceRecorder.hasPermission();
    if (!hasPermission) return;
    try {
      final dir = await getTemporaryDirectory();
      final recordPath = path.join(
          dir.path, 'push_voice_${DateTime.now().millisecondsSinceEpoch}.m4a');
      await voiceRecorder.start(const RecordConfig(), path: recordPath);
      recordingPushToTalk = true;
    } catch (e) {
      recordingPushToTalk = false;
    }
  }

  Future<void> stopPushToTalkAndSend() async {
    if (!recordingPushToTalk) return;
    final coreService = _coreSvc;
    final remotePeerInstanceId = _remotePeerInstanceId;
    try {
      final filePath = await voiceRecorder.stop();
      recordingPushToTalk = false;
      if (filePath == null || filePath.isEmpty) return;
      final file = File(filePath);
      if (!await file.exists()) return;
      if (coreService != null &&
          coreService.federationE2eRequireEncrypted &&
          (remotePeerInstanceId?.trim().isNotEmpty ?? false)) {
        return;
      }
      try {
        final uploaded = await coreService!.uploadFiles([filePath]);
        final audioRef = uploaded.isNotEmpty ? uploaded.first : filePath;
        await coreService.sendUserMessage(
          fromUserId: _userId!,
          toUserId: _toUserId!.trim(),
          text: '',
          audios: [audioRef],
        );
        _onMessageAppend?.call(
          [const MapEntry('(voice)', true)],
          [null],
          [[audioRef]],
          [null],
          [null],
          [null],
        );
        _onScrollToBottom?.call();
      } catch (_) {}
    } catch (_) {
      recordingPushToTalk = false;
    }
  }

  Future<void> cancelVoiceInput() async {
    if (!voiceListening) return;
    voiceInputCancelled = true;
    voiceSubscription?.cancel();
    voiceSubscription = null;
    await voice.stopVoiceListening();
    voiceListening = false;
    _onTranscriptChanged?.call('');
  }

  void voiceDispose() {
    voiceSubscription?.cancel();
    voiceRecorder.dispose();
    voice.dispose();
  }
}
