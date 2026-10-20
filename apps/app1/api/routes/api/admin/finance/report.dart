import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';
import 'package:tri_docuras_api/finance.dart';

Future<Response> onRequest(RequestContext context) async {
  if (!AdminAuth.isConfigured) {
    return Response.json(
      statusCode: HttpStatus.serviceUnavailable,
      body: {'error': 'Painel admin não configurado.'},
    );
  }

  final session = await AdminAuth.resolve(context.request);
  if (session == null) {
    return AdminAuth.unauthorized();
  }

  if (context.request.method != HttpMethod.get) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final query = context.request.uri.queryParameters;
  try {
    final range = resolveDateRange(from: query['from'], to: query['to']);
    final report = await buildFinanceReport(range: range);
    return Response.json(body: report);
  } on FinanceException catch (error) {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': error.message},
    );
  }
}
