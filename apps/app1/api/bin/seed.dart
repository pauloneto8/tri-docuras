import 'dart:io';

import 'package:tri_docuras_api/db.dart';

Future<void> main() async {
  await initializeDatabase();
  await closeConnection();
  print('Banco inicializado com sucesso.');
  exit(0);
}
