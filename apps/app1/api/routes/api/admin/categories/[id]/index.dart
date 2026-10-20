import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';
import 'package:tri_docuras_api/admin_categories.dart';

Future<Response> onRequest(RequestContext context, String id) async {
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

  final categoryId = int.tryParse(id.trim());
  if (categoryId == null || categoryId <= 0) {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': 'ID de categoria inválido.'},
    );
  }

  if (context.request.method == HttpMethod.put) {
    try {
      final body = await context.request.json() as Map<String, dynamic>;
      final input = parseCategoryInput(body, requireSlug: false);
      final category = await updateCategory(categoryId, input);
      return Response.json(body: {'category': category});
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

  if (context.request.method == HttpMethod.delete) {
    try {
      await deleteCategory(categoryId);
      return Response.json(body: {'deleted': true});
    } on AdminCategoryException catch (error) {
      return Response.json(
        statusCode: HttpStatus.badRequest,
        body: {'error': error.message},
      );
    }
  }

  return Response(statusCode: HttpStatus.methodNotAllowed);
}
