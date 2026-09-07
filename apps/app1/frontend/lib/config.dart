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
}
