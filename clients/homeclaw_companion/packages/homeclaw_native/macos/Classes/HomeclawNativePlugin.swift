import AVFoundation
import Cocoa
import FlutterMacOS
import ScreenCaptureKit
import UserNotifications

public class HomeclawNativePlugin: NSObject, FlutterPlugin {
  public static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(name: "homeclaw_native", binaryMessenger: registrar.messenger)
    let instance = HomeclawNativePlugin()
    registrar.addMethodCallDelegate(instance, channel: channel)
  }

  public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "getPlatformVersion":
      result("macOS " + ProcessInfo.processInfo.operatingSystemVersionString)
    case "showNotification":
      guard let args = call.arguments as? [String: Any],
            let title = args["title"] as? String,
            let body = args["body"] as? String else {
        result(FlutterError(code: "INVALID_ARGS", message: "title and body required", details: nil))
        return
      }
      showNotification(title: title, body: body, result: result)
    case "getTraySupported":
      result(true)
    case "setTrayIcon":
      result(nil)
    case "startScreenRecord":
      let args = call.arguments as? [String: Any] ?? [:]
      let durationSec = args["durationSec"] as? Int ?? 10
      let includeAudio = args["includeAudio"] as? Bool ?? false
      startScreenRecord(durationSec: durationSec, includeAudio: includeAudio, result: result)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func showNotification(title: String, body: String, result: @escaping FlutterResult) {
    let center = UNUserNotificationCenter.current()
    center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
      guard granted else {
        DispatchQueue.main.async { result(nil) }
        return
      }
      let content = UNMutableNotificationContent()
      content.title = title
      content.body = body
      content.sound = .default
      let request = UNNotificationRequest(
        identifier: "homeclaw-\(UUID().uuidString)",
        content: content,
        trigger: UNTimeIntervalNotificationTrigger(timeInterval: 0.1, repeats: false)
      )
      center.add(request) { err in
        DispatchQueue.main.async {
          if let err = err {
            result(FlutterError(code: "NOTIFICATION_FAILED", message: err.localizedDescription, details: nil))
          } else {
            result(nil)
          }
        }
      }
    }
  }

  private func startScreenRecord(durationSec: Int, includeAudio: Bool, result: @escaping FlutterResult) {
    Task {
      let path: String? = await recordScreen(durationSec: durationSec, includeAudio: includeAudio)
      await MainActor.run {
        result(path)
      }
    }
  }

  private func recordScreen(durationSec: Int, includeAudio: Bool) async -> String? {
    let content: SCShareableContent
    do {
      content = try await SCShareableContent.current
    } catch {
      return nil
    }
    guard let display = content.displays.first else { return nil }
    let filter = SCContentFilter(display: display, excludingWindows: [])
    let config = SCStreamConfiguration()
    config.width = Int(display.width)
    config.height = Int(display.height)
    if config.width <= 0 || config.height <= 0 {
      config.width = 1920
      config.height = 1080
    }
    config.minimumFrameInterval = CMTime(value: 1, timescale: 30)
    let tempDir = FileManager.default.temporaryDirectory
    let outURL = tempDir.appendingPathComponent("homeclaw_screen_\(UUID().uuidString).mov")
    let writer: AVAssetWriter
    do {
      writer = try AVAssetWriter(url: outURL, fileType: .mov)
    } catch {
      return nil
    }
    let videoSettings: [String: Any] = [
      AVVideoCodecKey: AVVideoCodecType.h264,
      AVVideoWidthKey: config.width,
      AVVideoHeightKey: config.height,
    ]
    let videoInput = AVAssetWriterInput(mediaType: .video, outputSettings: videoSettings)
    videoInput.expectsMediaDataInRealTime = true
    writer.add(videoInput)
    let queue = DispatchQueue(label: "homeclaw.screen.record")
    let streamOutput = StreamOutput(videoInput: videoInput, writer: writer, queue: queue)
    let stream: SCStream
    do {
      stream = SCStream(filter: filter, configuration: config, delegate: nil)
      try stream.addStreamOutput(streamOutput, type: .screen, sampleHandlerQueue: queue)
    } catch {
      return nil
    }
    do {
      try await stream.startCapture()
    } catch {
      return nil
    }
    try? await Task.sleep(nanoseconds: UInt64(durationSec) * 1_000_000_000)
    try? await stream.stopCapture()
    await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
      queue.async {
        streamOutput.finish {
          cont.resume()
        }
      }
    }
    while writer.status == .writing || writer.status == .unknown {
      try? await Task.sleep(nanoseconds: 50_000_000)
    }
    guard writer.status == .completed else { return nil }
    return outURL.path
  }
}

/// Used only on a single DispatchQueue; safe to mark Sendable for closure capture.
private final class StreamOutput: NSObject, SCStreamOutput, @unchecked Sendable {
  let videoInput: AVAssetWriterInput
  let writer: AVAssetWriter
  let queue: DispatchQueue
  private var firstSampleTime = CMTime.zero
  private var lastSampleBuffer: CMSampleBuffer?
  private var started = false

  init(videoInput: AVAssetWriterInput, writer: AVAssetWriter, queue: DispatchQueue) {
    self.videoInput = videoInput
    self.writer = writer
    self.queue = queue
  }

  func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
    guard type == .screen else { return }
    if !started {
      started = true
      firstSampleTime = sampleBuffer.presentationTimeStamp
      writer.startWriting()
      writer.startSession(atSourceTime: firstSampleTime)
    }
    lastSampleBuffer = sampleBuffer
    if videoInput.isReadyForMoreMediaData {
      videoInput.append(sampleBuffer)
    }
  }

  func finish(completion: @escaping () -> Void) {
    let endTime = lastSampleBuffer?.presentationTimeStamp ?? firstSampleTime
    writer.endSession(atSourceTime: endTime)
    videoInput.markAsFinished()
    writer.finishWriting {
      completion()
    }
  }
}
