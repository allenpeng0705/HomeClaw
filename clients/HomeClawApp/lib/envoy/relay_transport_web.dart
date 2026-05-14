import 'package:web_socket_channel/web_socket_channel.dart';

WebSocketChannel openRelayTransport(
  Uri uri, {
  required Duration handshakeTimeout,
  Map<String, dynamic>? headers,
}) {
  return WebSocketChannel.connect(uri);
}
