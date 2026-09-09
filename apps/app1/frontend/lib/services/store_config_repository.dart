import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:tri_docuras/config.dart';
import 'package:tri_docuras/models/store_config.dart';

class StoreConfigRepository {
  StoreConfigRepository({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  Future<StoreConfig> fetch() async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}/config');
    final response = await _client.get(uri);
    if (response.statusCode != 200) {
      return StoreConfigFallback.fallback;
    }

    try {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      return StoreConfig.fromJson(body);
    } on FormatException {
      return StoreConfigFallback.fallback;
    }
  }
}

extension StoreConfigFallback on StoreConfig {
  static StoreConfig get fallback => StoreConfig(
        appName: AppConfig.appName,
        storeWhatsApp: AppConfig.storeWhatsApp,
        storeWhatsAppDisplay: AppConfig.storeWhatsAppDisplay,
      );
}
