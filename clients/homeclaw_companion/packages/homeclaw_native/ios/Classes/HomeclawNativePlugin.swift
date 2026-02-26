import Flutter
import UIKit
import UserNotifications

public class HomeclawNativePlugin: NSObject, FlutterPlugin {
  private static var pendingApnsResult: FlutterResult?

  public static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(name: "homeclaw_native", binaryMessenger: registrar.messenger())
    let instance = HomeclawNativePlugin()
    registrar.addMethodCallDelegate(instance, channel: channel)
  }

  /// Call this from AppDelegate.didRegisterForRemoteNotificationsWithDeviceToken to pass the APNs token to Flutter.
  public static func receiveApnsToken(_ deviceToken: Data) {
    let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
    if let result = pendingApnsResult {
      DispatchQueue.main.async { result(token) }
      pendingApnsResult = nil
    }
  }

  public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "getPlatformVersion":
      result("iOS " + UIDevice.current.systemVersion)
    case "showNotification":
      guard let args = call.arguments as? [String: Any],
            let title = args["title"] as? String,
            let body = args["body"] as? String else {
        result(FlutterError(code: "INVALID_ARGS", message: "title and body required", details: nil))
        return
      }
      showNotification(title: title, body: body, result: result)
    case "getApnsToken":
      requestApnsToken(result: result)
    case "startScreenRecord":
      result(nil)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func requestApnsToken(result: @escaping FlutterResult) {
    let center = UNUserNotificationCenter.current()
    center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
      guard granted else {
        DispatchQueue.main.async { result(nil) }
        return
      }
      Self.pendingApnsResult = result
      DispatchQueue.main.async {
        UIApplication.shared.registerForRemoteNotifications()
      }
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
}
