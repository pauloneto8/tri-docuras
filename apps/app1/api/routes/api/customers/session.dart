import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/customer_auth.dart';
import 'package:tri_docuras_api/customers.dart';
import 'package:tri_docuras_api/rate_limiter.dart';

const _invalidLogin = 'E-mail ou senha incorretos.';

/// Login de cliente. A resposta de erro é a mesma para e-mail inexistente e
/// senha errada.
Future<Response> onRequest(RequestContext context) async {
  if (context.request.method != HttpMethod.post) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  if (!CustomerAuth.isConfigured) {
    return Response.json(
      statusCode: HttpStatus.serviceUnavailable,
      body: {'error': 'Contas indisponíveis no momento.'},
    );
  }

  final limited = rateLimitResponse(customerLoginLimiter, clientIp(context));
  if (limited != null) return limited;

  try {
    final body = await context.request.json() as Map<String, dynamic>;
    final email = CustomerAuth.normalizeEmail(body['email']);
    final password = body['password']?.toString() ?? '';
    if (email == null || password.isEmpty) {
      return _unauthorized();
    }

    final auth = await authenticateCustomer(email, password);
    if (auth == null) return _unauthorized();

    final customer = await getCustomerProfile(auth.id);
    if (customer == null) return _unauthorized();

    final token = CustomerAuth.issueToken(
      customerId: auth.id,
      sessionVersion: auth.sessionVersion,
      now: DateTime.now(),
    );
    return Response.json(body: {'customer': customer, 'token': token});
  } on FormatException {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': 'Corpo da requisição inválido.'},
    );
  }
}

Response _unauthorized() => Response.json(
      statusCode: HttpStatus.unauthorized,
      body: {'error': _invalidLogin},
    );
