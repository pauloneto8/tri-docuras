import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';
import 'package:tri_docuras_api/admin_products.dart';

Future<Response> onRequest(RequestContext context, String id) async {
  if (!AdminAuth.isConfigured) {
    return Response.json(
      statusCode: HttpStatus.serviceUnavailable,
      body: {'error': 'Painel admin não configurado.'},
    );
  }

  if (!AdminAuth.isAuthorized(context.request)) {
    return AdminAuth.unauthorized();
  }

  if (context.request.method != HttpMethod.put) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final productId = int.tryParse(id.trim());
  if (productId == null || productId <= 0) {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': 'ID de produto inválido.'},
    );
  }

  try {
    final body = await context.request.json() as Map<String, dynamic>;
    final input = parseProductInput(body);
    final product = await updateProduct(productId, input);
    return Response.json(body: {'product': product});
  } on AdminProductException catch (error) {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': error.message},
    );
  } on FormatException {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': 'Corpo da requisição inválido.'},
    );
  }
}
