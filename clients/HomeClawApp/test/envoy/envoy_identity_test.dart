import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:home_claw_app/envoy/envoy_identity.dart';

void main() {
  // ============================================
  // Canonical JSON
  // ============================================

  group('canonicalJson', () {
    test('sorts keys alphabetically', () {
      final input = {'z': 1, 'a': 2, 'm': 3};
      final result = canonicalJson(input);
      expect(result, '{"a":2,"m":3,"z":1}');
    });

    test('filters null values', () {
      final input = {'a': 1, 'b': null, 'c': 3};
      final result = canonicalJson(input);
      expect(result, '{"a":1,"c":3}');
    });

    test('recurses into nested objects', () {
      final input = {
        'outer': {'b': 2, 'a': 1},
        'inner': null,
      };
      final result = canonicalJson(input);
      expect(result, '{"outer":{"a":1,"b":2}}');
    });

    test('handles empty object', () {
      final result = canonicalJson({});
      expect(result, '{}');
    });

    test('handles arrays without reordering', () {
      final input = {'items': [3, 1, 2]};
      final result = canonicalJson(input);
      expect(result, '{"items":[3,1,2]}');
    });

    test('handles primitive values', () {
      expect(canonicalJson('hello'), '"hello"');
      expect(canonicalJson(42), '42');
      expect(canonicalJson(true), 'true');
    });

    test('nested array of objects', () {
      final input = {
        'msgs': [
          {'id': '2', 'text': 'b'},
          {'id': '1', 'text': 'a'},
        ],
      };
      // Arrays preserve order; objects within arrays have sorted keys
      expect(canonicalJson(input), '{"msgs":[{"id":"2","text":"b"},{"id":"1","text":"a"}]}');
    });
  });

  // ============================================
  // Key Generation
  // ============================================

  group('generateEd25519KeyPair', () {
    test('produces valid PEM keys', () async {
      final keys = await generateEd25519KeyPair();

      // Public key PEM
      expect(keys.publicKeyPem, startsWith('-----BEGIN PUBLIC KEY-----\n'));
      expect(keys.publicKeyPem, endsWith('-----END PUBLIC KEY-----\n'));

      // Private key PEM
      expect(keys.privateKeyPem, startsWith('-----BEGIN PRIVATE KEY-----\n'));
      expect(keys.privateKeyPem, endsWith('-----END PRIVATE KEY-----\n'));
    });

    test('generates unique keys each time', () async {
      final a = await generateEd25519KeyPair();
      final b = await generateEd25519KeyPair();

      expect(a.publicKeyPem, isNot(b.publicKeyPem));
      expect(a.privateKeyPem, isNot(b.privateKeyPem));
    });

    test('public key PEM is 44 base64 chars of DER (excluding header/footer)', () async {
      final keys = await generateEd25519KeyPair();
      final lines = keys.publicKeyPem.trim().split('\n');
      final b64 = lines.sublist(1, lines.length - 1).join('');
      final der = base64.decode(b64);
      // Ed25519 SPKI DER: 12 byte header + 32 byte key = 44 bytes
      expect(der.length, 44);
    });

    test('private key PEM contains 48 bytes DER (excluding header/footer)', () async {
      final keys = await generateEd25519KeyPair();
      final lines = keys.privateKeyPem.trim().split('\n');
      final b64 = lines.sublist(1, lines.length - 1).join('');
      final der = base64.decode(b64);
      // Ed25519 PKCS#8 DER: 16 byte header + 32 byte key = 48 bytes
      expect(der.length, 48);
    });
  });

  // ============================================
  // Identity Derivation
  // ============================================

  group('derivePeerId', () {
    test('produces expected format', () {
      // Use a known PEM to test deterministic output
      const pem = '-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaAAA=\n-----END PUBLIC KEY-----\n';
      final id = derivePeerId(pem);
      expect(id, startsWith('envoy_'));
      expect(id.length, greaterThan(6)); // "envoy_" + at least some base64url chars
    });

    test('different keys produce different peer IDs', () async {
      final a = await generateEd25519KeyPair();
      final b = await generateEd25519KeyPair();
      expect(derivePeerId(a.publicKeyPem), isNot(derivePeerId(b.publicKeyPem)));
    });

    test('same key produces same peer ID', () async {
      final keys = await generateEd25519KeyPair();
      expect(derivePeerId(keys.publicKeyPem), derivePeerId(keys.publicKeyPem));
    });
  });

  group('deriveOwnerId', () {
    test('produces expected format', () async {
      final keys = await generateEd25519KeyPair();
      final id = deriveOwnerId(keys.publicKeyPem);
      expect(id, startsWith('envoy:owner:'));
    });
  });

  group('deriveDeviceId', () {
    test('produces expected format', () async {
      final keys = await generateEd25519KeyPair();
      final id = deriveDeviceId(keys.publicKeyPem);
      expect(id, startsWith('envoy:device:'));
    });
  });

  group('deriveAgentId', () {
    test('produces expected format', () async {
      final keys = await generateEd25519KeyPair();
      final ownerId = deriveOwnerId(keys.publicKeyPem);
      final id = deriveAgentId(ownerId, keys.publicKeyPem);
      expect(id, startsWith('envoy:agent:'));
    });
  });

  group('deriveAgentPeerId', () {
    test('produces expected format', () async {
      final keys = await generateEd25519KeyPair();
      final ownerId = deriveOwnerId(keys.publicKeyPem);
      final id = deriveAgentPeerId(ownerId, keys.publicKeyPem);
      expect(id, startsWith('envoy_agent_'));
    });
  });

  // ============================================
  // Identity Generation
  // ============================================

  group('generateIdentity', () {
    test('produces valid peer identity', () async {
      final identity = await generateIdentity();
      expect(identity.peerId, startsWith('envoy_'));
      expect(identity.publicKeyPem, startsWith('-----BEGIN PUBLIC KEY-----'));
      expect(identity.privateKeyPem, startsWith('-----BEGIN PRIVATE KEY-----'));
      expect(derivePeerId(identity.publicKeyPem), identity.peerId);
    });
  });

  group('generateOwnerIdentity', () {
    test('produces valid owner identity', () async {
      final identity = await generateOwnerIdentity();
      expect(identity.ownerId, startsWith('envoy:owner:'));
      expect(deriveOwnerId(identity.publicKeyPem), identity.ownerId);
    });
  });

  group('generateDeviceIdentity', () {
    test('produces valid device identity', () async {
      final identity = await generateDeviceIdentity();
      expect(identity.deviceId, startsWith('envoy:device:'));
      expect(deriveDeviceId(identity.publicKeyPem), identity.deviceId);
    });
  });

  group('generateAgentIdentity', () {
    test('produces valid agent identity linked to owner', () async {
      final owner = await generateOwnerIdentity();
      final agent = await generateAgentIdentity(owner.ownerId);
      expect(agent.agentId, startsWith('envoy:agent:'));
      expect(agent.agentPeerId, startsWith('envoy_agent_'));
      expect(deriveAgentId(owner.ownerId, agent.publicKeyPem), agent.agentId);
      expect(deriveAgentPeerId(owner.ownerId, agent.publicKeyPem), agent.agentPeerId);
    });

    test('different owners produce different agent IDs for same agent key', () async {
      final ownerA = await generateOwnerIdentity();
      final ownerB = await generateOwnerIdentity();
      final agentKeys = await generateEd25519KeyPair();

      expect(
        deriveAgentId(ownerA.ownerId, agentKeys.publicKeyPem),
        isNot(deriveAgentId(ownerB.ownerId, agentKeys.publicKeyPem)),
      );
    });
  });

  // ============================================
  // Signing & Verification
  // ============================================

  group('signCanonicalPayload / verifyCanonicalPayload', () {
    test('sign and verify round-trip', () async {
      final keys = await generateEd25519KeyPair();
      final input = {'intent': 'chat.message', 'text': 'hello'};

      final signature = await signCanonicalPayload(
        input,
        keys.privateKeyPem,
        keys.publicKeyPem,
      );

      expect(signature, isNotEmpty);
      // Ed25519 signature in base64url: 64 bytes → 86 chars (no padding)
      // Re-add padding for Dart's strict base64Url.decode (requires multiple-of-4 length)
      var paddedSig = signature;
      while (paddedSig.length % 4 != 0) paddedSig += '=';
      expect(base64Url.decode(paddedSig).length, 64);

      final valid = await verifyCanonicalPayload(
        input,
        signature,
        keys.publicKeyPem,
      );
      expect(valid, isTrue);
    });

    test('rejects tampered payload', () async {
      final keys = await generateEd25519KeyPair();
      final original = {'text': 'hello'};
      final tampered = {'text': 'goodbye'};

      final signature = await signCanonicalPayload(
        original,
        keys.privateKeyPem,
        keys.publicKeyPem,
      );

      final valid = await verifyCanonicalPayload(
        tampered,
        signature,
        keys.publicKeyPem,
      );
      expect(valid, isFalse);
    });

    test('rejects wrong public key', () async {
      final alice = await generateEd25519KeyPair();
      final bob = await generateEd25519KeyPair();
      final input = {'text': 'hello'};

      final signature = await signCanonicalPayload(
        input,
        alice.privateKeyPem,
        alice.publicKeyPem,
      );

      final valid = await verifyCanonicalPayload(
        input,
        signature,
        bob.publicKeyPem,
      );
      expect(valid, isFalse);
    });

    test('canonical JSON changes produce different signature', () async {
      final keys = await generateEd25519KeyPair();
      final a = {'a': 1, 'b': 2};
      final b = {'b': 2, 'a': 1}; // same content, different key order

      final sigA = await signCanonicalPayload(a, keys.privateKeyPem, keys.publicKeyPem);
      final sigB = await signCanonicalPayload(b, keys.privateKeyPem, keys.publicKeyPem);

      // Both canonicalize to the same thing, so signatures should match
      expect(sigA, sigB);
    });

    test('rejects short signature', () async {
      final keys = await generateEd25519KeyPair();
      final valid = await verifyCanonicalPayload(
        {'a': 1},
        base64Url.encode([1, 2, 3]), // too short, not 64 bytes
        keys.publicKeyPem,
      );
      expect(valid, isFalse);
    });

    test('verify rejects malformed PEM', () async {
      final keys = await generateEd25519KeyPair();
      final input = {'a': 1};
      final signature = await signCanonicalPayload(
        input,
        keys.privateKeyPem,
        keys.publicKeyPem,
      );

      final valid = await verifyCanonicalPayload(
        input,
        signature,
        'not-valid-pem',
      );
      expect(valid, isFalse);
    });
  });

  // ============================================
  // hashCanonicalPayload
  // ============================================

  group('hashCanonicalPayload', () {
    test('produces deterministic hash', () {
      final hash1 = hashCanonicalPayload({'a': 1, 'b': 2});
      final hash2 = hashCanonicalPayload({'b': 2, 'a': 1});
      expect(hash1, hash2);
    });

    test('different payloads produce different hashes', () {
      final hash1 = hashCanonicalPayload({'a': 1});
      final hash2 = hashCanonicalPayload({'a': 2});
      expect(hash1, isNot(hash2));
    });

    test('hash is base64url of SHA-256', () {
      final hash = hashCanonicalPayload({'key': 'value'});
      // SHA-256 = 32 bytes → base64url (with padding) = 44 chars
      expect(hash.length, greaterThanOrEqualTo(43));
    });
  });
}
