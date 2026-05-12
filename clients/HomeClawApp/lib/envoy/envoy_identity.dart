import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:crypto/crypto.dart' as crypto;

// ============================================
// PEM encoding for Ed25519 keys
// ============================================

/// DER-encoded SPKI (SubjectPublicKeyInfo) for an Ed25519 32-byte public key.
///
/// ASN.1 structure:
///   30 2A          SEQUENCE (42 bytes)
///     30 05        SEQUENCE (5 bytes)
///       06 03      OID (3 bytes)
///         2B 65 70 1.3.101.112 (Ed25519)
///     03 21        BIT STRING (33 bytes)
///       00         unused bits = 0
///       <32 bytes public key>
Uint8List _encodePublicKeySpki(Uint8List publicKeyBytes) {
  if (publicKeyBytes.length != 32) {
    throw ArgumentError('Ed25519 public key must be 32 bytes');
  }
  return Uint8List.fromList([
    0x30, 0x2A, // SEQUENCE, 42 bytes
    0x30, 0x05, 0x06, 0x03, 0x2B, 0x65, 0x70, // OID 1.3.101.112
    0x03, 0x21, 0x00, // BIT STRING, 33 bytes, 0 unused bits
    ...publicKeyBytes,
  ]);
}

/// DER-encoded PKCS#8 for an Ed25519 32-byte private key.
///
/// ASN.1 structure:
///   30 2E          SEQUENCE (46 bytes)
///     02 01 00     INTEGER 0 (version)
///     30 05        SEQUENCE (5 bytes)
///       06 03      OID (3 bytes)
///         2B 65 70 1.3.101.112 (Ed25519)
///     04 22        OCTET STRING (34 bytes)
///       04 20      OCTET STRING (32 bytes)
///         <32 bytes private key>
Uint8List _encodePrivateKeyPkcs8(Uint8List privateKeyBytes) {
  if (privateKeyBytes.length != 32) {
    throw ArgumentError('Ed25519 private key must be 32 bytes');
  }
  return Uint8List.fromList([
    0x30, 0x2E, // SEQUENCE, 46 bytes
    0x02, 0x01, 0x00, // INTEGER 0 (version)
    0x30, 0x05, 0x06, 0x03, 0x2B, 0x65, 0x70, // OID 1.3.101.112
    0x04, 0x22, // OCTET STRING, 34 bytes
    0x04, 0x20, // OCTET STRING, 32 bytes
    ...privateKeyBytes,
  ]);
}

/// Convert DER bytes to PEM format with the given label.
String _derToPem(Uint8List der, String label) {
  final b64 = base64.encode(der);
  final lines = <String>['-----BEGIN $label-----'];
  for (var i = 0; i < b64.length; i += 64) {
    lines.add(b64.substring(i, i + 64 > b64.length ? b64.length : i + 64));
  }
  lines.add('-----END $label-----');
  return lines.join('\n') + '\n';
}

/// Parse a PEM string to DER bytes. Returns null if the PEM is invalid.
Uint8List? _pemToDer(String pem) {
  final trimmed = pem.trim();
  final lines = trimmed.split('\n');
  if (lines.length < 2) return null;
  if (!lines.first.startsWith('-----BEGIN ') || !lines.last.startsWith('-----END ')) {
    return null;
  }
  final b64 = lines.sublist(1, lines.length - 1).join('');
  try {
    return Uint8List.fromList(base64.decode(b64));
  } catch (_) {
    return null;
  }
}

/// Extract the 32-byte raw key from an Ed25519 SPKI DER.
Uint8List? _parsePublicKeySpki(Uint8List der) {
  // Ed25519 SPKI: 30 2A 30 05 06 03 2B 65 70 03 21 00 <32 bytes>
  if (der.length < 44) return null;
  if (der[0] != 0x30 || der[1] != 0x2A) return null;
  if (der[2] != 0x30 || der[3] != 0x05) return null;
  if (der[4] != 0x06 || der[5] != 0x03) return null;
  if (der[6] != 0x2B || der[7] != 0x65 || der[8] != 0x70) return null; // OID Ed25519
  if (der[9] != 0x03 || der[10] != 0x21) return null; // BIT STRING 33 bytes
  if (der[11] != 0x00) return null; // unused bits = 0
  return Uint8List.sublistView(der, 12, 44);
}

/// Extract the 32-byte raw key from an Ed25519 PKCS#8 DER.
Uint8List? _parsePrivateKeyPkcs8(Uint8List der) {
  // Ed25519 PKCS#8: 30 2E 02 01 00 30 05 06 03 2B 65 70 04 22 04 20 <32 bytes>
  if (der.length < 48) return null;
  if (der[0] != 0x30 || der[1] != 0x2E) return null;
  if (der[2] != 0x02 || der[3] != 0x01 || der[4] != 0x00) return null;
  if (der[5] != 0x30 || der[6] != 0x05) return null;
  if (der[7] != 0x06 || der[8] != 0x03) return null;
  if (der[9] != 0x2B || der[10] != 0x65 || der[11] != 0x70) return null;
  if (der[12] != 0x04 || der[13] != 0x22) return null;
  if (der[14] != 0x04 || der[15] != 0x20) return null;
  return Uint8List.sublistView(der, 16, 48);
}

// ============================================
// Canonical JSON
// ============================================

/// Sorts keys, removes `undefined`-equivalent values (null for optional fields
/// that were excluded), and returns a value ready for `jsonEncode`.
///
/// Matches the TypeScript `sortForCanonicalJson` exactly:
/// - Object keys sorted lexicographically
/// - `null` values are kept (TypeScript `undefined` is dropped, but Dart uses
///   `null` for absent optional fields — we drop `null` in maps to match)
/// - Arrays and primitives pass through unchanged
dynamic _sortForCanonicalJson(dynamic input) {
  if (input is List) {
    return input.map(_sortForCanonicalJson).toList();
  }
  if (input is Map<String, dynamic>) {
    return Map.fromEntries(
      input.entries
          .where((e) => e.value != null)
          .toList()
        ..sort((a, b) => a.key.compareTo(b.key)),
    ).map((key, value) => MapEntry(key, _sortForCanonicalJson(value)));
  }
  return input;
}

/// Canonical JSON serialization: sorted keys, no null values.
/// Produces byte-identical output to the TypeScript `canonicalJson()`.
String canonicalJson(dynamic input) {
  final sorted = _sortForCanonicalJson(input);
  return jsonEncode(sorted);
}

// ============================================
// Key Generation
// ============================================

/// A PEM-encoded Ed25519 key pair.
class EnvoyKeyPair {
  final String publicKeyPem;
  final String privateKeyPem;

  const EnvoyKeyPair({
    required this.publicKeyPem,
    required this.privateKeyPem,
  });
}

/// Generates an Ed25519 key pair and returns PEM-encoded keys.
///
/// Public key: SPKI PEM format.
/// Private key: PKCS#8 PEM format.
///
/// Matches the TypeScript `generateEd25519KeyPair()`.
Future<EnvoyKeyPair> generateEd25519KeyPair() async {
  final algorithm = Ed25519();
  final keyPair = await algorithm.newKeyPair();
  final data = await keyPair.extract(); // SimpleKeyPairData

  final publicKeyBytes = data.publicKey.bytes;
  final privateKeyBytes = data.bytes;

  final publicKeyPem = _derToPem(
    _encodePublicKeySpki(Uint8List.fromList(publicKeyBytes)),
    'PUBLIC KEY',
  );

  final privateKeyPem = _derToPem(
    _encodePrivateKeyPkcs8(Uint8List.fromList(privateKeyBytes)),
    'PRIVATE KEY',
  );

  return EnvoyKeyPair(
    publicKeyPem: publicKeyPem,
    privateKeyPem: privateKeyPem,
  );
}

/// Base64url-encode without padding, matching Node.js `buffer.toString('base64url')`.
String _base64UrlNoPad(List<int> bytes) {
  final encoded = base64Url.encode(bytes);
  // Strip trailing '=' padding characters
  return encoded.replaceAll('=', '');
}

/// Decode a base64url string that may be missing padding (Node.js style).
Uint8List _base64UrlNoPadDecode(String encoded) {
  // Re-add padding if needed — Dart's base64Url.decode requires multiple-of-4 length
  var padded = encoded;
  while (padded.length % 4 != 0) {
    padded += '=';
  }
  return Uint8List.fromList(base64Url.decode(padded));
}

// ============================================
// Identity Derivation
// ============================================

/// Derives a peer ID from a PEM-encoded Ed25519 public key.
///
/// Format: `envoy_<base64url(sha256(publicKeyPem))>`
///
/// Matches the TypeScript `derivePeerId()`.
String derivePeerId(String publicKeyPem) {
  final hash = crypto.sha256.convert(utf8.encode(publicKeyPem));
  return 'envoy_${_base64UrlNoPad(hash.bytes)}';
}

/// Derives an owner ID from a PEM-encoded Ed25519 public key.
///
/// Format: `envoy:owner:<base64url(sha256(publicKeyPem))>`
///
/// Matches the TypeScript `deriveOwnerId()`.
String deriveOwnerId(String publicKeyPem) {
  final hash = crypto.sha256.convert(utf8.encode(publicKeyPem));
  return 'envoy:owner:${_base64UrlNoPad(hash.bytes)}';
}

/// Derives a device ID from a PEM-encoded Ed25519 public key.
///
/// Format: `envoy:device:<base64url(sha256(publicKeyPem))>`
///
/// Matches the TypeScript `deriveDeviceId()`.
String deriveDeviceId(String publicKeyPem) {
  final hash = crypto.sha256.convert(utf8.encode(publicKeyPem));
  return 'envoy:device:${_base64UrlNoPad(hash.bytes)}';
}

/// Derives an agent ID from the owner ID and agent public key.
///
/// Format: `envoy:agent:<base64url(sha256(ownerId + agentPublicKeyPem))>`
///
/// Matches the TypeScript `deriveAgentId()`.
String deriveAgentId(String ownerId, String agentPublicKeyPem) {
  final hash = crypto.sha256.convert(utf8.encode(ownerId + agentPublicKeyPem));
  return 'envoy:agent:${_base64UrlNoPad(hash.bytes)}';
}

/// Derives an agent peer ID (envelope-level identity) from owner ID and
/// agent public key.
///
/// Format: `envoy_agent_<base64url(sha256(ownerId + agentPublicKeyPem))>`
///
/// Matches the TypeScript `generateAgentIdentity()`.
String deriveAgentPeerId(String ownerId, String agentPublicKeyPem) {
  final hash = crypto.sha256.convert(utf8.encode(ownerId + agentPublicKeyPem));
  return 'envoy_agent_${_base64UrlNoPad(hash.bytes)}';
}

// ============================================
// Identity Types
// ============================================

/// A full EnvoyMesh peer identity: peerId + key pair.
class EnvoyIdentity {
  final String peerId;
  final String publicKeyPem;
  final String privateKeyPem;

  const EnvoyIdentity({
    required this.peerId,
    required this.publicKeyPem,
    required this.privateKeyPem,
  });
}

/// Owner identity: ownerId + key pair.
class OwnerIdentity {
  final String ownerId;
  final String publicKeyPem;
  final String privateKeyPem;

  const OwnerIdentity({
    required this.ownerId,
    required this.publicKeyPem,
    required this.privateKeyPem,
  });
}

/// Device identity: deviceId + key pair.
class DeviceIdentity {
  final String deviceId;
  final String publicKeyPem;
  final String privateKeyPem;

  const DeviceIdentity({
    required this.deviceId,
    required this.publicKeyPem,
    required this.privateKeyPem,
  });
}

/// Agent identity: agentId, agentPeerId + key pair.
class AgentIdentity {
  final String agentId;
  final String agentPeerId;
  final String publicKeyPem;
  final String privateKeyPem;

  const AgentIdentity({
    required this.agentId,
    required this.agentPeerId,
    required this.publicKeyPem,
    required this.privateKeyPem,
  });
}

// ============================================
// Identity Generation
// ============================================

/// Generates a full EnvoyMesh peer identity.
///
/// Matches the TypeScript `generateIdentity()`.
Future<EnvoyIdentity> generateIdentity() async {
  final keys = await generateEd25519KeyPair();
  return EnvoyIdentity(
    peerId: derivePeerId(keys.publicKeyPem),
    publicKeyPem: keys.publicKeyPem,
    privateKeyPem: keys.privateKeyPem,
  );
}

/// Generates an owner identity.
///
/// Matches the TypeScript `generateOwnerIdentity()`.
Future<OwnerIdentity> generateOwnerIdentity() async {
  final keys = await generateEd25519KeyPair();
  return OwnerIdentity(
    ownerId: deriveOwnerId(keys.publicKeyPem),
    publicKeyPem: keys.publicKeyPem,
    privateKeyPem: keys.privateKeyPem,
  );
}

/// Generates a device identity.
///
/// Matches the TypeScript `generateDeviceIdentity()`.
Future<DeviceIdentity> generateDeviceIdentity() async {
  final keys = await generateEd25519KeyPair();
  return DeviceIdentity(
    deviceId: deriveDeviceId(keys.publicKeyPem),
    publicKeyPem: keys.publicKeyPem,
    privateKeyPem: keys.privateKeyPem,
  );
}

/// Generates an agent identity (agent has its own peer ID derived from owner).
///
/// Matches the TypeScript `generateAgentIdentity()`.
Future<AgentIdentity> generateAgentIdentity(String ownerId) async {
  final keys = await generateEd25519KeyPair();
  return AgentIdentity(
    agentId: deriveAgentId(ownerId, keys.publicKeyPem),
    agentPeerId: deriveAgentPeerId(ownerId, keys.publicKeyPem),
    publicKeyPem: keys.publicKeyPem,
    privateKeyPem: keys.privateKeyPem,
  );
}

// ============================================
// Signing & Verification
// ============================================

final _ed25519 = Ed25519();

/// Signs a canonical JSON payload and returns the base64url-encoded signature.
///
/// Needs both the private key PEM (PKCS#8) and public key PEM (SPKI) because the
/// `cryptography` package requires both to construct a `SimpleKeyPairData`.
///
/// Matches the TypeScript `signCanonicalPayload()`.
Future<String> signCanonicalPayload(
  dynamic input,
  String privateKeyPem,
  String publicKeyPem,
) async {
  final payload = utf8.encode(canonicalJson(input));

  final privDer = _pemToDer(privateKeyPem);
  if (privDer == null) throw ArgumentError('Invalid PEM private key');
  final rawPrivKey = _parsePrivateKeyPkcs8(privDer);
  if (rawPrivKey == null) throw ArgumentError('Not an Ed25519 PKCS#8 private key');

  final pubDer = _pemToDer(publicKeyPem);
  if (pubDer == null) throw ArgumentError('Invalid PEM public key');
  final rawPubKey = _parsePublicKeySpki(pubDer);
  if (rawPubKey == null) throw ArgumentError('Not an Ed25519 SPKI public key');

  final keyPair = SimpleKeyPairData(
    rawPrivKey.toList(),
    publicKey: SimplePublicKey(rawPubKey.toList(), type: KeyPairType.ed25519),
    type: KeyPairType.ed25519,
  );

  final signature = await _ed25519.sign(payload, keyPair: keyPair);
  return _base64UrlNoPad(signature.bytes);
}

/// Verifies a base64url-encoded signature against a canonical JSON payload.
///
/// Matches the TypeScript `verifyCanonicalPayload()`.
Future<bool> verifyCanonicalPayload(
  dynamic input,
  String signatureBase64Url,
  String publicKeyPem,
) async {
  final payload = utf8.encode(canonicalJson(input));

  final der = _pemToDer(publicKeyPem);
  if (der == null) return false;
  final rawKey = _parsePublicKeySpki(der);
  if (rawKey == null) return false;

  final publicKey = SimplePublicKey(rawKey.toList(), type: KeyPairType.ed25519);

  final sigBytes = _base64UrlNoPadDecode(signatureBase64Url);
  // Ed25519 signatures are always 64 bytes
  if (sigBytes.length != 64) return false;

  final signature = Signature(sigBytes, publicKey: publicKey);
  return _ed25519.verify(payload, signature: signature);
}

/// Hashes a canonical JSON payload and returns the base64url-encoded hash.
///
/// Matches the TypeScript `hashCanonicalPayload()`.
String hashCanonicalPayload(dynamic input) {
  final hash = crypto.sha256.convert(utf8.encode(canonicalJson(input)));
  return _base64UrlNoPad(hash.bytes);
}
