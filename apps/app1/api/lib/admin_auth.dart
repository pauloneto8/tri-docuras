import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_users.dart';
import 'package:tri_docuras_api/env.dart';

/// Quem está logado no painel `/admin`.
class AdminSession {
  const AdminSession({
    required this.userId,
    required this.name,
    required this.role,
    this.email,
  });

  /// Sessão do modo legado (senha única, antes de existir usuário no banco).
  static const legacyOwner = AdminSession(
    userId: 0,
    name: 'Dono',
    role: 'dono',
  );

  final int userId;
  final String name;
  final String role;
  final String? email;

  bool get isOwner => role == 'dono';

  Map<String, Object?> toJson() => {
        'id': userId,
        'name': name,
        'email': email,
        'role': role,
      };
}

/// Campos assinados no token. `userId` 0 é o modo legado.
class AdminTokenClaims {
  const AdminTokenClaims({
    required this.userId,
    required this.sessionVersion,
  });

  final int userId;
  final int sessionVersion;
}

/// Sessão do painel `/admin`.
///
/// Token: `"<userId>.<versãoDaSessão>.<expiraEmEpoch>.<HMAC-SHA256>"`.
/// A chave é `APP1_ADMIN_SECRET` quando definida; senão, a senha do painel
/// (comportamento anterior). A versão da sessão é conferida no banco em
/// [AdminAuth.resolve], então desativar um usuário ou trocar a senha dele
/// invalida o token na hora.
class AdminAuth {
  AdminAuth._();

  static const _sessionTtl = Duration(hours: 12);

  static String? get password =>
      Env.get('APP1_ADMIN_PASSWORD') ?? Env.get('ADMIN_PASSWORD');

  static String? get _secret => Env.get('APP1_ADMIN_SECRET');

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

  /// Verifica a senha única do modo legado (tempo constante).
  static bool verifyPassword(String candidate) {
    final value = password;
    if (value == null) return false;
    return _constantTimeEquals(candidate, value);
  }

  static String _signingKey() {
    final key = _secret ?? password;
    if (key == null) throw StateError('Admin key not configured');
    return key;
  }

  static String _sign(String payload) {
    final hmac = Hmac(sha256, utf8.encode(_signingKey()));
    return hmac.convert(utf8.encode(payload)).toString();
  }

  static String issueToken({int userId = 0, int sessionVersion = 0}) {
    final expiresAt = DateTime.now().toUtc().add(_sessionTtl);
    final payload =
        '$userId.$sessionVersion.${expiresAt.millisecondsSinceEpoch}';
    return '$payload.${_sign(payload)}';
  }

  /// Confere assinatura e expiração. Não consulta o banco.
  static AdminTokenClaims? verifyToken(String? token) {
    if (!isConfigured || token == null || token.isEmpty) return null;
    final parts = token.split('.');
    if (parts.length != 4) return null;
    final [userIdRaw, versionRaw, expiresRaw, signature] = parts;

    final userId = int.tryParse(userIdRaw);
    final version = int.tryParse(versionRaw);
    final expiresEpoch = int.tryParse(expiresRaw);
    if (userId == null || version == null || expiresEpoch == null) {
      return null;
    }

    final expiresAt = DateTime.fromMillisecondsSinceEpoch(
      expiresEpoch,
      isUtc: true,
    );
    if (DateTime.now().toUtc().isAfter(expiresAt)) return null;

    final payload = '$userIdRaw.$versionRaw.$expiresRaw';
    if (!_constantTimeEquals(signature, _sign(payload))) return null;

    return AdminTokenClaims(userId: userId, sessionVersion: version);
  }

  static String? _bearer(Request request) {
    final auth = request.headers['Authorization'];
    if (auth == null || !auth.startsWith('Bearer ')) return null;
    return auth.substring(7).trim();
  }

  /// Resolve a sessão da requisição consultando o banco. Retorna `null` se o
  /// token for inválido, expirado, de usuário inativo ou de versão antiga.
  static Future<AdminSession?> resolve(Request request) async {
    final claims = verifyToken(_bearer(request));
    if (claims == null) return null;

    if (claims.userId == 0) {
      // Token legado só vale enquanto não existir nenhum usuário no banco.
      return await countAdminUsers() == 0 ? AdminSession.legacyOwner : null;
    }

    final user = await findAdminUserById(claims.userId);
    if (user == null ||
        !user.active ||
        user.sessionVersion != claims.sessionVersion) {
      return null;
    }
    return AdminSession(
      userId: user.id,
      name: user.name,
      role: user.role,
      email: user.email,
    );
  }

  static Response unauthorized() => Response.json(
        statusCode: HttpStatus.unauthorized,
        body: {'error': 'Não autorizado.'},
      );

  static Response forbidden() => Response.json(
        statusCode: HttpStatus.forbidden,
        body: {'error': 'Apenas o dono pode fazer isso.'},
      );
}
