import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

WebSocketChannel openRelayTransport(
  Uri uri, {
  required Duration handshakeTimeout,
  Map<String, dynamic>? headers,
}) {
  if (headers != null && headers.isNotEmpty) {
    return IOWebSocketChannel.connect(
      uri,
      headers: headers,
      connectTimeout: handshakeTimeout,
    );
  }
  return WebSocketChannel.connect(uri);
}
