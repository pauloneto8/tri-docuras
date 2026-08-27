import 'dart:io';

import 'package:postgres/postgres.dart';
import 'package:tri_docuras_api/db.dart';

Future<void> main() async {
  for (var attempt = 1; attempt <= 30; attempt++) {
    try {
      final connection = await getConnection();
      await connection.execute('SELECT 1;');
      exit(0);
    } catch (_) {
      if (attempt == 30) {
        exit(1);
      }
      await Future<void>.delayed(const Duration(seconds: 1));
    }
  }
}
