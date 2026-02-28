// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for German (`de`).
class AppLocalizationsDe extends AppLocalizations {
  AppLocalizationsDe([String locale = 'de']) : super(locale);

  @override
  String get appTitle => 'HomeClaw Companion';

  @override
  String get homeClaw => 'HomeClaw';

  @override
  String get refreshFriends => 'Freunde aktualisieren';

  @override
  String get logOut => 'Abmelden';

  @override
  String get retry => 'Erneut versuchen';

  @override
  String get noFriends => 'Keine Freunde. Füge Freunde in Core (config/user.yml) hinzu.';

  @override
  String get somethingWentWrong => 'Etwas ist schiefgelaufen';

  @override
  String get permissions => 'Berechtigungen';

  @override
  String get permissionsIntro => 'HomeClaw benötigt einige Berechtigungen. Du kannst sie jetzt erteilen oder beim ersten Nutzen der jeweiligen Funktion.';

  @override
  String get continue => 'Weiter';

  @override
  String get allow => 'Erlauben';

  @override
  String get openSettings => 'Einstellungen öffnen';

  @override
  String get done => 'Fertig';

  @override
  String get login => 'Anmelden';

  @override
  String get user => 'Benutzer';

  @override
  String get password => 'Passwort';

  @override
  String get coreUrl => 'Core-URL';

  @override
  String get apiKeyOptional => 'API-Schlüssel (optional; leer lassen, wenn Core-Authentifizierung deaktiviert ist)';

  @override
  String get refreshConnection => 'Verbindung aktualisieren';

  @override
  String get pleaseSelectUser => 'Bitte Benutzer auswählen';

  @override
  String get pleaseEnterPassword => 'Bitte Passwort eingeben';

  @override
  String get noUsersInCore => 'Keine Benutzer in Core. Füge einen Benutzer in config/user.yml hinzu und tippe unten auf «Verbindung aktualisieren».';

  @override
  String get reminder => 'Erinnerung';

  @override
  String get deleteMessage => 'Nachricht löschen?';

  @override
  String get deleteMessageExplanation => 'Diese Nachricht wird aus dem Chat entfernt. Betrifft nur dieses Gerät; die Core-Sitzung bleibt unverändert.';

  @override
  String get cancel => 'Abbrechen';

  @override
  String get delete => 'Löschen';

  @override
  String get scanToConnect => 'Scannen zum Verbinden';

  @override
  String get manageCore => 'Core verwalten';

  @override
  String get save => 'Speichern';

  @override
  String get takePhoto => 'Foto aufnehmen';

  @override
  String get takePhotoContent => 'Neues Foto mit der Kamera aufnehmen oder vorhandenes Bild vom Gerät wählen.';

  @override
  String get useCamera => 'Kamera verwenden';

  @override
  String get stillWorking => 'Wird bearbeitet…';

  @override
  String get thinking => 'Denke nach…';

  @override
  String get almostThere => 'Fast fertig…';
}
