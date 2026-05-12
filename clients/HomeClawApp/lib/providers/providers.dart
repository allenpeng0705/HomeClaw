import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core_service.dart';

// Re-export EnvoyMesh providers so consumers can import from a single location.
export 'envoy_providers.dart';

/// Provider for the singleton CoreService instance.
/// The CoreService is created in main() before runApp() and passed via this provider
/// so screens can access it without prop drilling.
final coreServiceProvider = Provider<CoreService>((ref) {
  throw UnimplementedError(
    'coreServiceProvider must be overridden at app startup via '
    'ProviderScope.overrides or by providing the CoreService instance directly.',
  );
});
