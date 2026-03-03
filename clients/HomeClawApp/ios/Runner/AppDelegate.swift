import Flutter
import UIKit
import UserNotifications
import homeclaw_native

@main
@objc class AppDelegate: FlutterAppDelegate, UNUserNotificationCenterDelegate {
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
  func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    didReceive response: UNNotificationResponse,
    withCompletionHandler completionHandler: @escaping () -> Void
  ) {
    let userInfo = response.notification.request.content.userInfo
    if let link = userInfo["link"] as? String, !link.isEmpty, let url = URL(string: link) {
      UIApplication.shared.open(url)
    }
    completionHandler()
  }
}
