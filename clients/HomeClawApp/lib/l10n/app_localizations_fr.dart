// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for French (`fr`).
class AppLocalizationsFr extends AppLocalizations {
  AppLocalizationsFr([String locale = 'fr']) : super(locale);

  @override
  String get appTitle => 'HomeClaw Companion';

  @override
  String get homeClaw => 'HomeClaw';

  @override
  String get refreshFriends => 'Actualiser les amis';

  @override
  String get logOut => 'Déconnexion';

  @override
  String get retry => 'Réessayer';

  @override
  String get noFriends =>
      'Aucun ami. Ajoutez des amis dans Core (config/user.yml).';

  @override
  String get somethingWentWrong => 'Une erreur s\'est produite';

  @override
  String get permissions => 'Autorisations';

  @override
  String get permissionsIntro =>
      'HomeClaw a besoin de quelques autorisations. Vous pouvez les accorder maintenant ou à la première utilisation de chaque fonction.';

  @override
  String get continueButton => 'Continuer';

  @override
  String get allow => 'Autoriser';

  @override
  String get openSettings => 'Ouvrir les réglages';

  @override
  String get done => 'Terminé';

  @override
  String get login => 'Connexion';

  @override
  String get user => 'Utilisateur';

  @override
  String get password => 'Mot de passe';

  @override
  String get coreUrl => 'URL Core';

  @override
  String get apiKeyOptional =>
      'Clé API (optionnelle ; laisser vide si l\'authentification Core est désactivée)';

  @override
  String get refreshConnection => 'Actualiser la connexion';

  @override
  String get pleaseSelectUser => 'Veuillez sélectionner un utilisateur';

  @override
  String get pleaseEnterPassword => 'Veuillez entrer le mot de passe';

  @override
  String get noUsersInCore =>
      'Aucun utilisateur dans Core. Ajoutez un utilisateur dans config/user.yml, puis appuyez sur « Actualiser la connexion » ci-dessous.';

  @override
  String get reminder => 'Rappel';

  @override
  String get deleteMessage => 'Supprimer le message ?';

  @override
  String get deleteMessageExplanation =>
      'Ce message sera retiré du chat. Cela n\'affecte que cet appareil ; la session Core ne change pas.';

  @override
  String get cancel => 'Annuler';

  @override
  String get delete => 'Supprimer';

  @override
  String get scanToConnect => 'Scanner pour connecter';

  @override
  String get manageCore => 'Gérer Core';

  @override
  String get save => 'Enregistrer';

  @override
  String get takePhoto => 'Prendre une photo';

  @override
  String get takePhotoContent =>
      'Prendre une nouvelle photo avec l\'appareil photo ou choisir une image existante sur l\'appareil.';

  @override
  String get useCamera => 'Utiliser l\'appareil photo';

  @override
  String get stillWorking => 'Traitement en cours…';

  @override
  String get thinking => 'Réflexion…';

  @override
  String get almostThere => 'Presque terminé…';
}
