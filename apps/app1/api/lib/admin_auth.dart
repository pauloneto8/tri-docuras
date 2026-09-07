import 'dart:convert';
import 'dart:io';

import 'package:dart_frog/dart_frog.dart';

class AdminAuth {
  static String? get password {
    final value = Platform.environment['APP1_ADMIN_PASSWORD'] ??
        Platform.environment['ADMIN_PASSWORD'];
    if (value == null || value.trim().isEmpty) return null;
    return value.trim();
  }

  static bool get isConfigured => password != null;

  static String issueToken() {
    final value = password;
    if (value == null) {
      throw StateError('Admin password not configured');
    }
    return base64Url.encode(utf8.encode(value));
  }

  static bool verifyToken(String? token) {
    final value = password;
    if (value == null || token == null || token.isEmpty) return false;
    try {
      final decoded = utf8.decode(base64Url.decode(token));
      return decoded == value;
    } catch (_) {
      return false;
    }
  }

  static bool isAuthorized(Request request) {
    final auth = request.headers['Authorization'];
    if (auth == null || !auth.startsWith('Bearer ')) return false;
    return verifyToken(auth.substring(7).trim());
  }

  static Response unauthorized() => Response.json(
        statusCode: HttpStatus.unauthorized,
        body: {'error': 'Não autorizado.'},
      );
}
