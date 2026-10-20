import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';
import 'package:tri_docuras_api/order_events.dart';

Future<Response> onRequest(RequestContext context, String id) async {
  if (context.request.method != HttpMethod.get) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final session = await AdminAuth.resolve(context.request);
  if (session == null) return AdminAuth.unauthorized();

  final events = await listOrderEvents(id);
  if (events == null) {
    return Response.json(
      statusCode: HttpStatus.notFound,
      body: {'error': 'Pedido não encontrado.'},
    );
  }
  return Response.json(body: {'events': events});
}
