import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:dart_frog/dart_frog.dart';

/// Validação de assinatura do webhook do Mercado Pago.
///
/// Referência: https://www.mercadopago.com.br/developers/pt/docs/checkout-api/webhooks
///
/// Opt-in: se `APP1_MP_WEBHOOK_SECRET` não estiver configurada, a validação
/// é pulada (retorna `true`) para não quebrar instalações existentes — o
/// endpoint continua protegido porque `syncOrderPaymentFromMercadoPago`
/// sempre reconsulta o status na API oficial antes de confirmar qualquer
/// pedido. Configure a secret no painel do Mercado Pago e em `.env` para
/// ativar a checagem.
class MercadoPagoWebhookSignature {
  static String? get _secret {
    final value = Platform.environment['APP1_MP_WEBHOOK_SECRET'];
    if (value == null || value.trim().isEmpty) return null;
    return value.trim();
  }

  static bool get isConfigured => _secret != null;

  static bool _constantTimeEquals(String a, String b) {
    if (a.length != b.length) return false;
    var diff = 0;
    for (var i = 0; i < a.length; i++) {
      diff |= a.codeUnitAt(i) ^ b.codeUnitAt(i);
    }
    return diff == 0;
  }

  /// Extrai `ts` e `v1` do header `x-signature` (`"ts=...,v1=..."`).
  static Map<String, String> parseSignatureHeader(String header) {
    final parts = <String, String>{};
    for (final segment in header.split(',')) {
      final kv = segment.split('=');
      if (kv.length < 2) continue;
      parts[kv[0].trim()] = kv.sublist(1).join('=').trim();
    }
    return parts;
  }

  static String buildManifest({
    required String dataId,
    required String requestId,
    required String ts,
  }) {
    return 'id:$dataId;request-id:$requestId;ts:$ts;';
  }

  static String sign(String manifest, String secret) {
    final hmac = Hmac(sha256, utf8.encode(secret));
    return hmac.convert(utf8.encode(manifest)).toString();
  }

  /// Retorna `true` se a assinatura for válida OU se a validação estiver
  /// desativada (secret não configurada). Retorna `false` apenas quando a
  /// secret está configurada e a assinatura não bate — nesse caso o
  /// chamador deve rejeitar a requisição.
  static bool verify(RequestContext context, {required String? dataId}) {
    final secret = _secret;
    if (secret == null) return true;

    if (dataId == null || dataId.isEmpty) return false;

    final signatureHeader = context.request.headers['x-signature'];
    final requestId = context.request.headers['x-request-id'];
    if (signatureHeader == null || requestId == null) return false;

    final parsed = parseSignatureHeader(signatureHeader);
    final ts = parsed['ts'];
    final v1 = parsed['v1'];
    if (ts == null || v1 == null) return false;

    final manifest = buildManifest(
      dataId: dataId.toLowerCase(),
      requestId: requestId,
      ts: ts,
    );
    final expected = sign(manifest, secret);
    return _constantTimeEquals(v1, expected);
  }
}
