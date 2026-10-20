import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';

Future<Response> onRequest(RequestContext context) async {
  if (context.request.method != HttpMethod.get) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final session = await AdminAuth.resolve(context.request);
  if (session == null) return AdminAuth.unauthorized();

  return Response.json(body: {'user': session.toJson()});
}
