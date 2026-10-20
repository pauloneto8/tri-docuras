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

  final session = await AdminAuth.resolve(context.request);
  if (session == null) {
    return AdminAuth.unauthorized();
  }

  if (context.request.method != HttpMethod.get) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final query = context.request.uri.queryParameters;
  try {
    final orders = await listOrdersForAdmin(
      status: query['status'],
      search: query['search'],
      from: query['from'],
      to: query['to'],
    );
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
  } on AdminOrderException catch (error) {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': error.message},
    );
  }
}
