import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/db.dart';

Handler middleware(Handler handler) {
  return (context) async {
    if (context.request.method == HttpMethod.options) {
      return _withCors(
        Response(statusCode: HttpStatus.noContent),
      );
    }

    try {
      await initializeDatabase();
    } catch (_) {
      // Database may be unavailable during startup; routes handle errors.
    }

    final response = await handler(context);
    return _withCors(response);
  };
}

Response _withCors(Response response) {
  return response.copyWith(
    headers: {
      ...response.headers,
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  );
}
