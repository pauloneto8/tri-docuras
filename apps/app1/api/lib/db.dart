import 'dart:io';

import 'package:postgres/postgres.dart';

Connection? _connection;

Future<Connection> getConnection() async {
  if (_connection != null) {
    return _connection!;
  }

  final databaseUrl = Platform.environment['DATABASE_URL'];
  if (databaseUrl != null && databaseUrl.isNotEmpty) {
    final uri = Uri.parse(databaseUrl);
    final userInfo = uri.userInfo.split(':');
    _connection = await Connection.open(
      Endpoint(
        host: uri.host,
        port: uri.port,
        database: uri.pathSegments.isNotEmpty ? uri.pathSegments.first : uri.path.replaceFirst('/', ''),
        username: userInfo.first,
        password: userInfo.length > 1 ? userInfo.sublist(1).join(':') : '',
      ),
      settings: const ConnectionSettings(sslMode: SslMode.disable),
    );
    return _connection!;
  }

  final host = Platform.environment['DB_HOST'] ?? 'localhost';
  final port = int.tryParse(Platform.environment['DB_PORT'] ?? '5432') ?? 5432;
  final database = Platform.environment['DB_NAME'] ?? 'app1';
  final username = Platform.environment['DB_USER'] ?? 'app1';
  final password = Platform.environment['DB_PASSWORD'] ?? '';

  _connection = await Connection.open(
    Endpoint(
      host: host,
      port: port,
      database: database,
      username: username,
      password: password,
    ),
    settings: const ConnectionSettings(sslMode: SslMode.disable),
  );

  return _connection!;
}

Future<void> ensureSchema(Connection connection) async {
  await connection.execute('''
    CREATE TABLE IF NOT EXISTS products (
      id SERIAL PRIMARY KEY,
      name VARCHAR(255) NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      price NUMERIC(10, 2) NOT NULL,
      featured BOOLEAN NOT NULL DEFAULT FALSE,
      category VARCHAR(50) NOT NULL DEFAULT 'brownies',
      available BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
  ''');

  await connection.execute('''
    ALTER TABLE products ADD COLUMN IF NOT EXISTS category VARCHAR(50) NOT NULL DEFAULT 'brownies';
  ''');
  await connection.execute('''
    ALTER TABLE products ADD COLUMN IF NOT EXISTS available BOOLEAN NOT NULL DEFAULT TRUE;
  ''');
}

Future<void> seedProducts(Connection connection) async {
  final result = await connection.execute('SELECT COUNT(*) FROM products;');
  final count = result.first.first as int;
  if (count > 0) {
    await _migrateCatalog(connection);
    return;
  }

  await _insertCatalog(connection);
}

Future<void> _insertCatalog(Connection connection) async {
  await connection.execute(
    r'''
    INSERT INTO products (name, description, price, featured, category, available) VALUES
      ($1, $2, $3, $4, $5, $6),
      ($7, $8, $9, $10, $11, $12),
      ($13, $14, $15, $16, $17, $18),
      ($19, $20, $21, $22, $23, $24);
    ''',
    parameters: [
      'Brownie Tradicional',
      'Brownie amanteigado clássico, macio por dentro e com casquinha.',
      12.00,
      true,
      'brownies',
      true,
      'Ninho c/ Nutella',
      'Brownie amanteigado, recheado e coberto com Nutella derretida e leite Ninho.',
      15.00,
      true,
      'brownies',
      true,
      'Brownie c/ Nozes',
      'Brownie intenso com nozes caramelizadas e textura crocante.',
      14.00,
      false,
      'brownies',
      true,
      'Caixa Presente (4un)',
      'Seleção especial de 4 brownies artesanais para presentear.',
      48.00,
      false,
      'combos',
      true,
    ],
  );
}

Future<void> _migrateCatalog(Connection connection) async {
  final catalog = [
    ['Brownie Tradicional', 'Brownie amanteigado clássico, macio por dentro e com casquinha.', 12.00, true, 'brownies'],
    ['Ninho c/ Nutella', 'Brownie amanteigado, recheado e coberto com Nutella derretida e leite Ninho.', 15.00, true, 'brownies'],
    ['Brownie c/ Nozes', 'Brownie intenso com nozes caramelizadas e textura crocante.', 14.00, false, 'brownies'],
    ['Caixa Presente (4un)', 'Seleção especial de 4 brownies artesanais para presentear.', 48.00, false, 'combos'],
  ];

  for (final item in catalog) {
    final existing = await connection.execute(
      'SELECT id FROM products WHERE name = \$1 LIMIT 1;',
      parameters: [item[0]],
    );
    if (existing.isEmpty) {
      await connection.execute(
        r'''
        INSERT INTO products (name, description, price, featured, category, available)
        VALUES ($1, $2, $3, $4, $5, TRUE);
        ''',
        parameters: [item[0], item[1], item[2], item[3], item[4]],
      );
    } else {
      await connection.execute(
        r'''
        UPDATE products
        SET description = $2, price = $3, featured = $4, category = $5, available = TRUE
        WHERE name = $1;
        ''',
        parameters: [item[0], item[1], item[2], item[3], item[4]],
      );
    }
  }

  final catalogNames = catalog.map((item) => item[0]).toList();
  await connection.execute(
    r'''
    UPDATE products SET available = FALSE
    WHERE NOT (name = ANY($1::text[]));
    ''',
    parameters: [catalogNames],
  );
}

Future<void> closeConnection() async {
  if (_connection != null) {
    await _connection!.close();
    _connection = null;
  }
}

Future<void> initializeDatabase() async {
  final connection = await getConnection();
  await ensureSchema(connection);
  await seedProducts(connection);
}

Future<bool> pingDatabase() async {
  try {
    final connection = await getConnection();
    await connection.execute('SELECT 1;');
    return true;
  } catch (_) {
    return false;
  }
}

Future<List<Map<String, Object?>>> fetchProducts() async {
  final connection = await getConnection();
  final result = await connection.execute(
    '''
    SELECT id, name, description, price, featured, category, available
    FROM products
    WHERE available = TRUE
    ORDER BY featured DESC, name ASC;
    ''',
  );

  return result
      .map(
        (row) => {
          'id': row[0],
          'name': row[1],
          'description': row[2],
          'price': switch (row[3]) {
            final num value => value.toDouble(),
            final String value => double.parse(value),
            _ => 0.0,
          },
          'featured': row[4],
          'category': row[5],
          'available': row[6],
        },
      )
      .toList();
}
