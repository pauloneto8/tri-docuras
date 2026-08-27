import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/db.dart';

Future<Response> onRequest(RequestContext context) async {
  if (context.request.method != HttpMethod.get) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final dbOk = await pingDatabase();

  return Response.json(
    body: {
      'status': 'ok',
      'service': 'Tri Doçuras API',
      'database': dbOk ? 'connected' : 'unavailable',
    },
  );
}
