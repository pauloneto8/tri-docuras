import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/customers.dart';

/// Perfil do cliente logado: GET para ler, PUT para salvar nome, WhatsApp e
/// endereços. O e-mail não muda por aqui.
Future<Response> onRequest(RequestContext context) async {
  final session = await resolveCustomerSession(
    context.request.headers['authorization'],
  );
  if (session == null) return _notLoggedIn();

  switch (context.request.method) {
    case HttpMethod.get:
      final profile = await getCustomerProfile(session.customerId);
      if (profile == null) return _notLoggedIn();
      return Response.json(body: {'customer': profile});

    case HttpMethod.put:
      try {
        final body = await context.request.json() as Map<String, dynamic>;
        final profile = parseProfileFields(body);
        final addresses = parseCustomerAddresses(body['addresses']);
        await updateCustomerProfile(
          session.customerId,
          name: profile.name,
          whatsapp: profile.whatsapp,
          addresses: addresses,
        );
        final updated = await getCustomerProfile(session.customerId);
        return Response.json(body: {'customer': updated});
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

Response _notLoggedIn() => Response.json(
      statusCode: HttpStatus.unauthorized,
      body: {'error': 'Entre na sua conta para continuar.'},
    );
