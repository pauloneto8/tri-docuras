import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';
import 'package:tri_docuras_api/store_settings.dart';

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
    final settings = await getStoreSettings();
    return Response.json(body: {'settings': settings.toJson()});
  }

  if (context.request.method == HttpMethod.put) {
    try {
      final body = await context.request.json() as Map<String, dynamic>;
      final settings = await updateStoreSettings(
        parseStoreSettingsInput(body),
      );
      return Response.json(body: {'settings': settings.toJson()});
    } on StoreSettingsException catch (error) {
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
