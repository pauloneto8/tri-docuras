import 'dart:io';

import 'package:dart_frog/dart_frog.dart';
import 'package:tri_docuras_api/product_images.dart';

Future<Response> onRequest(RequestContext context, String filename) async {
  if (context.request.method != HttpMethod.get) {
    return Response(statusCode: HttpStatus.methodNotAllowed);
  }

  final file = resolveProductImageFile(filename);
  if (file == null) {
    return Response(statusCode: HttpStatus.notFound);
  }

  final bytes = await file.readAsBytes();
  return Response.bytes(
    body: bytes,
    headers: {
      'Content-Type': contentTypeForFilename(filename),
      'Cache-Control': 'public, max-age=86400',
    },
  );
}
