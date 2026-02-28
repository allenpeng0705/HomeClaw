// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Italian (`it`).
class AppLocalizationsIt extends AppLocalizations {
  AppLocalizationsIt([String locale = 'it']) : super(locale);

  @override
  String get appTitle => 'HomeClaw Companion';

  @override
  String get homeClaw => 'HomeClaw';

  @override
  String get refreshFriends => 'Aggiorna amici';

  @override
  String get logOut => 'Esci';

  @override
  String get retry => 'Riprova';

  @override
  String get noFriends => 'Nessun amico. Aggiungi amici in Core (config/user.yml).';

  @override
  String get somethingWentWrong => 'Qualcosa è andato storto';

  @override
  String get permissions => 'Permessi';

  @override
  String get permissionsIntro => 'HomeClaw ha bisogno di alcuni permessi. Puoi concederli ora o la prima volta che usi ogni funzione.';

  @override
  String get continue => 'Continua';

  @override
  String get allow => 'Consenti';

  @override
  String get openSettings => 'Apri impostazioni';

  @override
  String get done => 'Fine';

  @override
  String get login => 'Accedi';

  @override
  String get user => 'Utente';

  @override
  String get password => 'Password';

  @override
  String get coreUrl => 'URL Core';

  @override
  String get apiKeyOptional => 'Chiave API (opzionale; lascia vuoto se l\'autenticazione Core è disattivata)';

  @override
  String get refreshConnection => 'Aggiorna connessione';

  @override
  String get pleaseSelectUser => 'Seleziona un utente';

  @override
  String get pleaseEnterPassword => 'Inserisci la password';

  @override
  String get noUsersInCore => 'Nessun utente in Core. Aggiungi un utente in config/user.yml e tocca «Aggiorna connessione» sotto.';

  @override
  String get reminder => 'Promemoria';

  @override
  String get deleteMessage => 'Eliminare messaggio?';

  @override
  String get deleteMessageExplanation => 'Questo messaggio sarà rimosso dalla chat. Riguarda solo questo dispositivo; non modifica la sessione Core.';

  @override
  String get cancel => 'Annulla';

  @override
  String get delete => 'Elimina';

  @override
  String get scanToConnect => 'Scansiona per connettere';

  @override
  String get manageCore => 'Gestisci Core';

  @override
  String get save => 'Salva';

  @override
  String get takePhoto => 'Scatta foto';

  @override
  String get takePhotoContent => 'Scatta una nuova foto con la fotocamera o scegli un\'immagine esistente dal dispositivo.';

  @override
  String get useCamera => 'Usa fotocamera';

  @override
  String get stillWorking => 'Elaborazione in corso…';

  @override
  String get thinking => 'Sto pensando…';

  @override
  String get almostThere => 'Quasi fatto…';
}
