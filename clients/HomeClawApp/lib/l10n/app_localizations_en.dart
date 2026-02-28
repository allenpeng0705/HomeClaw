// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'HomeClaw Companion';

  @override
  String get homeClaw => 'HomeClaw';

  @override
  String get refreshFriends => 'Refresh friends';

  @override
  String get logOut => 'Log out';

  @override
  String get retry => 'Retry';

  @override
  String get noFriends => 'No friends. Add friends in Core (config/user.yml).';

  @override
  String get somethingWentWrong => 'Something went wrong';

  @override
  String get permissions => 'Permissions';

  @override
  String get permissionsIntro => 'HomeClaw needs a few permissions to work. You can allow them now or when you first use each feature.';

  @override
  String get continue => 'Continue';

  @override
  String get allow => 'Allow';

  @override
  String get openSettings => 'Open Settings';

  @override
  String get done => 'Done';

  @override
  String get login => 'Login';

  @override
  String get user => 'User';

  @override
  String get password => 'Password';

  @override
  String get coreUrl => 'Core URL';

  @override
  String get apiKeyOptional => 'API key (optional; leave empty if Core auth is disabled)';

  @override
  String get refreshConnection => 'Refresh the connection';

  @override
  String get pleaseSelectUser => 'Please select a user';

  @override
  String get pleaseEnterPassword => 'Please enter password';

  @override
  String get noUsersInCore => 'No users with username in Core. Add username in config/user.yml, then tap Refresh the connection below.';

  @override
  String get reminder => 'Reminder';

  @override
  String get deleteMessage => 'Delete message?';

  @override
  String get deleteMessageExplanation => 'This message will be removed from the chat. This only affects this device; it does not change Core\'s session.';

  @override
  String get cancel => 'Cancel';

  @override
  String get delete => 'Delete';

  @override
  String get scanToConnect => 'Scan to connect';

  @override
  String get manageCore => 'Manage Core';

  @override
  String get save => 'Save';

  @override
  String get takePhoto => 'Take photo';

  @override
  String get takePhotoContent => 'Use camera to take a new photo, or choose an existing image from your device.';

  @override
  String get useCamera => 'Use camera';

  @override
  String get stillWorking => 'Still working…';

  @override
  String get thinking => 'Thinking…';

  @override
  String get almostThere => 'Almost there…';
}
