// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Spanish Castilian (`es`).
class AppLocalizationsEs extends AppLocalizations {
  AppLocalizationsEs([String locale = 'es']) : super(locale);

  @override
  String get appTitle => 'HomeClaw Companion';

  @override
  String get homeClaw => 'HomeClaw';

  @override
  String get refreshFriends => 'Actualizar amigos';

  @override
  String get logOut => 'Cerrar sesión';

  @override
  String get retry => 'Reintentar';

  @override
  String get noFriends => 'No hay amigos. Añade amigos en Core (config/user.yml).';

  @override
  String get somethingWentWrong => 'Algo salió mal';

  @override
  String get permissions => 'Permisos';

  @override
  String get permissionsIntro => 'HomeClaw necesita algunos permisos para funcionar. Puedes concederlos ahora o la primera vez que uses cada función.';

  @override
  String get continue => 'Continuar';

  @override
  String get allow => 'Permitir';

  @override
  String get openSettings => 'Abrir ajustes';

  @override
  String get done => 'Listo';

  @override
  String get login => 'Iniciar sesión';

  @override
  String get user => 'Usuario';

  @override
  String get password => 'Contraseña';

  @override
  String get coreUrl => 'URL de Core';

  @override
  String get apiKeyOptional => 'Clave API (opcional; déjalo vacío si la autenticación de Core está desactivada)';

  @override
  String get refreshConnection => 'Actualizar la conexión';

  @override
  String get pleaseSelectUser => 'Selecciona un usuario';

  @override
  String get pleaseEnterPassword => 'Introduce la contraseña';

  @override
  String get noUsersInCore => 'No hay usuarios en Core. Añade un usuario en config/user.yml y pulsa «Actualizar la conexión» abajo.';

  @override
  String get reminder => 'Recordatorio';

  @override
  String get deleteMessage => '¿Eliminar mensaje?';

  @override
  String get deleteMessageExplanation => 'Este mensaje se quitará del chat. Solo afecta a este dispositivo; no cambia la sesión en Core.';

  @override
  String get cancel => 'Cancelar';

  @override
  String get delete => 'Eliminar';

  @override
  String get scanToConnect => 'Escanear para conectar';

  @override
  String get manageCore => 'Gestionar Core';

  @override
  String get save => 'Guardar';

  @override
  String get takePhoto => 'Tomar foto';

  @override
  String get takePhotoContent => 'Usa la cámara para una nueva foto o elige una imagen existente de tu dispositivo.';

  @override
  String get useCamera => 'Usar cámara';

  @override
  String get stillWorking => 'Trabajando…';

  @override
  String get thinking => 'Pensando…';

  @override
  String get almostThere => 'Casi listo…';
}
