import 'dart:convert';
import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/mercado_pago_webhook.dart';
import 'package:tri_docuras_api/orders.dart';

Future<Response> onRequest(RequestContext context) async {
  if (context.request.method == HttpMethod.get) {
    return _handleLegacyIpn(context);
  }
  if (context.request.method == HttpMethod.post) {
    return _handleWebhook(context);
  }
  return Response(statusCode: HttpStatus.methodNotAllowed);
}

Response _invalidSignature(String? dataId) {
  stderr.writeln('[mp] webhook rejeitado: assinatura inválida (data.id=$dataId)');
  return Response.json(
    statusCode: HttpStatus.unauthorized,
    body: {'error': 'Assinatura inválida.'},
  );
}

Future<Response> _handleLegacyIpn(RequestContext context) async {
  final rawId = context.request.uri.queryParameters['id'] ??
      context.request.uri.queryParameters['data.id'];
  final paymentId = _parsePaymentId(rawId);
  if (paymentId == null) {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': 'Notificação inválida.'},
    );
  }

  if (!MercadoPagoWebhookSignature.verify(context, dataId: rawId)) {
    return _invalidSignature(rawId);
  }

  try {
    final updated = await syncOrderPaymentFromMercadoPago(paymentId);
    return Response.json(body: {'processed': updated, 'payment_id': paymentId});
  } catch (error) {
    // Responde 200 para o MP não reenviar em loop; a reconsulta do polling
    // do app cobre o pedido. O log é o único sinal da falha.
    stderr.writeln('[mp] webhook: falha ao processar pagamento $paymentId: $error');
    return Response.json(
      statusCode: HttpStatus.ok,
      body: {'processed': false, 'payment_id': paymentId},
    );
  }
}

Future<Response> _handleWebhook(RequestContext context) async {
  int? paymentId;
  try {
    final bodyText = await context.request.body();
    if (bodyText.isEmpty) {
      return await _handleLegacyIpn(context);
    }

    final body = jsonDecode(bodyText);
    paymentId = _extractPaymentIdFromBody(body);
    if (paymentId == null) {
      stderr.writeln('[mp] webhook sem ID de pagamento: $bodyText');
      return Response.json(body: {'processed': false});
    }

    // A assinatura é calculada sobre o `data.id` da query string (padrão
    // Mercado Pago), com fallback pro id extraído do corpo quando ausente.
    final dataId =
        context.request.uri.queryParameters['data.id'] ?? paymentId.toString();
    if (!MercadoPagoWebhookSignature.verify(context, dataId: dataId)) {
      return _invalidSignature(dataId);
    }

    final updated = await syncOrderPaymentFromMercadoPago(paymentId);
    return Response.json(body: {'processed': updated, 'payment_id': paymentId});
  } catch (error) {
    stderr.writeln('[mp] webhook: falha ao processar pagamento $paymentId: $error');
    return Response.json(
      statusCode: HttpStatus.ok,
      body: {'processed': false},
    );
  }
}

int? _parsePaymentId(String? raw) {
  if (raw == null || raw.trim().isEmpty) return null;
  return int.tryParse(raw.trim());
}

int? _extractPaymentIdFromBody(Object? body) {
  if (body is Map) {
    final data = body['data'];
    if (data is Map && data['id'] != null) {
      return _parsePaymentId(data['id'].toString());
    }
    if (body['id'] != null) {
      return _parsePaymentId(body['id'].toString());
    }
  }
  return null;
}
