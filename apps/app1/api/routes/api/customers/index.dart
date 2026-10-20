import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/customer_auth.dart';
import 'package:tri_docuras_api/customers.dart';
import 'package:tri_docuras_api/rate_limiter.dart';

/// Cadastro de cliente.
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

  final limited = rateLimitResponse(customerCreateLimiter, clientIp(context));
  if (limited != null) return limited;

  try {
    final body = await context.request.json() as Map<String, dynamic>;
    final input = parseCustomerInput(body);
    final customer = await createCustomer(input);
    final token = CustomerAuth.issueToken(
      customerId: customer['id']! as int,
      sessionVersion: 0,
      now: DateTime.now(),
    );
    return Response.json(
      statusCode: HttpStatus.created,
      body: {'customer': customer, 'token': token},
    );
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
