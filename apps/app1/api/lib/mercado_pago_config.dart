import 'dart:io';

class MercadoPagoConfig {
  static bool get useTest {
    final value = Platform.environment['MP_USE_TEST'] ??
        Platform.environment['APP1_MP_USE_TEST'];
    if (value == null) return false;
    final normalized = value.trim().toLowerCase();
    return normalized == 'true' || normalized == '1' || normalized == 'yes';
  }

  static String? get accessToken {
    if (useTest) {
      final test = Platform.environment['MP_TEST_ACCESS_TOKEN'] ??
          Platform.environment['APP1_MP_TEST_ACCESS_TOKEN'];
      if (test != null && test.trim().isNotEmpty) return test.trim();
    }

    final value = Platform.environment['MP_ACCESS_TOKEN'] ??
        Platform.environment['APP1_MP_ACCESS_TOKEN'];
    if (value == null || value.trim().isEmpty) return null;
    return value.trim();
  }

  static String? get publicKey {
    if (useTest) {
      final test = Platform.environment['MP_TEST_PUBLIC_KEY'] ??
          Platform.environment['APP1_MP_TEST_PUBLIC_KEY'];
      if (test != null && test.trim().isNotEmpty) return test.trim();
    }

    final value = Platform.environment['MP_PUBLIC_KEY'] ??
        Platform.environment['APP1_MP_PUBLIC_KEY'];
    if (value == null || value.trim().isEmpty) return null;
    return value.trim();
  }

  static String get notificationUrl {
    final explicit = Platform.environment['MP_NOTIFICATION_URL'] ??
        Platform.environment['APP1_MP_NOTIFICATION_URL'];
    if (explicit != null && explicit.trim().isNotEmpty) {
      return explicit.trim();
    }
    final domain = Platform.environment['APP1_PUBLIC_URL'] ??
        Platform.environment['APP1_DOMAIN'];
    if (domain != null && domain.trim().isNotEmpty) {
      final host = domain.trim();
      final withScheme = host.startsWith('http') ? host : 'https://$host';
      return '$withScheme/api/webhooks/mercadopago';
    }
    return 'https://tridocuras.com.br/api/webhooks/mercadopago';
  }

  static bool get isConfigured => accessToken != null;

  static Map<String, Object?> enrichPixPayload(Map<String, Object?> pix) {
    return {
      ...pix,
      'mp_mode': useTest ? 'test' : 'production',
    };
  }
}
