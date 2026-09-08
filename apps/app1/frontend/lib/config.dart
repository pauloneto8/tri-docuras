import 'package:flutter/foundation.dart';

class AppConfig {
  static const String appName = 'Tri Doçuras';
  static const String tagline = 'Doceria online — carro-chefe: brownie artesanal';
  static const String appVersion = '1.0.0';

  /// WhatsApp da loja (apenas dígitos, com DDI 55).
  static const String storeWhatsApp = '5581987654321';
  static const String storeWhatsAppDisplay = '(81) 98765-4321';

  /// Web usa caminho relativo (mesmo domínio do Nginx).
  /// Mobile usa o domínio de produção; altere para dev local se necessário.
  static String get apiBaseUrl {
    if (kIsWeb) {
      return '/api';
    }
    return 'https://tridocuras.com.br/api';
  }

  /// Resolve caminho relativo da API (ex.: `/api/uploads/...`) para URL absoluta no mobile.
  static String? resolveMediaUrl(String? path) {
    if (path == null || path.trim().isEmpty) return null;
    final value = path.trim();
    if (value.startsWith('http://') || value.startsWith('https://')) {
      return value;
    }
    if (kIsWeb) {
      return value.startsWith('/') ? value : '/$value';
    }
    const origin = 'https://tridocuras.com.br';
    return value.startsWith('/') ? '$origin$value' : '$origin/$value';
  }
}
