import Cocoa
import FlutterMacOS
import UserNotifications
import homeclaw_native

@main
class AppDelegate: FlutterAppDelegate, UNUserNotificationCenterDelegate {
  override func applicationDidFinishLaunching(_ notification: Notification) {
    UNUserNotificationCenter.current().delegate = self
    super.applicationDidFinishLaunching(notification)
  }

  override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
    return true
  }

  override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
    return true
  }

  override func application(
    _ application: NSApplication,
    didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
  ) {
    HomeclawNativePlugin.receiveApnsToken(deviceToken)
  }

  func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    didReceive response: UNNotificationResponse,
    withCompletionHandler completionHandler: @escaping () -> Void
  ) {
    let userInfo = response.notification.request.content.userInfo
    let ud = UserDefaults.standard
    if let t = userInfo["text"] as? String, !t.isEmpty {
      ud.set(t, forKey: "homeclaw_pending_push_text")
      if let u = userInfo["user_id"] as? String, !u.isEmpty { ud.set(u, forKey: "homeclaw_pending_push_user_id") }
      else { ud.removeObject(forKey: "homeclaw_pending_push_user_id") }
      if let f = userInfo["from_friend"] as? String, !f.isEmpty { ud.set(f, forKey: "homeclaw_pending_push_from_friend") }
      else { ud.set("HomeClaw", forKey: "homeclaw_pending_push_from_friend") }
    }
    if let link = userInfo["link"] as? String, !link.isEmpty, let url = URL(string: link) {
      NSWorkspace.shared.open(url)
    }
    completionHandler()
  }
}
