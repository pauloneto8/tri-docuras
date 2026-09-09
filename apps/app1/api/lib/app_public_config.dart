import 'dart:io';

class AppPublicConfig {
  static String get appName =>
      Platform.environment['APP1_APP_NAME']?.trim().isNotEmpty == true
          ? Platform.environment['APP1_APP_NAME']!.trim()
          : 'Tri Doçuras';

  static String? get storeWhatsApp {
    final value = Platform.environment['APP1_STORE_WHATSAPP'] ??
        Platform.environment['STORE_WHATSAPP'];
    if (value == null || value.trim().isEmpty) return null;
    return _normalizePhone(value);
  }

  static String? get storeWhatsAppDisplay {
    final explicit = Platform.environment['APP1_STORE_WHATSAPP_DISPLAY'];
    if (explicit != null && explicit.trim().isNotEmpty) {
      return explicit.trim();
    }
    return _formatDisplay(storeWhatsApp);
  }

  static Map<String, Object?> toJson() {
    return {
      'app_name': appName,
      if (storeWhatsApp != null) 'store_whatsapp': storeWhatsApp,
      if (storeWhatsAppDisplay != null)
        'store_whatsapp_display': storeWhatsAppDisplay,
    };
  }

  static String? _formatDisplay(String? digits) {
    if (digits == null) return null;
    final local = digits.startsWith('55') ? digits.substring(2) : digits;
    if (local.length != 11) return digits;
    return '(${local.substring(0, 2)}) ${local.substring(2, 7)}-${local.substring(7)}';
  }

  static String _normalizePhone(String raw) {
    final digits = raw.replaceAll(RegExp(r'\D'), '');
    if (digits.startsWith('55') && digits.length >= 12) return digits;
    if (digits.length == 11) return '55$digits';
    return digits;
  }
}

String buildCustomerStoreWhatsAppUrl({
  required String storeWhatsApp,
  required String orderId,
  required String customerName,
  required String formattedTotal,
}) {
  final message = [
    'Olá! Acabei de pagar o pedido $orderId.',
    'Nome: $customerName',
    'Total: $formattedTotal',
    'Tri Doçuras',
  ].join('\n');

  return Uri(
    scheme: 'https',
    host: 'wa.me',
    path: storeWhatsApp,
    queryParameters: {'text': message},
  ).toString();
}
