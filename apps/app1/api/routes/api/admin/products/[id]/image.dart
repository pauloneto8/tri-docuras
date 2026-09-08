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

  if (context.request.method != HttpMethod.post) {
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
    final formData = await context.request.formData();
    final image = formData.files['image'];
    if (image == null) {
      return Response.json(
        statusCode: HttpStatus.badRequest,
        body: {'error': 'Nenhuma imagem enviada.'},
      );
    }

    final bytes = await image.readAsBytes();
    if (bytes.isEmpty) {
      return Response.json(
        statusCode: HttpStatus.badRequest,
        body: {'error': 'Arquivo de imagem vazio.'},
      );
    }

    final product = await uploadProductImage(
      productId: productId,
      bytes: bytes,
      contentType: image.contentType.mimeType,
      filename: image.name,
    );
    return Response.json(body: {'product': product});
  } on AdminProductException catch (error) {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': error.message},
    );
  } on StateError catch (error) {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': error.message},
    );
  }
}
