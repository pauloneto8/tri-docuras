import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/order_tracking.dart';
import 'package:tri_docuras_api/orders.dart';

Future<Response> onRequest(RequestContext context, String id) async {
  if (context.request.method != HttpMethod.get) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
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
