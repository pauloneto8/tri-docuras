import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/customers.dart';

/// Exportação dos dados do cliente logado (GET). Só o próprio cliente recebe.
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

  final export = await buildCustomerExport(session.customerId);
  if (export == null) {
    return Response.json(
      statusCode: HttpStatus.unauthorized,
      body: {'error': 'Entre na sua conta para continuar.'},
    );
  }
  return Response.json(body: export);
}
