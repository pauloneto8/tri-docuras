import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/customers.dart';
import 'package:tri_docuras_api/mercado_pago_client.dart';
import 'package:tri_docuras_api/mercado_pago_config.dart';
import 'package:tri_docuras_api/orders.dart';
import 'package:tri_docuras_api/rate_limiter.dart';

Future<Response> onRequest(RequestContext context) async {
  if (context.request.method != HttpMethod.post) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final limited = rateLimitResponse(orderCreateLimiter, clientIp(context));
  if (limited != null) return limited;

  final session = await resolveCustomerSession(
    context.request.headers['authorization'],
  );
  if (session == null) {
    return Response.json(
      statusCode: HttpStatus.unauthorized,
      body: {'error': 'Entre na sua conta para fazer um pedido.'},
    );
  }

  try {
    final body = await context.request.json() as Map<String, dynamic>;
    final input = await parseCreateOrderInput(body);
    final order = await createOrder(input, customerId: session.customerId);

    Map<String, Object?>? pix;
    String? pixError;
    if (MercadoPagoConfig.isConfigured) {
      try {
        pix = await createPixForOrder(order['id'] as String);
      } on MercadoPagoException catch (error) {
        pixError = error.message;
        stderr.writeln('[mp] Pix do pedido ${order['id']} não gerado: ${error.message}');
      } catch (error) {
        pixError = 'Não foi possível gerar o Pix.';
        stderr.writeln('[mp] Pix do pedido ${order['id']} falhou: $error');
      }
    } else {
      pixError = 'Pagamento Pix indisponível no momento.';
    }

    return Response.json(
      statusCode: HttpStatus.created,
      body: {
        'order': orderToPublicJson(order),
        if (pix != null) 'pix': pix,
        if (pixError != null) 'pix_error': pixError,
      },
    );
  } on OrderValidationException catch (error) {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': error.message},
    );
  } on FormatException {
    return Response.json(
      statusCode: HttpStatus.badRequest,
      body: {'error': 'Corpo da requisição inválido.'},
    );
  } catch (error) {
    return Response.json(
      statusCode: HttpStatus.internalServerError,
      body: {
        'error': 'Não foi possível registrar o pedido.',
        'details': error.toString(),
      },
    );
  }
}
