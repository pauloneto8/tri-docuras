import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/env.dart';
import 'package:tri_docuras_api/orders.dart';

Handler middleware(Handler handler) {
  return (context) async {
    if (context.request.method == HttpMethod.options) {
      return _withCors(
        context,
        Response(statusCode: HttpStatus.noContent),
      );
    }

    try {
      await initializeDatabase();
    } catch (_) {
      // Database may be unavailable during startup; routes handle errors.
    }

    _expireStaleOrdersSometimes();

    final response = await handler(context);
    return _withCors(context, response);
  };
}

DateTime _lastExpiryRun = DateTime.fromMillisecondsSinceEpoch(0);

/// Expira pedidos não pagos no máximo a cada 10 min, sem atrasar a resposta.
void _expireStaleOrdersSometimes() {
  final now = DateTime.now();
  if (now.difference(_lastExpiryRun) < const Duration(minutes: 10)) return;
  _lastExpiryRun = now;
  expireStaleOrders().then((count) {
    if (count > 0) stderr.writeln('[orders] $count pedido(s) expirado(s)');
  }).catchError((Object e) {
    stderr.writeln('[orders] falha ao expirar pedidos: $e');
  });
}

final RegExp _devHosts = RegExp(r'^(localhost|127\.0\.0\.1|::1)$');

/// Retorna a origem apenas se for permitida; `null` bloqueia CORS.
String? _allowedOrigin(RequestContext context) {
  final origin = context.request.headers['origin'];
  if (origin == null) return null;

  final uri = Uri.tryParse(origin);
  if (uri == null) return null;

  // Dev local (Flutter web / emulador).
  final isDev = _devHosts.hasMatch(uri.host) &&
      (uri.scheme == 'http' || uri.scheme == 'https');
  if (isDev) return origin;

  // Produção: somente o domínio da loja (mesmo esquema https).
  final domain = Env.get('APP1_DOMAIN')?.toLowerCase() ?? '';
  if (domain.isEmpty || uri.scheme != 'https') return null;
  if (uri.host == domain || uri.host == 'www.$domain') return origin;
  return null;
}

Response _withCors(RequestContext context, Response response) {
  final origin = _allowedOrigin(context);
  return response.copyWith(
    headers: {
      ...response.headers,
      if (origin != null) 'Access-Control-Allow-Origin': origin,
      if (origin != null) 'Vary': 'Origin',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  );
}
