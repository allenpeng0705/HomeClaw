import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// hc-e2e-v1: X25519 ephemeral + HKDF-SHA256 + AES-256-GCM (matches Core `core/federation_e2e.py`).
class FederationE2eCrypto {
  FederationE2eCrypto._();

  static const String algo = 'hc-e2e-v1';
  static const String _hkdfSalt = 'homeclaw-fed-e2e-v1';
  static const String secureStorageSeedKey = 'federation_e2e_x25519_seed_b64';

  static final X25519 _x25519 = X25519();
  static final Hkdf _hkdf = Hkdf(hmac: Hmac.sha256(), outputLength: 32);
  static final AesGcm _aes = AesGcm.with256bits();
  static final Random _rng = Random.secure();

  /// Persisted 32-byte seed for `X25519.newKeyPairFromSeed` (RFC-style; not double-clamped).
  /// Load existing seed only (no write). Used to decrypt; do not create keys on read path.
  static Future<SimpleKeyPair?> tryLoadKeyPair(FlutterSecureStorage storage) async {
    final existing = await storage.read(key: secureStorageSeedKey);
    if (existing == null || existing.isEmpty) return null;
    try {
      final seed = Uint8List.fromList(base64Decode(existing.trim()));
      if (seed.length != 32) return null;
      return _x25519.newKeyPairFromSeed(seed);
    } catch (_) {
      return null;
    }
  }

  static Future<SimpleKeyPair> loadOrCreateKeyPair(FlutterSecureStorage storage) async {
    final existing = await storage.read(key: secureStorageSeedKey);
    Uint8List seed;
    if (existing != null && existing.isNotEmpty) {
      try {
        seed = Uint8List.fromList(base64Decode(existing.trim()));
      } catch (_) {
        seed = _random32();
        await storage.write(key: secureStorageSeedKey, value: base64Encode(seed));
      }
      if (seed.length != 32) {
        seed = _random32();
        await storage.write(key: secureStorageSeedKey, value: base64Encode(seed));
      }
    } else {
      seed = _random32();
      await storage.write(key: secureStorageSeedKey, value: base64Encode(seed));
    }
    return _x25519.newKeyPairFromSeed(seed);
  }

  static Uint8List _random32() => Uint8List.fromList(List<int>.generate(32, (_) => _rng.nextInt(256)));

  static String _stringField(Map<String, dynamic> e2e, String a, String b) {
    final v = e2e[a] ?? e2e[b];
    if (v is String) return v.trim();
    if (v == null) return '';
    return v.toString().trim();
  }

  static Future<Map<String, String>> encryptEnvelopeUtf8({
    required String plaintext,
    required Uint8List recipientPublicKey32,
  }) async {
    if (recipientPublicKey32.length != 32) {
      throw ArgumentError.value(recipientPublicKey32.length, 'recipientPublicKey32', 'expected 32 bytes');
    }
    final ephemeral = await _x25519.newKeyPair();
    final remotePub = SimplePublicKey(recipientPublicKey32, type: KeyPairType.x25519);
    final shared = await _x25519.sharedSecretKey(keyPair: ephemeral, remotePublicKey: remotePub);
    final aesSecretKey = await _hkdf.deriveKey(
      secretKey: shared,
      nonce: utf8.encode(_hkdfSalt),
      info: Uint8List(0),
    );
    final nonce12 = Uint8List.fromList(List<int>.generate(12, (_) => _rng.nextInt(256)));
    final box = await _aes.encrypt(
      utf8.encode(plaintext),
      secretKey: aesSecretKey,
      nonce: nonce12,
    );
    final ctWithTag = Uint8List(box.cipherText.length + box.mac.bytes.length);
    ctWithTag.setAll(0, box.cipherText);
    ctWithTag.setAll(box.cipherText.length, box.mac.bytes);
    final epk = await ephemeral.extractPublicKey();
    return {
      'algo': algo,
      'ephemeral_public_key_b64': base64Encode(epk.bytes),
      'nonce_b64': base64Encode(box.nonce),
      'ciphertext_b64': base64Encode(ctWithTag),
    };
  }

  /// Decrypt inbox `e2e` map; returns UTF-8 text or null.
  static Future<String?> decryptEnvelopeUtf8({
    required Map<String, dynamic> e2e,
    required SimpleKeyPair recipientKeyPair,
  }) async {
    final a = _stringField(e2e, 'algo', 'algorithm');
    if (a.isNotEmpty && a != algo) return null;
    Uint8List epk;
    Uint8List nonce;
    Uint8List ct;
    try {
      epk = Uint8List.fromList(base64Decode(_stringField(e2e, 'ephemeral_public_key_b64', 'ephemeral_public_key')));
      nonce = Uint8List.fromList(base64Decode(_stringField(e2e, 'nonce_b64', 'nonce')));
      ct = Uint8List.fromList(base64Decode(_stringField(e2e, 'ciphertext_b64', 'ciphertext')));
    } catch (_) {
      return null;
    }
    if (epk.length != 32 || nonce.length != 12 || ct.length < 16) return null;
    final remotePub = SimplePublicKey(epk, type: KeyPairType.x25519);
    final shared = await _x25519.sharedSecretKey(keyPair: recipientKeyPair, remotePublicKey: remotePub);
    final aesSecretKey = await _hkdf.deriveKey(
      secretKey: shared,
      nonce: utf8.encode(_hkdfSalt),
      info: Uint8List(0),
    );
    const macLen = 16;
    final cipherOnly = ct.sublist(0, ct.length - macLen);
    final macBytes = ct.sublist(ct.length - macLen);
    final box = SecretBox(cipherOnly, nonce: nonce, mac: Mac(macBytes));
    try {
      final clear = await _aes.decrypt(box, secretKey: aesSecretKey);
      return utf8.decode(clear, allowMalformed: true);
    } catch (_) {
      return null;
    }
  }

  static Future<String> publicKeyB64(SimpleKeyPair kp) async {
    final pub = await kp.extractPublicKey();
    return base64Encode(pub.bytes);
  }
}
