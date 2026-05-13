import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/envoy/envoy_identity.dart';
import 'package:home_claw_app/envoy/envoy_protocol.dart';

/// Same vectors as [packages/identity/test/fixtures/companion_envelope_interop_golden.json]
/// in the EnvoyMesh repo (canonical sign + verify interop).
void main() {
  test('golden unsigned envelope signs to exact base64url signature', () async {
    final dir = Directory.current.path;
    final f = File('$dir/test/fixtures/companion_envelope_interop_golden.json');
    expect(f.existsSync(), isTrue,
        reason: 'Run from HomeClawApp package root (test/fixtures)');
    final map = jsonDecode(await f.readAsString()) as Map<String, dynamic>;
    final priv = map['privateKeyPem'] as String;
    final pub = map['publicKeyPem'] as String;
    final unsigned = map['unsignedEnvelopeJson'] as Map<String, dynamic>;
    final expectedSig = map['signatureBase64Url'] as String;

    final sig = await signCanonicalPayload(unsigned, priv, pub);
    expect(sig, expectedSig);
  });

  test('golden signed envelope verifies with verifyCanonicalPayload', () async {
    final dir = Directory.current.path;
    final f = File('$dir/test/fixtures/companion_envelope_interop_golden.json');
    final map = jsonDecode(await f.readAsString()) as Map<String, dynamic>;
    final pub = map['publicKeyPem'] as String;
    final signedJson =
        map['signedEnvelopeJson'] as Map<String, dynamic>;

    final env = parseEnvelope(signedJson);
    expect(env.senderPeerId, map['peerId']);

    final ok = await verifyCanonicalPayload(
      envelopeForSigning(env),
      env.signature,
      pub,
    );
    expect(ok, isTrue);
  });
}
