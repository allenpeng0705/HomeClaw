// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Chinese (`zh`).
class AppLocalizationsZh extends AppLocalizations {
  AppLocalizationsZh([String locale = 'zh']) : super(locale);

  @override
  String get appTitle => 'HomeClaw 伴侣';

  @override
  String get homeClaw => 'HomeClaw';

  @override
  String get refreshFriends => '刷新好友';

  @override
  String get logOut => '退出登录';

  @override
  String get retry => '重试';

  @override
  String get noFriends => '暂无好友。请在 Core 的 config/user.yml 中添加好友。';

  @override
  String get somethingWentWrong => '出错了';

  @override
  String get permissions => '权限';

  @override
  String get permissionsIntro => 'HomeClaw 需要一些权限才能正常工作。您可以立即授权，或在首次使用相关功能时再授权。';

  @override
  String get continue => '继续';

  @override
  String get allow => '允许';

  @override
  String get openSettings => '打开设置';

  @override
  String get done => '完成';

  @override
  String get login => '登录';

  @override
  String get user => '用户';

  @override
  String get password => '密码';

  @override
  String get coreUrl => 'Core 地址';

  @override
  String get apiKeyOptional => 'API 密钥（可选；若 Core 未启用认证可留空）';

  @override
  String get refreshConnection => '刷新连接';

  @override
  String get pleaseSelectUser => '请选择用户';

  @override
  String get pleaseEnterPassword => '请输入密码';

  @override
  String get noUsersInCore => 'Core 中暂无对应用户。请在 config/user.yml 中添加用户名，然后点击下方「刷新连接」。';

  @override
  String get reminder => '提醒';

  @override
  String get deleteMessage => '删除消息？';

  @override
  String get deleteMessageExplanation => '此消息将从本机对话中移除，不会更改 Core 的会话记录。';

  @override
  String get cancel => '取消';

  @override
  String get delete => '删除';

  @override
  String get scanToConnect => '扫码连接';

  @override
  String get manageCore => '管理 Core';

  @override
  String get save => '保存';

  @override
  String get takePhoto => '拍照';

  @override
  String get takePhotoContent => '使用相机拍摄新照片，或从设备中选择已有图片。';

  @override
  String get useCamera => '使用相机';

  @override
  String get stillWorking => '正在处理…';

  @override
  String get thinking => '思考中…';

  @override
  String get almostThere => '快好了…';
}
