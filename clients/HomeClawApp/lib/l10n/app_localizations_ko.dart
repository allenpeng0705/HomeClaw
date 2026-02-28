// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Korean (`ko`).
class AppLocalizationsKo extends AppLocalizations {
  AppLocalizationsKo([String locale = 'ko']) : super(locale);

  @override
  String get appTitle => 'HomeClaw Companion';

  @override
  String get homeClaw => 'HomeClaw';

  @override
  String get refreshFriends => '친구 새로 고침';

  @override
  String get logOut => '로그아웃';

  @override
  String get retry => '다시 시도';

  @override
  String get noFriends => '친구가 없습니다. Core의 config/user.yml에서 친구를 추가하세요.';

  @override
  String get somethingWentWrong => '문제가 발생했습니다';

  @override
  String get permissions => '권한';

  @override
  String get permissionsIntro => 'HomeClaw가 작동하려면 일부 권한이 필요합니다. 지금 허용하거나 각 기능을 처음 사용할 때 허용할 수 있습니다.';

  @override
  String get continue => '계속';

  @override
  String get allow => '허용';

  @override
  String get openSettings => '설정 열기';

  @override
  String get done => '완료';

  @override
  String get login => '로그인';

  @override
  String get user => '사용자';

  @override
  String get password => '비밀번호';

  @override
  String get coreUrl => 'Core URL';

  @override
  String get apiKeyOptional => 'API 키(선택 사항; Core 인증이 꺼져 있으면 비워 두세요)';

  @override
  String get refreshConnection => '연결 새로 고침';

  @override
  String get pleaseSelectUser => '사용자를 선택하세요';

  @override
  String get pleaseEnterPassword => '비밀번호를 입력하세요';

  @override
  String get noUsersInCore => 'Core에 사용자가 없습니다. config/user.yml에 사용자를 추가한 뒤 아래 \'연결 새로 고침\'을 탭하세요.';

  @override
  String get reminder => '리마인더';

  @override
  String get deleteMessage => '메시지를 삭제할까요?';

  @override
  String get deleteMessageExplanation => '이 메시지는 채팅에서 제거됩니다. 이 기기에만 적용되며 Core 세션은 변경되지 않습니다.';

  @override
  String get cancel => '취소';

  @override
  String get delete => '삭제';

  @override
  String get scanToConnect => '스캔하여 연결';

  @override
  String get manageCore => 'Core 관리';

  @override
  String get save => '저장';

  @override
  String get takePhoto => '사진 촬영';

  @override
  String get takePhotoContent => '카메라로 새 사진을 찍거나 기기에서 기존 이미지를 선택하세요.';

  @override
  String get useCamera => '카메라 사용';

  @override
  String get stillWorking => '처리 중…';

  @override
  String get thinking => '생각 중…';

  @override
  String get almostThere => '거의 완료…';
}
