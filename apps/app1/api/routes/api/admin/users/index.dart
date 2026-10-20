import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';
import 'package:tri_docuras_api/admin_users.dart';

Future<Response> onRequest(RequestContext context) async {
  if (!AdminAuth.isConfigured) {
    return Response.json(
      statusCode: HttpStatus.serviceUnavailable,
      body: {'error': 'Painel admin não configurado.'},
    );
  }

  final session = await AdminAuth.resolve(context.request);
  if (session == null) return AdminAuth.unauthorized();
  if (!session.isOwner) return AdminAuth.forbidden();

  if (context.request.method == HttpMethod.get) {
    final users = await listAdminUsers();
    return Response.json(
      body: {'users': users.map((user) => user.toAdminJson()).toList()},
    );
  }

  if (context.request.method == HttpMethod.post) {
    try {
      final body = await context.request.json() as Map<String, dynamic>;
      final input = parseAdminUserInput(body, isCreate: true);
      final user = await createAdminUser(input);
      return Response.json(
        statusCode: HttpStatus.created,
        body: {'user': user.toAdminJson()},
      );
    } on AdminUserException catch (error) {
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
