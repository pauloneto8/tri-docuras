import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';
import 'package:tri_docuras_api/admin_users.dart';
import 'package:tri_docuras_api/customer_auth.dart';
import 'package:tri_docuras_api/rate_limiter.dart';

Future<Response> onRequest(RequestContext context) async {
  if (context.request.method != HttpMethod.post) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  if (!AdminAuth.isConfigured) {
    return Response.json(
      statusCode: HttpStatus.serviceUnavailable,
      body: {'error': 'Painel admin não configurado.'},
    );
  }

  final limited = rateLimitResponse(loginLimiter, clientIp(context));
  if (limited != null) return limited;

  try {
    final body = await context.request.json() as Map<String, dynamic>;
    final email = body['email']?.toString().trim().toLowerCase() ?? '';
    final password = body['password']?.toString() ?? '';

    if (email.isEmpty) {
      // Modo legado: sem usuários no banco, a senha única ainda abre o painel.
      if (await countAdminUsers() == 0 && AdminAuth.verifyPassword(password)) {
        return Response.json(body: {
          'token': AdminAuth.issueToken(),
          'user': AdminSession.legacyOwner.toJson(),
        });
      }
      return _invalidCredentials();
    }

    final user = await findAdminUserByEmail(email);
    final valid = user != null &&
        user.active &&
        user.passwordHash != null &&
        CustomerAuth.verifyPassword(password, user.passwordHash!);
    if (!valid) return _invalidCredentials();

    await touchAdminLogin(user.id);
    return Response.json(body: {
      'token': AdminAuth.issueToken(
        userId: user.id,
        sessionVersion: user.sessionVersion,
      ),
      'user': AdminSession(
        userId: user.id,
        name: user.name,
        role: user.role,
        email: user.email,
      ).toJson(),
    });
  } on FormatException {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': 'Corpo da requisição inválido.'},
    );
  }
}

Response _invalidCredentials() => Response.json(
      statusCode: HttpStatus.unauthorized,
      body: {'error': 'E-mail ou senha incorretos.'},
    );
