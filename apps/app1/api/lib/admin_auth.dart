import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/env.dart';

/// Sessão do painel `/admin`.
///
/// O token de sessão NÃO é mais a senha codificada em base64 (reversível
/// trivialmente): é `"<expiraEmEpoch>.<assinaturaHMAC-SHA256>"`, assinado com
/// a senha do admin como chave. Expira sozinho e não expõe a senha caso
/// vaze (XSS, log, etc.).
class AdminAuth {
  static const _sessionTtl = Duration(hours: 12);

  static String? get password =>
      Env.get('APP1_ADMIN_PASSWORD') ?? Env.get('ADMIN_PASSWORD');

  static bool get isConfigured => password != null;

  /// Compara duas strings em tempo constante (evita timing attack).
  static bool _constantTimeEquals(String a, String b) {
    if (a.length != b.length) return false;
    var diff = 0;
    for (var i = 0; i < a.length; i++) {
      diff |= a.codeUnitAt(i) ^ b.codeUnitAt(i);
    }
    return diff == 0;
  }

  /// Verifica a senha informada no login contra a configurada (tempo
  /// constante, para não vazar por timing quantos caracteres acertaram).
  static bool verifyPassword(String candidate) {
    final value = password;
    if (value == null) return false;
    return _constantTimeEquals(candidate, value);
  }

  static String _sign(String payload, String key) {
    final hmac = Hmac(sha256, utf8.encode(key));
    return hmac.convert(utf8.encode(payload)).toString();
  }

  static String issueToken() {
    final value = password;
    if (value == null) {
      throw StateError('Admin password not configured');
    }
    final expiresAt = DateTime.now().toUtc().add(_sessionTtl);
    final expiresEpoch = expiresAt.millisecondsSinceEpoch.toString();
    final signature = _sign(expiresEpoch, value);
    return '$expiresEpoch.$signature';
  }

  static bool verifyToken(String? token) {
    final value = password;
    if (value == null || token == null || token.isEmpty) return false;

    final separatorIndex = token.lastIndexOf('.');
    if (separatorIndex <= 0 || separatorIndex == token.length - 1) {
      return false;
    }

    final expiresEpochRaw = token.substring(0, separatorIndex);
    final signature = token.substring(separatorIndex + 1);

    final expiresEpoch = int.tryParse(expiresEpochRaw);
    if (expiresEpoch == null) return false;

    final expiresAt = DateTime.fromMillisecondsSinceEpoch(
      expiresEpoch,
      isUtc: true,
    );
    if (DateTime.now().toUtc().isAfter(expiresAt)) return false;

    final expectedSignature = _sign(expiresEpochRaw, value);
    return _constantTimeEquals(signature, expectedSignature);
  }

  static bool isAuthorized(Request request) {
    final auth = request.headers['Authorization'];
    if (auth == null || !auth.startsWith('Bearer ')) return false;
    return verifyToken(auth.substring(7).trim());
  }

  static Response unauthorized() => Response.json(
        statusCode: HttpStatus.unauthorized,
        body: {'error': 'Não autorizado.'},
      );
}
