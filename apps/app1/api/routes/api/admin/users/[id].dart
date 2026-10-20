import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_auth.dart';
import 'package:tri_docuras_api/admin_users.dart';

Future<Response> onRequest(RequestContext context, String id) async {
  final session = await AdminAuth.resolve(context.request);
  if (session == null) return AdminAuth.unauthorized();
  if (!session.isOwner) return AdminAuth.forbidden();

  final userId = int.tryParse(id);
  if (userId == null) {
    return Response.json(
      statusCode: HttpStatus.notFound,
      body: {'error': 'Usuário não encontrado.'},
    );
  }

  if (context.request.method == HttpMethod.put) {
    try {
      final body = await context.request.json() as Map<String, dynamic>;
      final input = parseAdminUserInput(body, isCreate: false);
      final user = await updateAdminUser(
        userId,
        input,
        actingUserId: session.userId,
      );
      return Response.json(body: {'user': user.toAdminJson()});
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
