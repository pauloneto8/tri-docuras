import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/customer_auth.dart';
import 'package:tri_docuras_api/customers.dart';
import 'package:tri_docuras_api/rate_limiter.dart';

/// Troca de senha. Exige a senha atual e devolve um token novo: a troca
/// derruba as sessões antigas, inclusive esta.
Future<Response> onRequest(RequestContext context) async {
  if (context.request.method != HttpMethod.post) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final session = await resolveCustomerSession(
    context.request.headers['authorization'],
  );
  if (session == null) {
    return Response.json(
      statusCode: HttpStatus.unauthorized,
      body: {'error': 'Entre na sua conta para continuar.'},
    );
  }

  // Limita tentativas de adivinhar a senha atual, por conta.
  final limited = rateLimitResponse(
    customerLoginLimiter,
    'senha:${session.customerId}',
  );
  if (limited != null) return limited;

  try {
    final body = await context.request.json() as Map<String, dynamic>;
    final newPassword = body['new_password']?.toString() ?? '';
    final problem = CustomerAuth.passwordProblem(newPassword);
    if (problem != null) {
      return Response.json(
        statusCode: HttpStatus.badRequest,
        body: {'error': problem},
      );
    }

    final version = await changeCustomerPassword(
      session.customerId,
      currentPassword: body['current_password']?.toString() ?? '',
      newPassword: newPassword,
    );
    final token = CustomerAuth.issueToken(
      customerId: session.customerId,
      sessionVersion: version,
      now: DateTime.now(),
    );
    return Response.json(body: {'token': token});
  } on CustomerException catch (error) {
    return Response.json(
      statusCode: error.statusCode,
      body: {'error': error.message},
    );
  } on FormatException {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': 'Corpo da requisição inválido.'},
    );
  }
}
