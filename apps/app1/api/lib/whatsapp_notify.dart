import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:postgres/postgres.dart';
import 'package:tri_docuras_api/db.dart';

class WhatsappNotifyConfig {
  static bool get enabled {
    final value = Platform.environment['APP1_WHATSAPP_NOTIFY_ENABLED'] ??
        Platform.environment['WHATSAPP_NOTIFY_ENABLED'];
    if (value == null) return _provider != null;
    final normalized = value.trim().toLowerCase();
    return normalized == 'true' || normalized == '1' || normalized == 'yes';
  }

  static String? get provider {
    final value = Platform.environment['APP1_WHATSAPP_PROVIDER'] ??
        Platform.environment['WHATSAPP_PROVIDER'];
    return value?.trim().toLowerCase();
  }

  static String? get _provider => provider;

  static String? get storeWhatsApp {
    final value = Platform.environment['APP1_STORE_WHATSAPP'] ??
        Platform.environment['STORE_WHATSAPP'];
    if (value == null || value.trim().isEmpty) return null;
    return _normalizePhone(value);
  }

  static String? get callMeBotApiKey {
    final value = Platform.environment['APP1_CALLMEBOT_API_KEY'] ??
        Platform.environment['CALLMEBOT_API_KEY'];
    if (value == null || value.trim().isEmpty) return null;
    return value.trim();
  }

  static String? get metaAccessToken {
    final value = Platform.environment['APP1_WHATSAPP_ACCESS_TOKEN'] ??
        Platform.environment['WHATSAPP_ACCESS_TOKEN'];
    if (value == null || value.trim().isEmpty) return null;
    return value.trim();
  }

  static String? get metaPhoneNumberId {
    final value = Platform.environment['APP1_WHATSAPP_PHONE_NUMBER_ID'] ??
        Platform.environment['WHATSAPP_PHONE_NUMBER_ID'];
    if (value == null || value.trim().isEmpty) return null;
    return value.trim();
  }

  static bool get isConfigured {
    if (!enabled) return false;
    final phone = storeWhatsApp;
    if (phone == null) return false;

    switch (_provider) {
      case 'callmebot':
        return callMeBotApiKey != null;
      case 'meta':
        return metaAccessToken != null && metaPhoneNumberId != null;
      default:
        return false;
    }
  }
}

String buildStorePaidOrderMessage({
  required String publicId,
  required String customerName,
  required String whatsapp,
  required String deliveryLabel,
  required double total,
  required List<String> itemLines,
}) {
  final items = itemLines.isEmpty ? '—' : itemLines.join('\n');
  return [
    '✅ Pagamento confirmado — Tri Doçuras',
    '',
    'Pedido: $publicId',
    'Cliente: $customerName',
    'WhatsApp: $whatsapp',
    'Entrega: $deliveryLabel',
    'Total: ${formatMoneyBrl(total)}',
    '',
    'Itens:',
    items,
    '',
    'Painel: https://tridocuras.com.br/admin',
  ].join('\n');
}

String formatMoneyBrl(double value) {
  return 'R\$ ${value.toStringAsFixed(2).replaceAll('.', ',')}';
}

String _normalizePhone(String raw) {
  final digits = raw.replaceAll(RegExp(r'\D'), '');
  if (digits.startsWith('55') && digits.length >= 12) return digits;
  if (digits.length == 11) return '55$digits';
  return digits;
}

Future<void> notifyStoreOrderPaid(String publicId) async {
  if (!WhatsappNotifyConfig.isConfigured) return;

  final connection = await getConnection();
  final orderResult = await connection.execute(
    '''
    SELECT public_id, customer_name, whatsapp, delivery_mode, total, whatsapp_notified_at
    FROM orders
    WHERE public_id = \$1 AND status = 'paid'
    LIMIT 1;
    ''',
    parameters: [publicId],
  );
  if (orderResult.isEmpty) return;

  final row = orderResult.first;
  if (row[5] != null) return;

  final items = await _fetchItemLines(connection, publicId);
  final deliveryMode = row[3] as String;
  final message = buildStorePaidOrderMessage(
    publicId: row[0] as String,
    customerName: row[1] as String,
    whatsapp: row[2] as String,
    deliveryLabel: deliveryMode == 'pickup' ? 'Retirada' : 'Entrega',
    total: _toDouble(row[4]),
    itemLines: items,
  );

  final sent = await _sendToStore(message);
  if (!sent) return;

  await connection.execute(
    '''
    UPDATE orders SET whatsapp_notified_at = NOW() WHERE public_id = \$1;
    ''',
    parameters: [publicId],
  );
}

Future<List<String>> _fetchItemLines(Connection connection, String publicId) async {
  final result = await connection.execute(
    '''
    SELECT oi.quantity, oi.product_name, oi.line_total
    FROM order_items oi
    JOIN orders o ON o.id = oi.order_id
    WHERE o.public_id = \$1
    ORDER BY oi.id ASC;
    ''',
    parameters: [publicId],
  );

  return result
      .map(
        (row) =>
            '${row[0]}× ${row[1]} — ${formatMoneyBrl(_toDouble(row[2]))}',
      )
      .toList();
}

Future<bool> _sendToStore(String message) async {
  final phone = WhatsappNotifyConfig.storeWhatsApp;
  if (phone == null) return false;

  switch (WhatsappNotifyConfig.provider) {
    case 'callmebot':
      return _sendCallMeBot(phone: phone, message: message);
    case 'meta':
      return _sendMetaCloud(phone: phone, message: message);
    default:
      return false;
  }
}

Future<bool> _sendCallMeBot({
  required String phone,
  required String message,
  http.Client? client,
}) async {
  final apiKey = WhatsappNotifyConfig.callMeBotApiKey;
  if (apiKey == null) return false;

  final httpClient = client ?? http.Client();
  try {
    final uri = Uri.https('api.callmebot.com', '/whatsapp.php', {
      'phone': phone,
      'text': message,
      'apikey': apiKey,
    });
    final response = await httpClient.get(uri);
    return response.statusCode == 200;
  } finally {
    if (client == null) {
      httpClient.close();
    }
  }
}

Future<bool> _sendMetaCloud({
  required String phone,
  required String message,
  http.Client? client,
}) async {
  final token = WhatsappNotifyConfig.metaAccessToken;
  final phoneId = WhatsappNotifyConfig.metaPhoneNumberId;
  if (token == null || phoneId == null) return false;

  final httpClient = client ?? http.Client();
  try {
    final uri = Uri.parse('https://graph.facebook.com/v22.0/$phoneId/messages');
    final response = await httpClient.post(
      uri,
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        'messaging_product': 'whatsapp',
        'to': phone,
        'type': 'text',
        'text': {'body': message},
      }),
    );
    return response.statusCode >= 200 && response.statusCode < 300;
  } finally {
    if (client == null) {
      httpClient.close();
    }
  }
}

double _toDouble(Object? value) => switch (value) {
      final num n => n.toDouble(),
      final String s => double.parse(s),
      _ => 0.0,
    };

// Test helpers
Future<bool> sendCallMeBotMessage({
  required String phone,
  required String message,
  required String apiKey,
  http.Client? client,
}) =>
    _sendCallMeBot(phone: phone, message: message, client: client);

Future<bool> sendMetaWhatsAppMessage({
  required String phone,
  required String message,
  required String accessToken,
  required String phoneNumberId,
  http.Client? client,
}) async {
  final httpClient = client ?? http.Client();
  try {
    final uri = Uri.parse('https://graph.facebook.com/v22.0/$phoneNumberId/messages');
    final response = await httpClient.post(
      uri,
      headers: {
        'Authorization': 'Bearer $accessToken',
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        'messaging_product': 'whatsapp',
        'to': phone,
        'type': 'text',
        'text': {'body': message},
      }),
    );
    return response.statusCode >= 200 && response.statusCode < 300;
  } finally {
    if (client == null) {
      httpClient.close();
    }
  }
}
