import 'dart:convert';

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
  MercadoPagoClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  static const _baseUrl = 'https://api.mercadopago.com';

  Future<PixChargeResult> createPixPayment({
    required String orderPublicId,
    required double amount,
    required String customerName,
    required String whatsapp,
    Duration expiry = const Duration(minutes: 10),
  }) async {
    final token = MercadoPagoConfig.accessToken;
    if (token == null) {
      throw MercadoPagoException(
        'Pagamento Pix indisponível: credencial Mercado Pago não configurada.',
      );
    }

    final nameParts = _splitName(customerName);
    final expiresAt = DateTime.now().toUtc().add(expiry);

    final body = {
      'transaction_amount': double.parse(amount.toStringAsFixed(2)),
      'description': 'Pedido Tri Doçuras $orderPublicId',
      'payment_method_id': 'pix',
      'external_reference': orderPublicId,
      'notification_url': MercadoPagoConfig.notificationUrl,
      'date_of_expiration': _formatMpDate(expiresAt),
      'payer': {
        'email': _payerEmail(orderPublicId, whatsapp),
        'first_name': nameParts.first,
        'last_name': nameParts.last,
      },
    };

    final response = await _client.post(
      Uri.parse('$_baseUrl/v1/payments'),
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
        'X-Idempotency-Key': '$orderPublicId-${expiresAt.millisecondsSinceEpoch}',
      },
      body: jsonEncode(body),
    );

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
    final token = MercadoPagoConfig.accessToken;
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

  static ({String first, String last}) _splitName(String fullName) {
    final parts = fullName.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty) return (first: 'Cliente', last: 'Tri');
    if (parts.length == 1) return (first: parts.first, last: 'Doçuras');
    return (first: parts.first, last: parts.sublist(1).join(' '));
  }
}

bool mercadoPagoStatusIsPaid(String? status) {
  final normalized = status?.toLowerCase().trim();
  return normalized == 'approved' || normalized == 'authorized';
}
