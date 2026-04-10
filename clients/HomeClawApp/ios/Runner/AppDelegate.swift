import Flutter
import UIKit
import UserNotifications
import homeclaw_native

@main
@objc class AppDelegate: FlutterAppDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)
    UNUserNotificationCenter.current().delegate = self
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  override func application(
    _ application: UIApplication,
    didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
  ) {
    HomeclawNativePlugin.receiveApnsToken(deviceToken)
  }

  // When user taps a push notification, open the deep link so the app can navigate to the right chat.
  override func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    didReceive response: UNNotificationResponse,
    withCompletionHandler completionHandler: @escaping () -> Void
  ) {
    let userInfo = response.notification.request.content.userInfo
    // Stash payload so Flutter can persist the reply into chat history (WS is dead when app was killed).
    let ud = UserDefaults.standard
    if let t = userInfo["text"] as? String, !t.isEmpty {
      ud.set(t, forKey: "homeclaw_pending_push_text")
      if let u = userInfo["user_id"] as? String, !u.isEmpty { ud.set(u, forKey: "homeclaw_pending_push_user_id") }
      else { ud.removeObject(forKey: "homeclaw_pending_push_user_id") }
      if let f = userInfo["from_friend"] as? String, !f.isEmpty { ud.set(f, forKey: "homeclaw_pending_push_from_friend") }
      else { ud.set("HomeClaw", forKey: "homeclaw_pending_push_from_friend") }
    }
    if let link = userInfo["link"] as? String, !link.isEmpty, let url = URL(string: link) {
      UIApplication.shared.open(url)
    }
    completionHandler()
  }
}
