import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/envoy/envoy_identity.dart';

/// Same vectors as [packages/identity/test/fixtures/companion_identity_golden.json]
/// in the EnvoyMesh repo (public key + expected peer/owner ids).
void main() {
  test('golden PEM matches TypeScript derivePeerId / deriveOwnerId', () async {
    final dir = Directory.current.path;
    final f =
        File('$dir/test/fixtures/companion_identity_golden.json');
    expect(f.existsSync(), isTrue,
        reason: 'Run from HomeClawApp package root (test/fixtures)');
    final map = jsonDecode(await f.readAsString()) as Map<String, dynamic>;
    final pem = map['publicKeyPem'] as String;
    expect(derivePeerId(pem), map['peerId']);
    expect(deriveOwnerId(pem), map['ownerId']);
  });
}
