import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/customers.dart';

/// Pedidos do cliente logado, mais recentes primeiro.
Future<Response> onRequest(RequestContext context) async {
  if (context.request.method != HttpMethod.get) {
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

  final orders = await listCustomerOrders(session.customerId);
  return Response.json(body: {'orders': orders});
}
