import 'package:flutter/foundation.dart';

class AppConfig {
  static const String appName = 'Tri Doçuras';
  static const String tagline = 'Doceria online — carro-chefe: brownie artesanal';

  /// Web usa caminho relativo (mesmo domínio do Nginx).
  /// Mobile usa o domínio de produção; altere para dev local se necessário.
  static String get apiBaseUrl {
    if (kIsWeb) {
      return '/api';
    }
    return 'https://tridocuras.com.br/api';
  }
}
