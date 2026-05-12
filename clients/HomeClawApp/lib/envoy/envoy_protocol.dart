import 'dart:convert';

import 'package:uuid/uuid.dart';

import 'envoy_identity.dart';

const _uuid = Uuid();

// ============================================
// Enums
// ============================================

/// All valid EnvoyMesh intents (56 values).
enum EnvoyIntent {
  systemPing,
  systemSignal,
  agentCardRequest,
  agentCardResponse,
  authChallenge,
  authChallengeResponse,
  bondRequest,
  bondAccept,
  bondChallenge,
  bondChallengeResponse,
  discoveryRequest,
  discoveryResponse,
  relayPeersRequest,
  relayPeersResponse,
  relayCheckin,
  relayLookup,
  relayLookupResponse,
  relayHintsRequest,
  relayHintsResponse,
  relayJoinRequest,
  relayJoinResponse,
  relayRegister,
  relayRegisterResponse,
  relaySummary,
  chatMessage,
  knowledgeQuery,
  knowledgeResponse,
  taskMandate,
  taskPropose,
  taskNegotiate,
  taskAccept,
  taskReject,
  taskCancel,
  taskHeartbeat,
  taskResult,
  reportCreate,
  syncState,
  devicePairRequest,
  devicePairApprove,
  devicePairDeferred,
  rendezvousRegister,
  rendezvousQuery,
  rendezvousResponse,
  sharePreview,
  shareRequest,
  shareAccept,
  broadcastRequest,
  broadcastResponse,
  broadcastCancel,
  taskFeedback,
  officialCredential,
}

/// Maps [EnvoyIntent] to its wire-format string.
const Map<EnvoyIntent, String> _intentToString = {
  EnvoyIntent.systemPing: 'system.ping',
  EnvoyIntent.systemSignal: 'system.signal',
  EnvoyIntent.agentCardRequest: 'agent.card.request',
  EnvoyIntent.agentCardResponse: 'agent.card.response',
  EnvoyIntent.authChallenge: 'auth.challenge',
  EnvoyIntent.authChallengeResponse: 'auth.challenge.response',
  EnvoyIntent.bondRequest: 'bond.request',
  EnvoyIntent.bondAccept: 'bond.accept',
  EnvoyIntent.bondChallenge: 'bond.challenge',
  EnvoyIntent.bondChallengeResponse: 'bond.challenge.response',
  EnvoyIntent.discoveryRequest: 'discovery.request',
  EnvoyIntent.discoveryResponse: 'discovery.response',
  EnvoyIntent.relayPeersRequest: 'relay.peers.request',
  EnvoyIntent.relayPeersResponse: 'relay.peers.response',
  EnvoyIntent.relayCheckin: 'relay.checkin',
  EnvoyIntent.relayLookup: 'relay.lookup',
  EnvoyIntent.relayLookupResponse: 'relay.lookup.response',
  EnvoyIntent.relayHintsRequest: 'relay.hints.request',
  EnvoyIntent.relayHintsResponse: 'relay.hints.response',
  EnvoyIntent.relayJoinRequest: 'relay.join.request',
  EnvoyIntent.relayJoinResponse: 'relay.join.response',
  EnvoyIntent.relayRegister: 'relay.register',
  EnvoyIntent.relayRegisterResponse: 'relay.register.response',
  EnvoyIntent.relaySummary: 'relay.summary',
  EnvoyIntent.chatMessage: 'chat.message',
  EnvoyIntent.knowledgeQuery: 'knowledge.query',
  EnvoyIntent.knowledgeResponse: 'knowledge.response',
  EnvoyIntent.taskMandate: 'task.mandate',
  EnvoyIntent.taskPropose: 'task.propose',
  EnvoyIntent.taskNegotiate: 'task.negotiate',
  EnvoyIntent.taskAccept: 'task.accept',
  EnvoyIntent.taskReject: 'task.reject',
  EnvoyIntent.taskCancel: 'task.cancel',
  EnvoyIntent.taskHeartbeat: 'task.heartbeat',
  EnvoyIntent.taskResult: 'task.result',
  EnvoyIntent.reportCreate: 'report.create',
  EnvoyIntent.syncState: 'sync.state',
  EnvoyIntent.devicePairRequest: 'device.pair.request',
  EnvoyIntent.devicePairApprove: 'device.pair.approve',
  EnvoyIntent.devicePairDeferred: 'device.pair.deferred',
  EnvoyIntent.rendezvousRegister: 'rendezvous.register',
  EnvoyIntent.rendezvousQuery: 'rendezvous.query',
  EnvoyIntent.rendezvousResponse: 'rendezvous.response',
  EnvoyIntent.sharePreview: 'share.preview',
  EnvoyIntent.shareRequest: 'share.request',
  EnvoyIntent.shareAccept: 'share.accept',
  EnvoyIntent.broadcastRequest: 'broadcast.request',
  EnvoyIntent.broadcastResponse: 'broadcast.response',
  EnvoyIntent.broadcastCancel: 'broadcast.cancel',
  EnvoyIntent.taskFeedback: 'task.feedback',
  EnvoyIntent.officialCredential: 'official.credential',
};

/// Parses a wire-format intent string. Returns null if not a valid intent.
EnvoyIntent? parseIntent(String s) {
  for (final entry in _intentToString.entries) {
    if (entry.value == s) return entry.key;
  }
  return null;
}

String _intentStr(EnvoyIntent i) => _intentToString[i]!;

/// Returns the wire-format string for an [EnvoyIntent] (e.g. `"chat.message"`).
String envoyIntentToString(EnvoyIntent intent) => _intentToString[intent]!;

/// Actor role: human, agent, or system.
enum EnvoyActorRole { human, agent, system }

const Map<EnvoyActorRole, String> _roleToString = {
  EnvoyActorRole.human: 'human',
  EnvoyActorRole.agent: 'agent',
  EnvoyActorRole.system: 'system',
};

const Map<String, EnvoyActorRole> _stringToRole = {
  'human': EnvoyActorRole.human,
  'agent': EnvoyActorRole.agent,
  'system': EnvoyActorRole.system,
};

String _roleStr(EnvoyActorRole r) => _roleToString[r]!;
EnvoyActorRole? _parseRole(String s) => _stringToRole[s];

enum RelayVisibility { public, capability, bonded, private }

const Map<RelayVisibility, String> _visibilityToString = {
  RelayVisibility.public: 'public',
  RelayVisibility.capability: 'capability',
  RelayVisibility.bonded: 'bonded',
  RelayVisibility.private: 'private',
};

const Map<String, RelayVisibility> _stringToVisibility = {
  'public': RelayVisibility.public,
  'capability': RelayVisibility.capability,
  'bonded': RelayVisibility.bonded,
  'private': RelayVisibility.private,
};

String _visStr(RelayVisibility v) => _visibilityToString[v]!;
RelayVisibility? _parseVisibility(String s) => _stringToVisibility[s];

// ============================================
// Validation result
// ============================================

class ParseResult<T> {
  final T? value;
  final String? reason;

  const ParseResult.ok(this.value) : reason = null;
  const ParseResult.error(this.reason) : value = null;
}

// ============================================
// Payload types
// ============================================

/// `chat.message` payload: { senderOwnerId, text }
class ChatMessagePayload {
  final String senderOwnerId;
  final String text;

  const ChatMessagePayload({required this.senderOwnerId, required this.text});

  factory ChatMessagePayload.fromJson(Map<String, dynamic> json) {
    final senderOwnerId = json['senderOwnerId'];
    final text = json['text'];
    if (senderOwnerId is! String || senderOwnerId.isEmpty) {
      throw FormatException('senderOwnerId must be a non-empty string');
    }
    if (text is! String || text.isEmpty || text.length > 4000) {
      throw FormatException('text must be 1-4000 characters');
    }
    return ChatMessagePayload(senderOwnerId: senderOwnerId, text: text);
  }

  Map<String, dynamic> toJson() => {
    'senderOwnerId': senderOwnerId,
    'text': text,
  };
}

/// `system.ping` payload: { nonce, message? }
class SystemPingPayload {
  final String nonce;
  final String? message;

  const SystemPingPayload({required this.nonce, this.message});

  factory SystemPingPayload.fromJson(Map<String, dynamic> json) {
    final nonce = json['nonce'];
    final message = json['message'];
    if (nonce is! String || nonce.isEmpty) {
      throw FormatException('nonce must be a non-empty string');
    }
    if (message != null && message is! String) {
      throw FormatException('message must be a string');
    }
    if (message is String && message.length > 512) {
      throw FormatException('message must be <= 512 characters');
    }
    return SystemPingPayload(nonce: nonce, message: message);
  }

  Map<String, dynamic> toJson() {
    if (message == null) return {'nonce': nonce};
    return {'nonce': nonce, 'message': message};
  }
}

/// `system.signal` payload
class SystemSignalPayload {
  final String ownerId;
  final String ownerPublicKeyPem;
  final String deviceId;
  final Map<String, dynamic> deviceCertificate;
  final String deviceProfile;
  final List<String> capabilities;
  final List<String> supportedProtocolVersions;
  final List<String> listenAddrs;
  final List<String> publicTopics;
  final String status;

  const SystemSignalPayload({
    required this.ownerId,
    required this.ownerPublicKeyPem,
    required this.deviceId,
    required this.deviceCertificate,
    required this.deviceProfile,
    required this.capabilities,
    required this.supportedProtocolVersions,
    this.listenAddrs = const [],
    this.publicTopics = const [],
    this.status = 'online',
  });

  factory SystemSignalPayload.fromJson(Map<String, dynamic> json) {
    final ownerId = json['ownerId'];
    final ownerPublicKeyPem = json['ownerPublicKeyPem'];
    final deviceId = json['deviceId'];
    final deviceCertificate = json['deviceCertificate'];
    final deviceProfile = json['deviceProfile'];
    final capabilities = json['capabilities'];
    final supportedProtocolVersions = json['supportedProtocolVersions'];

    if (ownerId is! String || ownerId.isEmpty) {
      throw FormatException('ownerId must be a non-empty string');
    }
    if (ownerPublicKeyPem is! String || ownerPublicKeyPem.isEmpty) {
      throw FormatException('ownerPublicKeyPem must be a non-empty string');
    }
    if (deviceId is! String || deviceId.isEmpty) {
      throw FormatException('deviceId must be a non-empty string');
    }
    if (deviceCertificate is! Map<String, dynamic>) {
      throw FormatException('deviceCertificate must be an object');
    }
    if (deviceProfile is! String || deviceProfile.isEmpty) {
      throw FormatException('deviceProfile must be a non-empty string');
    }
    if (capabilities is! List || capabilities.isEmpty) {
      throw FormatException('capabilities must be a non-empty array');
    }
    if (supportedProtocolVersions is! List || supportedProtocolVersions.isEmpty) {
      throw FormatException('supportedProtocolVersions must be a non-empty array');
    }
    final status = json['status'] as String? ?? 'online';
    if (!['online', 'away', 'busy'].contains(status)) {
      throw FormatException('status must be "online", "away", or "busy"');
    }

    return SystemSignalPayload(
      ownerId: ownerId,
      ownerPublicKeyPem: ownerPublicKeyPem,
      deviceId: deviceId,
      deviceCertificate: deviceCertificate,
      deviceProfile: deviceProfile,
      capabilities: List<String>.from(capabilities),
      supportedProtocolVersions: List<String>.from(supportedProtocolVersions),
      listenAddrs: List<String>.from(json['listenAddrs'] as List? ?? []),
      publicTopics: List<String>.from(json['publicTopics'] as List? ?? []),
      status: status,
    );
  }

  Map<String, dynamic> toJson() => {
    'ownerId': ownerId,
    'ownerPublicKeyPem': ownerPublicKeyPem,
    'deviceId': deviceId,
    'deviceCertificate': deviceCertificate,
    'deviceProfile': deviceProfile,
    'capabilities': capabilities,
    'supportedProtocolVersions': supportedProtocolVersions,
    if (listenAddrs.isNotEmpty) 'listenAddrs': listenAddrs,
    if (publicTopics.isNotEmpty) 'publicTopics': publicTopics,
    'status': status,
  };
}

// ============================================
// Relay types
// ============================================

class RelayHint {
  final String relayId;
  final int? level;
  final String? region;
  final List<String> multiaddrs;
  final double? scoreHint;
  final String? expiresAt;

  const RelayHint({
    required this.relayId,
    this.level,
    this.region,
    this.multiaddrs = const [],
    this.scoreHint,
    this.expiresAt,
  });

  factory RelayHint.fromJson(Map<String, dynamic> json) {
    final relayId = json['relayId'];
    if (relayId is! String || relayId.isEmpty) {
      throw FormatException('relayId must be a non-empty string');
    }
    return RelayHint(
      relayId: relayId,
      level: json['level'] as int?,
      region: json['region'] as String?,
      multiaddrs: List<String>.from(json['multiaddrs'] as List? ?? []),
      scoreHint: (json['scoreHint'] as num?)?.toDouble(),
      expiresAt: json['expiresAt'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
    'relayId': relayId,
    if (level != null) 'level': level,
    if (region != null) 'region': region,
    if (multiaddrs.isNotEmpty) 'multiaddrs': multiaddrs,
    if (scoreHint != null) 'scoreHint': scoreHint,
    if (expiresAt != null) 'expiresAt': expiresAt,
  };
}

class RelayPeerInfo {
  final String peerId;
  final String ownerId;
  final List<String> multiaddrs;

  const RelayPeerInfo({
    required this.peerId,
    required this.ownerId,
    this.multiaddrs = const [],
  });

  factory RelayPeerInfo.fromJson(Map<String, dynamic> json) {
    final peerId = json['peerId'];
    final ownerId = json['ownerId'];
    if (peerId is! String || peerId.isEmpty) {
      throw FormatException('peerId must be a non-empty string');
    }
    if (ownerId is! String || ownerId.isEmpty) {
      throw FormatException('ownerId must be a non-empty string');
    }
    return RelayPeerInfo(
      peerId: peerId,
      ownerId: ownerId,
      multiaddrs: List<String>.from(json['multiaddrs'] as List? ?? []),
    );
  }

  Map<String, dynamic> toJson() => {
    'peerId': peerId,
    'ownerId': ownerId,
    if (multiaddrs.isNotEmpty) 'multiaddrs': multiaddrs,
  };
}

class RelayPeerCandidate {
  final String peerId;
  final String? ownerId;
  final List<String> multiaddrs;
  final String? viaRelayId;
  final List<String> capabilities;
  final RelayVisibility visibility;
  final String? expiresAt;

  const RelayPeerCandidate({
    required this.peerId,
    this.ownerId,
    this.multiaddrs = const [],
    this.viaRelayId,
    this.capabilities = const [],
    this.visibility = RelayVisibility.public,
    this.expiresAt,
  });

  factory RelayPeerCandidate.fromJson(Map<String, dynamic> json) {
    final peerId = json['peerId'];
    if (peerId is! String || peerId.isEmpty) {
      throw FormatException('peerId must be a non-empty string');
    }
    final visStr = json['visibility'] as String? ?? 'public';
    final visibility = _parseVisibility(visStr);
    if (visibility == null) {
      throw FormatException('invalid visibility: $visStr');
    }
    return RelayPeerCandidate(
      peerId: peerId,
      ownerId: json['ownerId'] as String?,
      multiaddrs: List<String>.from(json['multiaddrs'] as List? ?? []),
      viaRelayId: json['viaRelayId'] as String?,
      capabilities: List<String>.from(json['capabilities'] as List? ?? []),
      visibility: visibility,
      expiresAt: json['expiresAt'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
    'peerId': peerId,
    if (ownerId != null) 'ownerId': ownerId,
    if (multiaddrs.isNotEmpty) 'multiaddrs': multiaddrs,
    if (viaRelayId != null) 'viaRelayId': viaRelayId,
    if (capabilities.isNotEmpty) 'capabilities': capabilities,
    'visibility': _visStr(visibility),
    if (expiresAt != null) 'expiresAt': expiresAt,
  };
}

// ============================================
// Relay payloads
// ============================================

class RelayPeersRequestPayload {
  const RelayPeersRequestPayload();

  factory RelayPeersRequestPayload.fromJson(Map<String, dynamic> _) =>
    const RelayPeersRequestPayload();

  Map<String, dynamic> toJson() => {};
}

class RelayPeersResponsePayload {
  final String requestMessageId;
  final List<RelayPeerInfo> peers;

  const RelayPeersResponsePayload({
    required this.requestMessageId,
    this.peers = const [],
  });

  factory RelayPeersResponsePayload.fromJson(Map<String, dynamic> json) {
    final requestMessageId = json['requestMessageId'];
    if (requestMessageId is! String || requestMessageId.isEmpty) {
      throw FormatException('requestMessageId must be a non-empty string');
    }
    final peersList = (json['peers'] as List?)?.map(
      (p) => RelayPeerInfo.fromJson(p as Map<String, dynamic>),
    ).toList() ?? <RelayPeerInfo>[];
    return RelayPeersResponsePayload(
      requestMessageId: requestMessageId,
      peers: peersList,
    );
  }

  Map<String, dynamic> toJson() => {
    'requestMessageId': requestMessageId,
    if (peers.isNotEmpty) 'peers': peers.map((p) => p.toJson()).toList(),
  };
}

class RelayLookupPayload {
  final String queryId;
  final String? targetPeerId;
  final String? targetOwnerId;
  final String? capability;
  final String? topicHash;
  final int maxResults;
  final int maxHops;
  final int maxFanout;
  final RelayVisibility visibilityScope;
  final String expiresAt;

  const RelayLookupPayload({
    required this.queryId,
    this.targetPeerId,
    this.targetOwnerId,
    this.capability,
    this.topicHash,
    this.maxResults = 20,
    this.maxHops = 0,
    this.maxFanout = 2,
    this.visibilityScope = RelayVisibility.public,
    required this.expiresAt,
  });

  factory RelayLookupPayload.fromJson(Map<String, dynamic> json) {
    final queryId = json['queryId'];
    if (queryId is! String || queryId.isEmpty) {
      throw FormatException('queryId must be a non-empty string');
    }
    final hasTarget = json['targetPeerId'] != null ||
        json['targetOwnerId'] != null ||
        json['capability'] != null ||
        json['topicHash'] != null;
    if (!hasTarget) {
      throw FormatException(
        'relay.lookup requires targetPeerId, targetOwnerId, capability, or topicHash',
      );
    }
    final visStr = json['visibilityScope'] as String? ?? 'public';
    final visibilityScope = _parseVisibility(visStr);
    if (visibilityScope == null) {
      throw FormatException('invalid visibilityScope: $visStr');
    }
    return RelayLookupPayload(
      queryId: queryId,
      targetPeerId: json['targetPeerId'] as String?,
      targetOwnerId: json['targetOwnerId'] as String?,
      capability: json['capability'] as String?,
      topicHash: json['topicHash'] as String?,
      maxResults: json['maxResults'] as int? ?? 20,
      maxHops: json['maxHops'] as int? ?? 0,
      maxFanout: json['maxFanout'] as int? ?? 2,
      visibilityScope: visibilityScope,
      expiresAt: json['expiresAt'] as String,
    );
  }

  Map<String, dynamic> toJson() => {
    'queryId': queryId,
    if (targetPeerId != null) 'targetPeerId': targetPeerId,
    if (targetOwnerId != null) 'targetOwnerId': targetOwnerId,
    if (capability != null) 'capability': capability,
    if (topicHash != null) 'topicHash': topicHash,
    'maxResults': maxResults,
    'maxHops': maxHops,
    'maxFanout': maxFanout,
    'visibilityScope': _visStr(visibilityScope),
    'expiresAt': expiresAt,
  };
}

class RelayLookupResponsePayload {
  final String queryId;
  final List<RelayPeerCandidate> peers;
  final List<RelayHint> relayHints;
  final bool truncated;
  final String? policy;
  final String expiresAt;

  const RelayLookupResponsePayload({
    required this.queryId,
    this.peers = const [],
    this.relayHints = const [],
    this.truncated = false,
    this.policy,
    required this.expiresAt,
  });

  factory RelayLookupResponsePayload.fromJson(Map<String, dynamic> json) {
    final queryId = json['queryId'];
    final expiresAt = json['expiresAt'];
    if (queryId is! String || queryId.isEmpty) {
      throw FormatException('queryId must be a non-empty string');
    }
    if (expiresAt is! String || expiresAt.isEmpty) {
      throw FormatException('expiresAt must be a non-empty string');
    }
    return RelayLookupResponsePayload(
      queryId: queryId,
      peers: (json['peers'] as List?)
          ?.map((p) => RelayPeerCandidate.fromJson(p as Map<String, dynamic>))
          .toList() ?? [],
      relayHints: (json['relayHints'] as List?)
          ?.map((h) => RelayHint.fromJson(h as Map<String, dynamic>))
          .toList() ?? [],
      truncated: json['truncated'] as bool? ?? false,
      policy: json['policy'] as String?,
      expiresAt: expiresAt,
    );
  }

  Map<String, dynamic> toJson() => {
    'queryId': queryId,
    if (peers.isNotEmpty) 'peers': peers.map((p) => p.toJson()).toList(),
    if (relayHints.isNotEmpty)
      'relayHints': relayHints.map((h) => h.toJson()).toList(),
    'truncated': truncated,
    if (policy != null) 'policy': policy,
    'expiresAt': expiresAt,
  };
}

class RelayHintsRequestPayload {
  /// One of: lookup-failed, dial-failed, bootstrap, refresh
  final String reason;
  final String? region;
  final int maxResults;
  final String expiresAt;

  const RelayHintsRequestPayload({
    this.reason = 'refresh',
    this.region,
    this.maxResults = 10,
    required this.expiresAt,
  });

  factory RelayHintsRequestPayload.fromJson(Map<String, dynamic> json) {
    final reason = json['reason'] as String? ?? 'refresh';
    if (!['lookup-failed', 'dial-failed', 'bootstrap', 'refresh'].contains(reason)) {
      throw FormatException(
        'reason must be one of: lookup-failed, dial-failed, bootstrap, refresh',
      );
    }
    return RelayHintsRequestPayload(
      reason: reason,
      region: json['region'] as String?,
      maxResults: json['maxResults'] as int? ?? 10,
      expiresAt: json['expiresAt'] as String,
    );
  }

  Map<String, dynamic> toJson() => {
    'reason': reason,
    if (region != null) 'region': region,
    'maxResults': maxResults,
    'expiresAt': expiresAt,
  };
}

class RelayHintsResponsePayload {
  final List<RelayHint> relayHints;
  final bool truncated;
  final String expiresAt;

  const RelayHintsResponsePayload({
    this.relayHints = const [],
    this.truncated = false,
    required this.expiresAt,
  });

  factory RelayHintsResponsePayload.fromJson(Map<String, dynamic> json) {
    return RelayHintsResponsePayload(
      relayHints: (json['relayHints'] as List?)
          ?.map((h) => RelayHint.fromJson(h as Map<String, dynamic>))
          .toList() ?? [],
      truncated: json['truncated'] as bool? ?? false,
      expiresAt: json['expiresAt'] as String,
    );
  }

  Map<String, dynamic> toJson() => {
    if (relayHints.isNotEmpty)
      'relayHints': relayHints.map((h) => h.toJson()).toList(),
    'truncated': truncated,
    'expiresAt': expiresAt,
  };
}

// ============================================
// Envelope
// ============================================

/// Full signed EnvoyEnvelope, matching the TypeScript `EnvoyEnvelope<TPayload>`.
class EnvoyEnvelope {
  final String version;
  final String messageId;
  final String? correlationId;
  final String createdAt;
  final String senderPeerId;
  final String senderPublicKey;
  final EnvoyActorRole senderRole;
  final String? recipientPeerId;
  final EnvoyActorRole recipientRole;
  final EnvoyIntent intent;
  final dynamic payload;
  final Map<String, dynamic>? agentCredential;
  final String signature;

  const EnvoyEnvelope({
    required this.version,
    required this.messageId,
    this.correlationId,
    required this.createdAt,
    required this.senderPeerId,
    required this.senderPublicKey,
    required this.senderRole,
    this.recipientPeerId,
    required this.recipientRole,
    required this.intent,
    required this.payload,
    this.agentCredential,
    required this.signature,
  });

  /// Returns the unsigned form of this envelope (drops `signature`).
  UnsignedEnvoyEnvelope get unsigned {
    return UnsignedEnvoyEnvelope(
      version: version,
      messageId: messageId,
      correlationId: correlationId,
      createdAt: createdAt,
      senderPeerId: senderPeerId,
      senderPublicKey: senderPublicKey,
      senderRole: senderRole,
      recipientPeerId: recipientPeerId,
      recipientRole: recipientRole,
      intent: intent,
      payload: payload,
      agentCredential: agentCredential,
    );
  }

  factory EnvoyEnvelope.fromJson(Map<String, dynamic> json) {
    _validateEnvelopeBase(json);

    final signature = json['signature'];
    if (signature is! String || signature.isEmpty) {
      throw FormatException('signature must be a non-empty string');
    }

    return EnvoyEnvelope(
      version: json['version'],
      messageId: json['messageId'],
      correlationId: json['correlationId'] as String?,
      createdAt: json['createdAt'],
      senderPeerId: json['senderPeerId'],
      senderPublicKey: json['senderPublicKey'],
      senderRole: _parseRole(json['senderRole'])!,
      recipientPeerId: json['recipientPeerId'] as String?,
      recipientRole: _parseRole(json['recipientRole'])!,
      intent: parseIntent(json['intent'])!,
      payload: json['payload'],
      agentCredential: json['agentCredential'] as Map<String, dynamic>?,
      signature: signature,
    );
  }

  Map<String, dynamic> toJson() {
    final m = <String, dynamic>{
      'version': version,
      'messageId': messageId,
      'createdAt': createdAt,
      'senderPeerId': senderPeerId,
      'senderPublicKey': senderPublicKey,
      'senderRole': _roleStr(senderRole),
      'recipientRole': _roleStr(recipientRole),
      'intent': _intentStr(intent),
      'payload': payload,
      'signature': signature,
    };
    if (correlationId != null) m['correlationId'] = correlationId;
    if (recipientPeerId != null) m['recipientPeerId'] = recipientPeerId;
    if (agentCredential != null) m['agentCredential'] = agentCredential;
    return m;
  }
}

/// Unsigned envelope (no signature), used for signing and pre-transmission.
class UnsignedEnvoyEnvelope {
  final String version;
  final String messageId;
  final String? correlationId;
  final String createdAt;
  final String senderPeerId;
  final String senderPublicKey;
  final EnvoyActorRole senderRole;
  final String? recipientPeerId;
  final EnvoyActorRole recipientRole;
  final EnvoyIntent intent;
  final dynamic payload;
  final Map<String, dynamic>? agentCredential;

  const UnsignedEnvoyEnvelope({
    required this.version,
    required this.messageId,
    this.correlationId,
    required this.createdAt,
    required this.senderPeerId,
    required this.senderPublicKey,
    required this.senderRole,
    this.recipientPeerId,
    required this.recipientRole,
    required this.intent,
    required this.payload,
    this.agentCredential,
  });

  /// Attach a signature to produce a full signed envelope.
  EnvoyEnvelope sign(String signature) {
    return EnvoyEnvelope(
      version: version,
      messageId: messageId,
      correlationId: correlationId,
      createdAt: createdAt,
      senderPeerId: senderPeerId,
      senderPublicKey: senderPublicKey,
      senderRole: senderRole,
      recipientPeerId: recipientPeerId,
      recipientRole: recipientRole,
      intent: intent,
      payload: payload,
      agentCredential: agentCredential,
      signature: signature,
    );
  }

  factory UnsignedEnvoyEnvelope.fromJson(Map<String, dynamic> json) {
    _validateEnvelopeBase(json);
    return UnsignedEnvoyEnvelope(
      version: json['version'],
      messageId: json['messageId'],
      correlationId: json['correlationId'] as String?,
      createdAt: json['createdAt'],
      senderPeerId: json['senderPeerId'],
      senderPublicKey: json['senderPublicKey'],
      senderRole: _parseRole(json['senderRole'])!,
      recipientPeerId: json['recipientPeerId'] as String?,
      recipientRole: _parseRole(json['recipientRole'])!,
      intent: parseIntent(json['intent'])!,
      payload: json['payload'],
      agentCredential: json['agentCredential'] as Map<String, dynamic>?,
    );
  }

  Map<String, dynamic> toJson() {
    final m = <String, dynamic>{
      'version': version,
      'messageId': messageId,
      'createdAt': createdAt,
      'senderPeerId': senderPeerId,
      'senderPublicKey': senderPublicKey,
      'senderRole': _roleStr(senderRole),
      'recipientRole': _roleStr(recipientRole),
      'intent': _intentStr(intent),
      'payload': payload,
    };
    if (correlationId != null) m['correlationId'] = correlationId;
    if (recipientPeerId != null) m['recipientPeerId'] = recipientPeerId;
    if (agentCredential != null) m['agentCredential'] = agentCredential;
    return m;
  }
}

/// Shared validation for the base envelope fields (excluding signature).
void _validateEnvelopeBase(Map<String, dynamic> json) {
  final version = json['version'];
  if (version != '0.1') throw FormatException('version must be "0.1"');

  final messageId = json['messageId'];
  if (messageId is! String || messageId.isEmpty) {
    throw FormatException('messageId must be a non-empty string');
  }
  final createdAt = json['createdAt'];
  if (createdAt is! String || createdAt.isEmpty) {
    throw FormatException('createdAt must be a non-empty string');
  }
  final senderPeerId = json['senderPeerId'];
  if (senderPeerId is! String || senderPeerId.isEmpty) {
    throw FormatException('senderPeerId must be a non-empty string');
  }
  final senderPublicKey = json['senderPublicKey'];
  if (senderPublicKey is! String || senderPublicKey.isEmpty) {
    throw FormatException('senderPublicKey must be a non-empty string');
  }

  final senderRoleStr = json['senderRole'] as String?;
  final senderRole = senderRoleStr != null ? _parseRole(senderRoleStr) : null;
  if (senderRole == null) {
    throw FormatException('senderRole must be "human", "agent", or "system"');
  }

  final recipientRoleStr = json['recipientRole'] as String?;
  final recipientRole =
      recipientRoleStr != null ? _parseRole(recipientRoleStr) : null;
  if (recipientRole == null) {
    throw FormatException('recipientRole must be "human", "agent", or "system"');
  }

  final intentStr = json['intent'] as String?;
  final intent = intentStr != null ? parseIntent(intentStr) : null;
  if (intent == null) {
    throw FormatException('invalid intent: $intentStr');
  }

  // Role policy
  final policyOk = evaluateEnvelopeRolePolicy(intent, senderRole, recipientRole);
  if (!policyOk) {
    throw FormatException(
      'role policy violation for ${_intentStr(intent)}: '
      'sender=${_roleStr(senderRole)} recipient=${_roleStr(recipientRole)}',
    );
  }

  // When senderRole is "agent" and intent is chat.message, agentCredential is required
  if (senderRole == EnvoyActorRole.agent && intent == EnvoyIntent.chatMessage) {
    final cred = json['agentCredential'];
    if (cred == null) {
      throw FormatException(
        'agentCredential is required when senderRole is "agent" for chat.message',
      );
    }
  }
}

// ============================================
// Role Policy
// ============================================

/// Enforces role policy rules for envelope intents.
/// Returns true if the combination is allowed.
bool evaluateEnvelopeRolePolicy(
  EnvoyIntent intent,
  EnvoyActorRole senderRole,
  EnvoyActorRole recipientRole,
) {
  if (intent == EnvoyIntent.chatMessage) {
    if (senderRole == EnvoyActorRole.system ||
        recipientRole == EnvoyActorRole.system) {
      return false;
    }
    return true;
  }

  final intentStr = _intentStr(intent);
  if (intentStr.startsWith('task.') || intent == EnvoyIntent.reportCreate) {
    if (senderRole != EnvoyActorRole.agent) return false;
    if (recipientRole != EnvoyActorRole.agent) return false;
  }

  return true;
}

// ============================================
// Constructor functions
// ============================================

/// Input for [createUnsignedEnvelope].
class CreateEnvelopeInput {
  final String senderPeerId;
  final String senderPublicKey;
  final EnvoyActorRole? senderRole;
  final String? recipientPeerId;
  final EnvoyActorRole? recipientRole;
  final EnvoyIntent intent;
  final dynamic payload;
  final Map<String, dynamic>? agentCredential;
  final String? createdAt;
  final String? messageId;
  final String? correlationId;

  const CreateEnvelopeInput({
    required this.senderPeerId,
    required this.senderPublicKey,
    this.senderRole,
    this.recipientPeerId,
    this.recipientRole,
    required this.intent,
    required this.payload,
    this.agentCredential,
    this.createdAt,
    this.messageId,
    this.correlationId,
  });
}

/// Creates an unsigned envelope with sensible defaults.
///
/// Default roles:
/// - `chat.message` → human ↔ human
/// - `system.*` → system → agent
/// - everything else → agent ↔ agent
UnsignedEnvoyEnvelope createUnsignedEnvelope(CreateEnvelopeInput input) {
  final EnvoyActorRole defaultSenderRole;
  final EnvoyActorRole defaultRecipientRole;

  if (input.intent == EnvoyIntent.chatMessage) {
    defaultSenderRole = EnvoyActorRole.human;
    defaultRecipientRole = EnvoyActorRole.human;
  } else if (_intentStr(input.intent).startsWith('system.')) {
    defaultSenderRole = EnvoyActorRole.system;
    defaultRecipientRole = EnvoyActorRole.agent;
  } else {
    defaultSenderRole = EnvoyActorRole.agent;
    defaultRecipientRole = EnvoyActorRole.agent;
  }

  final envelope = UnsignedEnvoyEnvelope(
    version: '0.1',
    messageId: input.messageId ?? _uuid.v4(),
    correlationId: input.correlationId,
    createdAt: input.createdAt ?? DateTime.now().toUtc().toIso8601String(),
    senderPeerId: input.senderPeerId,
    senderPublicKey: input.senderPublicKey,
    senderRole: input.senderRole ?? defaultSenderRole,
    recipientPeerId: input.recipientPeerId,
    recipientRole: input.recipientRole ?? defaultRecipientRole,
    intent: input.intent,
    payload: input.payload,
    agentCredential: input.agentCredential,
  );

  // Validate role policy
  final policyOk = evaluateEnvelopeRolePolicy(
    envelope.intent,
    envelope.senderRole,
    envelope.recipientRole,
  );
  if (!policyOk) {
    throw ArgumentError(
      'role policy violation: intent=${_intentStr(envelope.intent)} '
      'sender=${_roleStr(envelope.senderRole)} '
      'recipient=${_roleStr(envelope.recipientRole)}',
    );
  }

  // Validate agentCredential requirement
  if (envelope.senderRole == EnvoyActorRole.agent &&
      envelope.intent == EnvoyIntent.chatMessage &&
      envelope.agentCredential == null) {
    throw ArgumentError(
      'agentCredential is required when senderRole is "agent" for chat.message',
    );
  }

  return envelope;
}

/// Creates a `chat.message` payload.
ChatMessagePayload createChatMessagePayload({
  required String senderOwnerId,
  required String text,
}) {
  return ChatMessagePayload(senderOwnerId: senderOwnerId, text: text);
}

/// Creates a `system.ping` payload.
SystemPingPayload createSystemPingPayload({String? message}) {
  return SystemPingPayload(nonce: _uuid.v4(), message: message);
}

// ============================================
// Parser functions
// ============================================

/// Parses and validates a full signed envelope from raw JSON.
EnvoyEnvelope parseEnvelope(dynamic input) {
  if (input is String) {
    input = jsonDecode(input) as Map<String, dynamic>;
  }
  if (input is! Map<String, dynamic>) {
    throw FormatException('envelope must be a JSON object');
  }
  return EnvoyEnvelope.fromJson(input);
}

/// Parses and validates an unsigned envelope from raw JSON.
UnsignedEnvoyEnvelope parseUnsignedEnvelope(dynamic input) {
  if (input is String) {
    input = jsonDecode(input) as Map<String, dynamic>;
  }
  if (input is! Map<String, dynamic>) {
    throw FormatException('envelope must be a JSON object');
  }
  return UnsignedEnvoyEnvelope.fromJson(input);
}

/// Parses a `chat.message` payload.
ChatMessagePayload parseChatMessagePayload(dynamic input) {
  if (input is! Map<String, dynamic>) {
    throw FormatException('chat.message payload must be a JSON object');
  }
  return ChatMessagePayload.fromJson(input);
}

/// Parses a `system.ping` payload.
SystemPingPayload parseSystemPingPayload(dynamic input) {
  if (input is! Map<String, dynamic>) {
    throw FormatException('system.ping payload must be a JSON object');
  }
  return SystemPingPayload.fromJson(input);
}

/// Parses a `system.signal` payload.
SystemSignalPayload parseSystemSignalPayload(dynamic input) {
  if (input is! Map<String, dynamic>) {
    throw FormatException('system.signal payload must be a JSON object');
  }
  return SystemSignalPayload.fromJson(input);
}

/// Parses a `relay.peers.request` payload.
RelayPeersRequestPayload parseRelayPeersRequestPayload(dynamic input) {
  if (input is Map) {
    return RelayPeersRequestPayload.fromJson(
      Map<String, dynamic>.from(input),
    );
  }
  throw FormatException('relay.peers.request payload must be a JSON object');
}

/// Parses a `relay.peers.response` payload.
RelayPeersResponsePayload parseRelayPeersResponsePayload(dynamic input) {
  if (input is! Map<String, dynamic>) {
    throw FormatException('relay.peers.response payload must be a JSON object');
  }
  return RelayPeersResponsePayload.fromJson(input);
}

/// Parses a `relay.lookup` payload.
RelayLookupPayload parseRelayLookupPayload(dynamic input) {
  if (input is! Map<String, dynamic>) {
    throw FormatException('relay.lookup payload must be a JSON object');
  }
  return RelayLookupPayload.fromJson(input);
}

/// Parses a `relay.lookup.response` payload.
RelayLookupResponsePayload parseRelayLookupResponsePayload(dynamic input) {
  if (input is! Map<String, dynamic>) {
    throw FormatException('relay.lookup.response payload must be a JSON object');
  }
  return RelayLookupResponsePayload.fromJson(input);
}

/// Parses a `relay.hints.request` payload.
RelayHintsRequestPayload parseRelayHintsRequestPayload(dynamic input) {
  if (input is! Map<String, dynamic>) {
    throw FormatException('relay.hints.request payload must be a JSON object');
  }
  return RelayHintsRequestPayload.fromJson(input);
}

/// Parses a `relay.hints.response` payload.
RelayHintsResponsePayload parseRelayHintsResponsePayload(dynamic input) {
  if (input is! Map<String, dynamic>) {
    throw FormatException('relay.hints.response payload must be a JSON object');
  }
  return RelayHintsResponsePayload.fromJson(input);
}

// ============================================
// Signing helpers
// ============================================

/// Strips the signature from a signed envelope, returning the unsigned form
/// suitable for canonical JSON signing/verification.
///
/// Matches the TypeScript `envelopeForSigning()`.
Map<String, dynamic> envelopeForSigning(EnvoyEnvelope envelope) {
  final json = envelope.toJson();
  json.remove('signature');
  return json;
}

/// Strips the signature from a signed envelope, returning the unsigned form
/// as an [UnsignedEnvoyEnvelope] instance.
UnsignedEnvoyEnvelope envelopeAsUnsigned(EnvoyEnvelope envelope) {
  return envelope.unsigned;
}
