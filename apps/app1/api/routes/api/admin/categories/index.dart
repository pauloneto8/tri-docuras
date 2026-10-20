import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';
import 'package:tri_docuras_api/admin_categories.dart';

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

  if (context.request.method == HttpMethod.get) {
    final categories = await listCategoriesForAdmin();
    return Response.json(
      body: {
        'categories': categories.map(categoryToAdminJson).toList(),
      },
    );
  }

  if (context.request.method == HttpMethod.post) {
    try {
      final body = await context.request.json() as Map<String, dynamic>;
      final input = parseCategoryInput(body);
      final category = await createCategory(input);
      return Response.json(
        statusCode: HttpStatus.created,
        body: {'category': category},
      );
    } on AdminCategoryException catch (error) {
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
