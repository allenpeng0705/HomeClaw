# homeclaw_voice

Voice input for HomeClaw companion. Wraps the [speech_to_text](https://pub.dev/packages/speech_to_text) package so we get one consistent, stream-based API across platforms.

## Why a separate plugin?

- **Single responsibility:** Voice stays separate from notifications, camera, screen record, etc. in `homeclaw_native`.
- **Better platform coverage:** `speech_to_text` supports Android, iOS, macOS, **Windows (beta)**, and Web. **Linux** uses a small Vosk-based Python helper (see below).
- **Less native code to maintain:** We rely on the community package for platform implementations.

## Usage

```yaml
dependencies:
  homeclaw_voice:
    path: packages/homeclaw_voice
```

```dart
import 'package:homeclaw_voice/homeclaw_voice.dart';

final voice = HomeclawVoice();

// Subscribe first, then start
voice.voiceEventStream.listen((event) {
  print(event['partial'] ?? event['final']);
});

await voice.startVoiceListening(locale: 'en_US');
// ... later
await voice.stopVoiceListening();

voice.dispose(); // when done
```

## API

| Member | Description |
|--------|-------------|
| `voiceEventStream` | `Stream<Map<String, dynamic>>` with `"partial"` and/or `"final"` (transcript text). |
| `startVoiceListening({String? locale})` | Start listening. Subscribe to the stream first. |
| `stopVoiceListening()` | Stop listening. |
| `isAvailable` | `Future<bool>` – whether speech recognition is available. |
| `dispose()` | Close the stream controller; call when done. |

## Platforms

- **Android, iOS, macOS:** Full support via `speech_to_text`.
- **Windows:** Beta support via `speech_to_text_windows`.
- **Linux:** Vosk-based (offline). Requires Python 3 and a Vosk model.
- **Web:** Supported by `speech_to_text`.

### macOS (speech_to_text fix)

On macOS, `speech_to_text` can crash in `listenForSpeech` when installing the input tap (invalid format or zero channels). The fix applied in the plugin (in pub cache or a fork) is: (1) On macOS, call `audioEngine?.prepare()` before reading the input format so the node’s format is valid. (2) Use `inputNode.outputFormat(forBus: 0)` (not `inputFormat`) for the channel check and for the tap. (3) Build an explicit `AVAudioFormat(commonFormat:sampleRate:channels:interleaved:)` from that output format and use it for `installTap`. (4) On macOS only, skip the second `prepare()` before `start()` (prepare is already called earlier). If voice crashes after a `flutter pub upgrade`, re-apply these changes in `SpeechToTextPlugin.swift` in the plugin’s darwin source, or use a path dependency to a forked copy with the fix.

### Linux (Vosk)

Voice on Linux uses a bundled Python script that runs [Vosk](https://alphacephei.com/vosk/) and streams partial/final results to the app.

**1. Install Python deps and a model**

```bash
pip install vosk sounddevice
```

Download a small model (e.g. [vosk-model-small-en-us-0.15](https://alphacephei.com/vosk/models)) and unzip it.

**2. Set the model path**

```bash
export VOSK_MODEL=/path/to/vosk-model-small-en-us-0.15
# or e.g. ~/Downloads/vosk-model-small-en-us-0.15
```

**3. Run the app**

The companion app will use Vosk when `VOSK_MODEL` is set and `python3` is on `PATH`. If something fails (e.g. missing deps), the stream will receive an error and the UI can show a message.

You can improve this later (e.g. ship a small binary, or detect a default model path).
