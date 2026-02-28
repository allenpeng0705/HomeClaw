// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Japanese (`ja`).
class AppLocalizationsJa extends AppLocalizations {
  AppLocalizationsJa([String locale = 'ja']) : super(locale);

  @override
  String get appTitle => 'HomeClaw Companion';

  @override
  String get homeClaw => 'HomeClaw';

  @override
  String get refreshFriends => '友達を更新';

  @override
  String get logOut => 'ログアウト';

  @override
  String get retry => '再試行';

  @override
  String get noFriends => '友達がいません。Core の config/user.yml で友達を追加してください。';

  @override
  String get somethingWentWrong => '問題が発生しました';

  @override
  String get permissions => '権限';

  @override
  String get permissionsIntro => 'HomeClaw はいくつかの権限が必要です。今許可するか、各機能を初めて使うときに許可できます。';

  @override
  String get continue => '続ける';

  @override
  String get allow => '許可';

  @override
  String get openSettings => '設定を開く';

  @override
  String get done => '完了';

  @override
  String get login => 'ログイン';

  @override
  String get user => 'ユーザー';

  @override
  String get password => 'パスワード';

  @override
  String get coreUrl => 'Core URL';

  @override
  String get apiKeyOptional => 'APIキー（任意；Core認証が無効の場合は空欄）';

  @override
  String get refreshConnection => '接続を更新';

  @override
  String get pleaseSelectUser => 'ユーザーを選択してください';

  @override
  String get pleaseEnterPassword => 'パスワードを入力してください';

  @override
  String get noUsersInCore => 'Core にユーザーがいません。config/user.yml でユーザーを追加し、下の「接続を更新」をタップしてください。';

  @override
  String get reminder => 'リマインダー';

  @override
  String get deleteMessage => 'メッセージを削除しますか？';

  @override
  String get deleteMessageExplanation => 'このメッセージはチャットから削除されます。この端末のみに影響し、Core のセッションは変わりません。';

  @override
  String get cancel => 'キャンセル';

  @override
  String get delete => '削除';

  @override
  String get scanToConnect => 'スキャンして接続';

  @override
  String get manageCore => 'Core を管理';

  @override
  String get save => '保存';

  @override
  String get takePhoto => '写真を撮る';

  @override
  String get takePhotoContent => 'カメラで新しい写真を撮るか、デバイスから既存の画像を選びます。';

  @override
  String get useCamera => 'カメラを使う';

  @override
  String get stillWorking => '処理中…';

  @override
  String get thinking => '考え中…';

  @override
  String get almostThere => 'もう少し…';
}
