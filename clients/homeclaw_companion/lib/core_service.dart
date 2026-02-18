import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// HomeClaw Core API client.
/// Sends messages via POST /inbound and returns the reply text.
class CoreService {
  static const String _keyBaseUrl = 'core_base_url';
  static const String _keyApiKey = 'core_api_key';
  static const String _defaultBaseUrl = 'http://127.0.0.1:9000';

  String _baseUrl = _defaultBaseUrl;
  String? _apiKey;

  String get baseUrl => _baseUrl;
  String? get apiKey => _apiKey;

  Future<void> loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString(_keyBaseUrl) ?? _defaultBaseUrl;
    _apiKey = prefs.getString(_keyApiKey);
  }

  Future<void> saveSettings({required String baseUrl, String? apiKey}) async {
    _baseUrl = baseUrl.trim().replaceFirst(RegExp(r'/$'), '');
    _apiKey = apiKey?.trim().isEmpty == true ? null : apiKey?.trim();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyBaseUrl, _baseUrl);
    if (_apiKey != null) {
      await prefs.setString(_keyApiKey, _apiKey!);
    } else {
      await prefs.remove(_keyApiKey);
    }
  }

  /// Send a message to Core and return the reply text.
  /// Throws on network or API error.
  Future<String> sendMessage(String text, {String userId = 'companion'}) async {
    final url = Uri.parse('$_baseUrl/inbound');
    final body = jsonEncode({
      'user_id': userId,
      'text': text,
      'channel_name': 'companion',
      'action': 'respond',
    });
    final headers = <String, String>{
      'Content-Type': 'application/json',
    };
    if (_apiKey != null && _apiKey!.isNotEmpty) {
      headers['X-API-Key'] = _apiKey!;
      headers['Authorization'] = 'Bearer $_apiKey';
    }
    final response = await http
        .post(url, headers: headers, body: body)
        .timeout(const Duration(seconds: 120));
    if (response.statusCode != 200) {
      final err = response.body;
      throw Exception('Core returned ${response.statusCode}: $err');
    }
    final map = jsonDecode(response.body) as Map<String, dynamic>?;
    return (map?['text'] as String?) ?? '';
  }
}
