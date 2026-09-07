import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/orders.dart';

Future<Response> onRequest(RequestContext context, String id) async {
  if (context.request.method != HttpMethod.get) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final order = await getOrderByPublicId(id);
  if (order.isEmpty) {
    return Response.json(
      statusCode: HttpStatus.notFound,
      body: {'error': 'Pedido não encontrado.'},
    );
  }

  return Response.json(body: {'order': orderToPublicJson(order)});
}
