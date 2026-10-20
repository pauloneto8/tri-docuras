import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/customers.dart';

/// Favoritos do cliente logado. GET devolve os IDs; PUT substitui a lista.
Future<Response> onRequest(RequestContext context) async {
  final session = await resolveCustomerSession(
    context.request.headers['authorization'],
  );
  if (session == null) {
    return Response.json(
      statusCode: HttpStatus.unauthorized,
      body: {'error': 'Entre na sua conta para continuar.'},
    );
  }

  switch (context.request.method) {
    case HttpMethod.get:
      final ids = await getCustomerFavorites(session.customerId);
      return Response.json(body: {'product_ids': ids});

    case HttpMethod.put:
      try {
        final body = await context.request.json() as Map<String, dynamic>;
        final ids = parseFavoriteIds(body['product_ids']);
        await replaceCustomerFavorites(session.customerId, ids);
        return Response.json(body: {'product_ids': ids});
      } on CustomerException catch (error) {
        return Response.json(
          statusCode: error.statusCode,
          body: {'error': error.message},
        );
      } on FormatException {
        return Response.json(
          statusCode: HttpStatus.badRequest,
          body: {'error': 'Corpo da requisição inválido.'},
        );
      }

    default:
      return Response(statusCode: HttpStatus.methodNotAllowed);
  }
}
