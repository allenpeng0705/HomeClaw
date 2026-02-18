# Why is "Record a 3 second video with microphone" so slow?

This doc summarizes where time is spent and what we can do about it.

## End-to-end flow (where time goes)

| Step | Where | What happens | Typical time |
|------|--------|----------------|--------------|
| 1 | User → Core | Message delivered (e.g. WebChat) | &lt;1s |
| 2 | Core → LLM | Model decides to call `route_to_plugin(homeclaw-browser, node_camera_clip, …)` | **5–30+ s** |
| 3 | Core → Plugin | HTTP POST to plugin `/run`; Core **blocks** until plugin responds | **see below** |
| 4 | Plugin → Node | WebSocket send command to Nodes page tab; plugin **blocks** until node responds | **see below** |
| 5 | Node (browser) | See "Node (browser) breakdown" | **often 20s–2+ min** |
| 6 | Node → Plugin | WebSocket send result (large data URL) | 1–10s |
| 7 | Plugin → Core | HTTP 200 + JSON (large body); Core → user | &lt;1s |

So total time ≈ **LLM time** + **Node (browser) time** + **transfer time**. The dominant variable is **Node (browser)**.

---

## Node (browser) breakdown — where the slowness is

The Nodes page (`public/nodes.html`) does the following for `camera_clip`:

1. **`getUserMedia({ video: true, audio: true })`**  
   - First time: permission prompt + device init → **1–5 s**.  
   - Later: usually fast if already granted.

2. **`MediaRecorder.start(200)`**  
   - Start recording; 200 ms timeslice. Negligible.

3. **`setTimeout(durationMs)`**  
   - Wait for the requested duration (e.g. 3 s). **~3 s** by design.

4. **`recorder.stop()` then `await onstop`** ← **main bottleneck**  
   - After `stop()`, the browser **encodes** the full clip (video + audio) into WebM.  
   - This runs in the browser’s media pipeline; we cannot control it from JS.  
   - **Often 10–60+ seconds** depending on device, resolution, and whether audio is included.  
   - Default camera resolution (e.g. 1280×720 or higher) and default bitrate make the encoded blob large and slow to encode.

5. **`new Blob(chunks, { type: 'video/webm' })`**  
   - Quick.

6. **`FileReader.readAsDataURL(blob)`**  
   - Converts the whole blob to base64.  
   - For a 2–10 MB blob this is **1–5 s** and blocks the main thread.  
   - Base64 is ~33% larger than binary, so the string we send is big.

7. **`sendResult({ media: dataUrl })`**  
   - Sends a **multi‑megabyte string** over the WebSocket.  
   - **1–5+ s** depending on size and connection.

So most of the delay is:

- **Encoding** (step 4): 10–60+ s.  
- **Base64 + send** (steps 6–7): a few seconds more.

That’s why a “3 second” clip can take **30 s to 2+ minutes** end‑to‑end on the node.

---

## What we can do

### 1. Reduce video resolution (done)

- In the Nodes page, request **constrained video** from `getUserMedia`, e.g.  
  `{ video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: useAudio }`.  
- Smaller frames → smaller blob → **faster encoding**, **faster base64**, **faster WebSocket**.  
- Trade-off: lower resolution; acceptable for “short clip” use.

### 2. Timeouts (already in place)

- **Core → plugin**: 420 s (so Core doesn’t ReadTimeout before the plugin answers).  
- **Plugin → node**: 300 s (CMD_TIMEOUT_MS).  
- These avoid hard failures when encoding is slow; they don’t make encoding faster.

### 3. LLM time

- Depends on model and prompt. Can be 5–30+ s.  
- Out of scope for this investigation; we only optimize the node path here.

### 4. Future ideas (not implemented)

- **Stream the result** instead of one huge data URL: e.g. chunk the blob and send in parts; plugin reassembles. Reduces “one big send” but adds complexity.  
- **Lower bitrate / codec options**: `MediaRecorder` has limited support for `videoBitsPerSecond`; could experiment per‑browser.  
- **Skip base64**: send binary over WebSocket (e.g. ArrayBuffer). Plugin and Core would need to support binary or re‑encode for storage/channel; more work.

---

## Summary

- **Why it’s slow:**  
  - LLM takes several seconds.  
  - In the browser, **encoding** after `MediaRecorder.stop()` dominates (10–60+ s).  
  - Then base64 + sending a multi‑MB string add more seconds.  
- **What we did:**  
  - Document the flow and bottlenecks (this file).  
  - Request **640×480 (or similar) video** in the Nodes page to reduce encoding and transfer time.  
  - Keep timeouts (420s Core, 300s plugin→node) so slow runs don’t hit ReadTimeout/503.
