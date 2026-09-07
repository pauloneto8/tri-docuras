import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';
import 'package:tri_docuras_api/admin_products.dart';

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

  if (context.request.method == HttpMethod.get) {
    final products = await listProductsForAdmin();
    return Response.json(
      body: {
        'products': products.map(productToAdminJson).toList(),
        'categories': adminProductCategories,
      },
    );
  }

  if (context.request.method == HttpMethod.post) {
    try {
      final body = await context.request.json() as Map<String, dynamic>;
      final input = parseProductInput(body);
      final product = await createProduct(input);
      return Response.json(statusCode: HttpStatus.created, body: {'product': product});
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

  return Response(statusCode: HttpStatus.methodNotAllowed);
}
