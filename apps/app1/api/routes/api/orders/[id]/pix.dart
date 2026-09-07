import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/mercado_pago_client.dart';
import 'package:tri_docuras_api/orders.dart';

Future<Response> onRequest(RequestContext context, String id) async {
  if (context.request.method != HttpMethod.post) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  try {
    final pix = await createPixForOrder(id);
    return Response.json(body: {'pix': pix});
  } on OrderValidationException catch (error) {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': error.message},
    );
  } on MercadoPagoException catch (error) {
    return Response.json(
      statusCode: HttpStatus.badGateway,
      body: {'error': error.message},
    );
  } catch (error) {
    return Response.json(
      statusCode: HttpStatus.internalServerError,
      body: {'error': 'Não foi possível gerar o Pix.'},
    );
  }
}
