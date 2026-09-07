import 'dart:convert';
import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
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

Future<Response> _handleLegacyIpn(RequestContext context) async {
  final paymentId = _parsePaymentId(
    context.request.uri.queryParameters['id'] ??
        context.request.uri.queryParameters['data.id'],
  );
  if (paymentId == null) {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': 'Notificação inválida.'},
    );
  }

  try {
    final updated = await syncOrderPaymentFromMercadoPago(paymentId);
    return Response.json(body: {'processed': updated, 'payment_id': paymentId});
  } catch (_) {
    return Response.json(
      statusCode: HttpStatus.ok,
      body: {'processed': false, 'payment_id': paymentId},
    );
  }
}

Future<Response> _handleWebhook(RequestContext context) async {
  try {
    final bodyText = await context.request.body();
    if (bodyText.isEmpty) {
      return _handleLegacyIpn(context);
    }

    final body = jsonDecode(bodyText);
    final paymentId = _extractPaymentIdFromBody(body);
    if (paymentId == null) {
      return Response.json(body: {'processed': false});
    }

    final updated = await syncOrderPaymentFromMercadoPago(paymentId);
    return Response.json(body: {'processed': updated, 'payment_id': paymentId});
  } catch (_) {
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
