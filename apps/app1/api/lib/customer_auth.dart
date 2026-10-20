import 'dart:convert';

import 'package:bcrypt/bcrypt.dart';
import 'package:crypto/crypto.dart';
import 'package:tri_docuras_api/env.dart';

/// Sessão de cliente já validada na assinatura. A versão precisa ser
/// conferida no banco (`session_version`) pelo chamador: trocar a senha
/// incrementa a versão e invalida os tokens antigos.
class CustomerSession {
  CustomerSession({required this.customerId, required this.sessionVersion});

  final int customerId;
  final int sessionVersion;
}

/// Autenticação de cliente: senha em bcrypt e token HMAC com chave própria
/// (`APP1_CUSTOMER_SECRET`). Não reaproveita a senha do painel nem a do MP.
class CustomerAuth {
  CustomerAuth._();

  static const tokenTtl = Duration(days: 30);
  static const minPasswordLength = 8;

  /// bcrypt só usa os 72 primeiros bytes; o limite é explícito para não
  /// aceitar uma senha que seria truncada em silêncio.
  static const maxPasswordBytes = 72;

  static String? get _secret => Env.get('APP1_CUSTOMER_SECRET');

  static bool get isConfigured => _secret != null;

  /// Hash bcrypt. [rounds] é ajustável só para os testes ficarem rápidos.
  static String hashPassword(String password, {int rounds = 12}) {
    return BCrypt.hashpw(password, BCrypt.gensalt(logRounds: rounds));
  }

  static bool verifyPassword(String password, String hash) {
    try {
      return BCrypt.checkpw(password, hash);
    } catch (_) {
      return false;
    }
  }

  static String? _dummyHash;

  /// Usado quando o e-mail não existe, para o tempo de resposta do login
  /// não revelar que a conta não existe.
  static String get dummyHash =>
      _dummyHash ??= hashPassword('nao-e-uma-senha-real', rounds: 12);

  /// Mensagem de erro, ou `null` se a senha é aceitável.
  static String? passwordProblem(String password) {
    if (password.length < minPasswordLength) {
      return 'A senha precisa ter pelo menos $minPasswordLength caracteres.';
    }
    if (utf8.encode(password).length > maxPasswordBytes) {
      return 'A senha é longa demais.';
    }
    return null;
  }

  static final _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

  /// E-mail em minúsculas e sem espaços, ou `null` se for inválido.
  static String? normalizeEmail(Object? raw) {
    final value = raw?.toString().trim().toLowerCase() ?? '';
    if (value.length > 254 || !_emailPattern.hasMatch(value)) return null;
    return value;
  }

  static String issueToken({
    required int customerId,
    required int sessionVersion,
    required DateTime now,
  }) {
    final secret = _secret;
    if (secret == null) {
      throw StateError('APP1_CUSTOMER_SECRET não configurada.');
    }
    final expiresEpoch =
        now.toUtc().add(tokenTtl).millisecondsSinceEpoch.toString();
    final payload = '$customerId.$sessionVersion.$expiresEpoch';
    return '$payload.${_sign(payload, secret)}';
  }

  /// Sessão válida na assinatura e dentro do prazo, ou `null`.
  static CustomerSession? parseToken(String? token, DateTime now) {
    final secret = _secret;
    if (secret == null || token == null || token.isEmpty) return null;

    final parts = token.split('.');
    if (parts.length != 4) return null;

    final payload = '${parts[0]}.${parts[1]}.${parts[2]}';
    if (!_constantTimeEquals(parts[3], _sign(payload, secret))) return null;

    final customerId = int.tryParse(parts[0]);
    final sessionVersion = int.tryParse(parts[1]);
    final expiresEpoch = int.tryParse(parts[2]);
    if (customerId == null || sessionVersion == null || expiresEpoch == null) {
      return null;
    }
    final expiresAt = DateTime.fromMillisecondsSinceEpoch(
      expiresEpoch,
      isUtc: true,
    );
    if (now.toUtc().isAfter(expiresAt)) return null;

    return CustomerSession(
      customerId: customerId,
      sessionVersion: sessionVersion,
    );
  }

  /// Extrai o token de `Authorization: Bearer <token>`.
  static String? bearerToken(String? header) {
    if (header == null) return null;
    const prefix = 'Bearer ';
    if (!header.startsWith(prefix)) return null;
    final token = header.substring(prefix.length).trim();
    return token.isEmpty ? null : token;
  }

  static String _sign(String payload, String secret) {
    final hmac = Hmac(sha256, utf8.encode(secret));
    return hmac.convert(utf8.encode(payload)).toString();
  }

  static bool _constantTimeEquals(String a, String b) {
    if (a.length != b.length) return false;
    var diff = 0;
    for (var i = 0; i < a.length; i++) {
      diff |= a.codeUnitAt(i) ^ b.codeUnitAt(i);
    }
    return diff == 0;
  }
}

/// Um pedido com cliente só pode ser visto pelo próprio cliente. Pedidos
/// antigos, sem conta (`orderCustomerId == null`), seguem públicos como
/// antes: o WhatsApp não é prova de identidade, então não são vinculados.
bool canAccessOrder({
  required int? orderCustomerId,
  required int? sessionCustomerId,
}) {
  if (orderCustomerId == null) return true;
  return sessionCustomerId == orderCustomerId;
}
