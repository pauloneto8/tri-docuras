import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';
import 'package:tri_docuras_api/admin_orders.dart';

Future<Response> onRequest(RequestContext context) async {
  if (!AdminAuth.isConfigured) {
    return Response.json(
      statusCode: HttpStatus.serviceUnavailable,
      body: {'error': 'Painel admin não configurado.'},
    );
  }

  if (!AdminAuth.isAuthorized(context.request)) {
    return AdminAuth.unauthorized();
  }

  if (context.request.method != HttpMethod.get) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final status = context.request.uri.queryParameters['status'];
  final orders = await listOrdersForAdmin(status: status);
  return Response.json(
    body: {
      'orders': orders
          .map(
            (order) => orderToAdminJson(
              order,
              (order['items'] as List).cast<Map<String, Object?>>(),
            ),
          )
          .toList(),
    },
  );
}
