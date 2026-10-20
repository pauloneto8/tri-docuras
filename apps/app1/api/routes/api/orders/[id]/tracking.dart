import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/customers.dart';
import 'package:tri_docuras_api/order_tracking.dart';
import 'package:tri_docuras_api/orders.dart';
import 'package:tri_docuras_api/tracking_token.dart';

Future<Response> onRequest(RequestContext context, String id) async {
  if (context.request.method != HttpMethod.get) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  // Quem tem o link (`?t=`) acompanha sem login. Sem o token, vale a sessão
  // do dono do pedido. Os dois casos respondem 404 igual a pedido inexistente.
  final order = await getOrderByPublicId(id);
  final byToken = trackingTokenMatches(
    order['tracking_token'] as String?,
    context.request.url.queryParameters['t'],
  );
  if (!byToken &&
      !await customerMayViewOrder(
        id,
        context.request.headers['authorization'],
      )) {
    return Response.json(
      statusCode: HttpStatus.notFound,
      body: {'error': 'Pedido não encontrado.'},
    );
  }

  try {
    final tracking = await getOrderTracking(id);
    return Response.json(body: tracking);
  } on OrderValidationException catch (error) {
    return Response.json(
      statusCode: HttpStatus.notFound,
      body: {'error': error.message},
    );
  }
}
