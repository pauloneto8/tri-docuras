import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:tri_docuras_api/mercado_pago_config.dart';

class MercadoPagoException implements Exception {
  MercadoPagoException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class PixChargeResult {
  PixChargeResult({
    required this.paymentId,
    required this.copyCode,
    required this.qrCodeBase64,
    required this.expiresAt,
    required this.status,
  });

  final int paymentId;
  final String copyCode;
  final String qrCodeBase64;
  final DateTime expiresAt;
  final String status;

  Map<String, Object?> toJson() => {
        'payment_id': paymentId,
        'copy_code': copyCode,
        'qr_code_base64': qrCodeBase64,
        'expires_at': expiresAt.toUtc().toIso8601String(),
        'status': status,
      };

  factory PixChargeResult.fromStored({
    required int paymentId,
    required String copyCode,
    required String qrCodeBase64,
    required DateTime expiresAt,
    required String status,
  }) =>
      PixChargeResult(
        paymentId: paymentId,
        copyCode: copyCode,
        qrCodeBase64: qrCodeBase64,
        expiresAt: expiresAt,
        status: status,
      );
}

class MercadoPagoClient {
  MercadoPagoClient({http.Client? client, String? accessToken})
      : _client = client ?? http.Client(),
        _accessToken = accessToken;

  final http.Client _client;
  final String? _accessToken;

  static const _baseUrl = 'https://api.mercadopago.com';

  Future<PixChargeResult> createPixPayment({
    required String orderPublicId,
    required double amount,
    required String customerName,
    required String whatsapp,
    String? payerEmail,
    List<PixItem> items = const [],
    Duration expiry = const Duration(minutes: 10),
  }) async {
    final token = _accessToken ?? MercadoPagoConfig.accessToken;
    if (token == null) {
      throw MercadoPagoException(
        'Pagamento Pix indisponível: credencial Mercado Pago não configurada.',
      );
    }

    final expiresAt = DateTime.now().toUtc().add(expiry);
    final body = buildPixBody(
      orderPublicId: orderPublicId,
      amount: amount,
      customerName: customerName,
      whatsapp: whatsapp,
      payerEmail: payerEmail,
      items: items,
      notificationUrl: MercadoPagoConfig.notificationUrl,
      expiresAt: expiresAt,
    );

    Future<http.Response> send(Map<String, Object?> payload, String key) {
      return _client.post(
        Uri.parse('$_baseUrl/v1/payments'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
          'X-Idempotency-Key': key,
        },
        body: jsonEncode(payload),
      );
    }

    final key = '$orderPublicId-${expiresAt.millisecondsSinceEpoch}';
    var response = await send(body, key);
    // Rede de segurança: se o Mercado Pago recusar os dados extras do
    // comprador, o Pix ainda sai com os dados básicos. O log mostra o motivo.
    if (response.statusCode == 400 && body.containsKey('additional_info')) {
      stderr.writeln(
        '[mp] Pix de $orderPublicId recusado com additional_info, '
        'tentando sem: ${response.body}',
      );
      response = await send(
        Map.of(body)..remove('additional_info'),
        '$key-basico',
      );
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw MercadoPagoException(
        _parseErrorMessage(response.body) ??
            'Mercado Pago retornou erro ${response.statusCode}.',
        statusCode: response.statusCode,
      );
    }

    final data = jsonDecode(response.body) as Map<String, dynamic>;
    return _parsePixResponse(data, fallbackExpiry: expiresAt);
  }

  Future<Map<String, dynamic>> fetchPayment(int paymentId) async {
    final token = _accessToken ?? MercadoPagoConfig.accessToken;
    if (token == null) {
      throw MercadoPagoException('Credencial Mercado Pago não configurada.');
    }

    final response = await _client.get(
      Uri.parse('$_baseUrl/v1/payments/$paymentId'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw MercadoPagoException(
        'Não foi possível consultar pagamento $paymentId.',
        statusCode: response.statusCode,
      );
    }

    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// Estorno total do pagamento. [idempotencyKey] faz uma nova tentativa do
  /// mesmo pedido devolver o resultado do estorno já feito, sem estornar 2x.
  Future<Map<String, dynamic>> refundPayment(
    int paymentId, {
    required String idempotencyKey,
  }) async {
    final token = _accessToken ?? MercadoPagoConfig.accessToken;
    if (token == null) {
      throw MercadoPagoException('Credencial Mercado Pago não configurada.');
    }

    final response = await _client.post(
      Uri.parse('$_baseUrl/v1/payments/$paymentId/refunds'),
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
        'X-Idempotency-Key': idempotencyKey,
      },
      body: '{}',
    );

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw MercadoPagoException(
        _parseErrorMessage(response.body) ??
            'Mercado Pago retornou erro ${response.statusCode} no estorno.',
        statusCode: response.statusCode,
      );
    }

    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  PixChargeResult _parsePixResponse(
    Map<String, dynamic> data, {
    required DateTime fallbackExpiry,
  }) {
    final paymentId = (data['id'] as num?)?.toInt();
    if (paymentId == null) {
      throw MercadoPagoException('Resposta inválida do Mercado Pago.');
    }

    final poi = data['point_of_interaction'] as Map<String, dynamic>?;
    final txData = poi?['transaction_data'] as Map<String, dynamic>?;
    final copyCode = txData?['qr_code'] as String?;
    final qrBase64 = txData?['qr_code_base64'] as String?;
    if (copyCode == null || copyCode.isEmpty) {
      throw MercadoPagoException('Mercado Pago não retornou código Pix.');
    }

    final expirationRaw = data['date_of_expiration'] as String?;
    final expiresAt = expirationRaw != null
        ? DateTime.tryParse(expirationRaw)?.toUtc() ?? fallbackExpiry
        : fallbackExpiry;

    return PixChargeResult(
      paymentId: paymentId,
      copyCode: copyCode,
      qrCodeBase64: qrBase64 ?? '',
      expiresAt: expiresAt,
      status: data['status']?.toString() ?? 'pending',
    );
  }

  String? _parseErrorMessage(String body) {
    try {
      final data = jsonDecode(body) as Map<String, dynamic>;
      final message = data['message'] as String?;
      if (message != null && message.isNotEmpty) return message;
      final cause = data['cause'];
      if (cause is List && cause.isNotEmpty) {
        final first = cause.first;
        if (first is Map && first['description'] != null) {
          return first['description'].toString();
        }
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  static String _formatMpDate(DateTime value) {
    final utc = value.toUtc();
    // Mercado Pago exige offset explícito, ex.: 2020-05-30T23:59:59.000-03:00
    const brOffset = Duration(hours: 3);
    final br = utc.subtract(brOffset);
    final y = br.year.toString().padLeft(4, '0');
    final m = br.month.toString().padLeft(2, '0');
    final d = br.day.toString().padLeft(2, '0');
    final h = br.hour.toString().padLeft(2, '0');
    final min = br.minute.toString().padLeft(2, '0');
    final s = br.second.toString().padLeft(2, '0');
    return '$y-$m-${d}T$h:$min:$s.000-03:00';
  }

  static String _payerEmail(String orderPublicId, String whatsapp) {
    final slug = orderPublicId.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');
    return 'pedido+$slug+$whatsapp@pagador.tridocuras.com.br';
  }

  /// Corpo do POST /v1/payments. Manda os dados reais do comprador (e-mail da
  /// conta, nome, telefone) e os itens: a análise antifraude do Mercado Pago
  /// usa esses dados, e um e-mail inventado aumenta a chance de recusa.
  static Map<String, Object?> buildPixBody({
    required String orderPublicId,
    required double amount,
    required String customerName,
    required String whatsapp,
    required String? payerEmail,
    required List<PixItem> items,
    required String notificationUrl,
    required DateTime expiresAt,
  }) {
    final nameParts = _splitName(customerName);
    final email = payerEmail?.trim() ?? '';
    final phone = _phone(whatsapp);
    return {
      'transaction_amount': double.parse(amount.toStringAsFixed(2)),
      'description': 'Pedido Tri Doçuras $orderPublicId',
      'payment_method_id': 'pix',
      'external_reference': orderPublicId,
      'notification_url': notificationUrl,
      'date_of_expiration': _formatMpDate(expiresAt),
      'payer': {
        // Pedido antigo, sem conta, não tem e-mail: mantém o sintético.
        'email': email.isNotEmpty ? email : _payerEmail(orderPublicId, whatsapp),
        'first_name': nameParts.first,
        'last_name': nameParts.last,
      },
      'additional_info': {
        if (items.isNotEmpty) 'items': [for (final item in items) item.toJson()],
        'payer': {
          'first_name': nameParts.first,
          'last_name': nameParts.last,
          if (phone != null) 'phone': phone,
        },
      },
    };
  }

  /// WhatsApp com DDD (11 dígitos) no formato do Mercado Pago.
  static Map<String, String>? _phone(String whatsapp) {
    final digits = whatsapp.replaceAll(RegExp(r'\D'), '');
    if (digits.length != 11) return null;
    return {'area_code': digits.substring(0, 2), 'number': digits.substring(2)};
  }

  static ({String first, String last}) _splitName(String fullName) {
    final parts = fullName.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty) return (first: 'Cliente', last: 'Tri');
    if (parts.length == 1) return (first: parts.first, last: 'Doçuras');
    return (first: parts.first, last: parts.sublist(1).join(' '));
  }
}

/// Item do pedido mandado ao Mercado Pago em `additional_info.items`.
class PixItem {
  const PixItem({
    required this.productId,
    required this.title,
    required this.quantity,
    required this.unitPrice,
  });

  final int productId;
  final String title;
  final int quantity;
  final double unitPrice;

  Map<String, Object?> toJson() => {
        'id': '$productId',
        'title': title,
        'quantity': quantity,
        'unit_price': double.parse(unitPrice.toStringAsFixed(2)),
      };
}

/// O Mercado Pago recusou o pagamento (ex.: `rejected_high_risk`). Se o
/// cliente já tinha pago, o próprio Mercado Pago devolve o valor.
bool mercadoPagoStatusIsRejected(String? status) {
  return status?.toLowerCase().trim() == 'rejected';
}

bool mercadoPagoStatusIsPaid(String? status) {
  final normalized = status?.toLowerCase().trim();
  return normalized == 'approved' || normalized == 'authorized';
}
