import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';

Future<Response> onRequest(RequestContext context) async {
  if (context.request.method != HttpMethod.post) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  if (!AdminAuth.isConfigured) {
    return Response.json(
      statusCode: HttpStatus.serviceUnavailable,
      body: {'error': 'Painel admin não configurado.'},
    );
  }

  try {
    final body = await context.request.json() as Map<String, dynamic>;
    final password = body['password']?.toString() ?? '';
    if (password != AdminAuth.password) {
      return Response.json(
        statusCode: HttpStatus.unauthorized,
        body: {'error': 'Senha incorreta.'},
      );
    }

    return Response.json(
      body: {
        'token': AdminAuth.issueToken(),
      },
    );
  } on FormatException {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': 'Corpo da requisição inválido.'},
    );
  }
}
