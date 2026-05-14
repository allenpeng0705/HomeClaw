import 'package:web_socket_channel/web_socket_channel.dart';

import 'relay_transport_io.dart'
    if (dart.library.html) 'relay_transport_web.dart' as relay_impl;

/// Opens the relay WebSocket. On VM/desktop/mobile, pairing [headers]
/// use [dart:io] so `Authorization` / etc. survive the upgrade.
WebSocketChannel openRelayTransport(
  Uri uri, {
  required Duration handshakeTimeout,
  Map<String, dynamic>? headers,
}) {
  return relay_impl.openRelayTransport(
    uri,
    handshakeTimeout: handshakeTimeout,
    headers: headers,
  );
}
