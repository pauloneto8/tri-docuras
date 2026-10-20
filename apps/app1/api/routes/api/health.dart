import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/db.dart';

Future<Response> onRequest(RequestContext context) async {
  if (context.request.method != HttpMethod.get) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final dbOk = await pingDatabase();

  // 503 quando o banco cai: o monitor externo precisa ver a falha.
  return Response.json(
    statusCode: dbOk ? HttpStatus.ok : HttpStatus.serviceUnavailable,
    body: {
      'status': dbOk ? 'ok' : 'error',
      'service': 'Tri Doçuras API',
      'database': dbOk ? 'connected' : 'unavailable',
    },
  );
}
