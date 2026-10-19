import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/admin_categories.dart';
import 'package:tri_docuras_api/app_public_config.dart';

Future<Response> onRequest(RequestContext context) async {
  if (context.request.method != HttpMethod.get) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final config = AppPublicConfig.toJson();
  try {
    final categories = await listActiveCategories();
    config['categories'] = categories
        .map((category) => {
              'slug': category['slug'],
              'label': category['label'],
            })
        .toList();
  } catch (_) {
    config['categories'] = const [];
  }

  return Response.json(body: config);
}
