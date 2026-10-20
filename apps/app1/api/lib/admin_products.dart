import 'package:postgres/postgres.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/product_images.dart';
import 'package:tri_docuras_api/product_options.dart';

final _categorySlugPattern = RegExp(r'^[a-z0-9]+(-[a-z0-9]+)*$');

class AdminProductException implements Exception {
  AdminProductException(this.message);

  final String message;

  @override
  String toString() => message;
}

class ProductInput {
  ProductInput({
    required this.name,
    required this.description,
    required this.price,
    required this.featured,
    required this.category,
    required this.available,
    this.stock,
    this.options,
  });

  final String name;
  final String description;
  final double price;
  final bool featured;
  final String category;
  final bool available;

  /// `null` = estoque ilimitado (padrão para produtos sem controle).
  final int? stock;

  /// `null` = não mexer nas variações (clientes antigos do painel não as enviam).
  final List<ProductOptionInput>? options;
}

class ProductOptionInput {
  ProductOptionInput({
    this.id,
    required this.kind,
    required this.label,
    required this.priceDelta,
    required this.active,
    required this.sortOrder,
  });

  /// Nulo para uma variação nova. Existentes voltam com o id, para que
  /// carrinhos abertos continuem válidos depois de salvar o produto.
  final int? id;
  final String kind;
  final String label;
  final double priceDelta;
  final bool active;
  final int sortOrder;
}

List<ProductOptionInput>? _parseOptions(Object? raw) {
  if (raw == null) return null;
  if (raw is! List) {
    throw AdminProductException('Variações inválidas.');
  }
  if (raw.length > maxProductOptions) {
    throw AdminProductException(
      'Use no máximo $maxProductOptions variações por produto.',
    );
  }

  final options = <ProductOptionInput>[];
  for (var index = 0; index < raw.length; index++) {
    final entry = raw[index];
    if (entry is! Map) {
      throw AdminProductException('Variação inválida.');
    }
    final kind = entry['kind']?.toString().trim() ?? '';
    if (!productOptionKinds.contains(kind)) {
      throw AdminProductException('Tipo de variação inválido.');
    }
    final label = entry['label']?.toString().trim() ?? '';
    if (label.isEmpty) {
      throw AdminProductException('Informe o nome de cada variação.');
    }
    if (label.length > maxOptionLabelLength) {
      throw AdminProductException(
        'Nome de variação muito longo (máx. $maxOptionLabelLength caracteres).',
      );
    }
    final priceRaw = entry['price_delta'];
    final priceDelta = switch (priceRaw) {
      null => 0.0,
      final num value => value.toDouble(),
      final String value when value.trim().isEmpty => 0.0,
      final String value => double.tryParse(value.replaceAll(',', '.')),
      _ => null,
    };
    if (priceDelta == null || priceDelta < 0 || priceDelta > maxOptionPrice) {
      throw AdminProductException(
        'Preço da variação "$label" inválido (use de 0 a $maxOptionPrice).',
      );
    }
    final idRaw = entry['id'];
    options.add(
      ProductOptionInput(
        id: idRaw == null
            ? null
            : idRaw is num
                ? idRaw.toInt()
                : throw AdminProductException('Variação inválida.'),
        kind: kind,
        label: label,
        priceDelta: double.parse(priceDelta.toStringAsFixed(2)),
        active: _parseBool(entry['active'], fallback: true),
        sortOrder: index + 1,
      ),
    );
  }
  return options;
}

const maxStock = 100000;

int? _parseStock(Object? raw) {
  if (raw == null) return null;
  final text = raw.toString().trim();
  if (text.isEmpty) return null;
  final value = int.tryParse(text);
  if (value == null || value < 0 || value > maxStock) {
    throw AdminProductException(
      'Estoque inválido (use um número de 0 a $maxStock, ou deixe em branco).',
    );
  }
  return value;
}

ProductInput parseProductInput(Map<String, dynamic> body) {
  final name = body['name']?.toString().trim() ?? '';
  if (name.isEmpty) {
    throw AdminProductException('Informe o nome do produto.');
  }
  if (name.length > 255) {
    throw AdminProductException('Nome muito longo (máx. 255 caracteres).');
  }

  final description = body['description']?.toString().trim() ?? '';

  final priceRaw = body['price'];
  final price = switch (priceRaw) {
    final num value => value.toDouble(),
    final String value => double.tryParse(value.replaceAll(',', '.')),
    _ => null,
  };
  if (price == null || price <= 0) {
    throw AdminProductException('Informe um preço válido maior que zero.');
  }
  if (price > 999999.99) {
    throw AdminProductException('Preço acima do limite permitido.');
  }

  final category = body['category']?.toString().trim() ?? '';
  if (category.isEmpty) {
    throw AdminProductException('Selecione a categoria do produto.');
  }
  if (category.length > 50 || !_categorySlugPattern.hasMatch(category)) {
    throw AdminProductException('Categoria inválida.');
  }

  return ProductInput(
    name: name,
    description: description,
    price: double.parse(price.toStringAsFixed(2)),
    featured: _parseBool(body['featured'], fallback: false),
    category: category,
    available: _parseBool(body['available'], fallback: true),
    stock: _parseStock(body['stock']),
    options: _parseOptions(body['options']),
  );
}

bool _parseBool(Object? value, {required bool fallback}) {
  if (value == null) return fallback;
  if (value is bool) return value;
  final normalized = value.toString().trim().toLowerCase();
  if (normalized == 'true' || normalized == '1' || normalized == 'yes') {
    return true;
  }
  if (normalized == 'false' || normalized == '0' || normalized == 'no') {
    return false;
  }
  return fallback;
}

Future<List<Map<String, Object?>>> listProductsForAdmin() async {
  final connection = await getConnection();
  final result = await connection.execute(
    '''
    SELECT p.id, p.name, p.description, p.price, p.featured, p.category,
           p.available, p.image_url, p.stock, c.label
    FROM products p
    LEFT JOIN product_categories c ON c.slug = p.category
    ORDER BY p.available DESC, p.featured DESC, p.name ASC;
    ''',
  );
  final products = result.map((row) {
    final map = _rowToProductMap(row);
    map['category_label'] = row[9]?.toString();
    return map;
  }).toList();

  final optionsByProduct = await _loadAdminOptions(
    connection,
    [for (final product in products) product['id']! as int],
  );
  for (final product in products) {
    product['options'] = optionsByProduct[product['id']] ?? const [];
  }
  return products;
}

/// Todas as variações (ativas e ocultas) dos produtos, para o painel.
Future<Map<int, List<Map<String, Object?>>>> _loadAdminOptions(
  Session session,
  List<int> productIds,
) async {
  final result = await session.execute(
    r'''
    SELECT id, product_id, kind, label, price_delta, active, sort_order
    FROM product_options
    WHERE product_id = ANY($1::int[])
    ORDER BY sort_order ASC, id ASC;
    ''',
    parameters: [productIds],
  );

  final byProduct = <int, List<Map<String, Object?>>>{};
  for (final row in result) {
    final productId = (row[1] as num).toInt();
    byProduct.putIfAbsent(productId, () => []).add({
      'id': (row[0] as num).toInt(),
      'kind': row[2],
      'label': row[3],
      'price_delta': _toDouble(row[4]),
      'active': row[5] == true,
      'sort_order': (row[6] as num).toInt(),
    });
  }
  return byProduct;
}

/// Grava as variações do produto. Existentes são atualizadas pelo id; as que
/// sumiram da lista são apagadas; as sem id são criadas.
Future<void> _saveOptions(
  Session session,
  int productId,
  List<ProductOptionInput> options,
) async {
  final existing = await session.execute(
    r'SELECT id FROM product_options WHERE product_id = $1;',
    parameters: [productId],
  );
  final existingIds = {for (final row in existing) (row[0] as num).toInt()};
  final keptIds = {
    for (final option in options)
      if (option.id != null) option.id!,
  };
  if (!existingIds.containsAll(keptIds)) {
    throw AdminProductException('Variação não encontrada. Recarregue o painel.');
  }

  for (final id in existingIds.difference(keptIds)) {
    await session.execute(
      r'DELETE FROM product_options WHERE id = $1;',
      parameters: [id],
    );
  }

  for (final option in options) {
    if (option.id == null) {
      await session.execute(
        r'''
        INSERT INTO product_options (product_id, kind, label, price_delta, active, sort_order)
        VALUES ($1, $2, $3, $4, $5, $6);
        ''',
        parameters: [
          productId,
          option.kind,
          option.label,
          option.priceDelta,
          option.active,
          option.sortOrder,
        ],
      );
    } else {
      await session.execute(
        r'''
        UPDATE product_options
        SET kind = $3, label = $4, price_delta = $5, active = $6, sort_order = $7
        WHERE id = $1 AND product_id = $2;
        ''',
        parameters: [
          option.id,
          productId,
          option.kind,
          option.label,
          option.priceDelta,
          option.active,
          option.sortOrder,
        ],
      );
    }
  }
}

Future<void> _ensureCategoryExists(Connection connection, String slug) async {
  final result = await connection.execute(
    'SELECT id FROM product_categories WHERE slug = \$1 LIMIT 1;',
    parameters: [slug],
  );
  if (result.isEmpty) {
    throw AdminProductException('Categoria não encontrada.');
  }
}

Future<Map<String, Object?>> createProduct(ProductInput input) async {
  final connection = await getConnection();
  await _ensureCategoryExists(connection, input.category);
  return connection.runTx((tx) async {
    final result = await tx.execute(
      '''
      INSERT INTO products (name, description, price, featured, category, available, stock)
      VALUES (\$1, \$2, \$3, \$4, \$5, \$6, \$7)
      RETURNING id, name, description, price, featured, category, available, image_url, stock;
      ''',
      parameters: [
        input.name,
        input.description,
        input.price,
        input.featured,
        input.category,
        input.available,
        input.stock,
      ],
    );

    if (result.isEmpty) {
      throw AdminProductException('Não foi possível criar o produto.');
    }

    final product = _rowToProductMap(result.first);
    final id = product['id']! as int;
    await _saveOptions(tx, id, input.options ?? const []);
    return _withOptions(tx, product);
  });
}

Future<Map<String, Object?>> _withOptions(
  Session session,
  Map<String, Object?> product,
) async {
  final id = product['id']! as int;
  final options = await _loadAdminOptions(session, [id]);
  product['options'] = options[id] ?? const [];
  return productToAdminJson(product);
}

Future<Map<String, Object?>> updateProduct(int id, ProductInput input) async {
  if (id <= 0) {
    throw AdminProductException('Produto inválido.');
  }

  final connection = await getConnection();
  await _ensureCategoryExists(connection, input.category);
  return connection.runTx((tx) async {
    final result = await tx.execute(
      '''
      UPDATE products
      SET name = \$2,
          description = \$3,
          price = \$4,
          featured = \$5,
          category = \$6,
          available = \$7,
          stock = \$8
      WHERE id = \$1
      RETURNING id, name, description, price, featured, category, available, image_url, stock;
      ''',
      parameters: [
        id,
        input.name,
        input.description,
        input.price,
        input.featured,
        input.category,
        input.available,
        input.stock,
      ],
    );

    if (result.isEmpty) {
      throw AdminProductException('Produto não encontrado.');
    }

    final options = input.options;
    if (options != null) {
      await _saveOptions(tx, id, options);
    }
    return _withOptions(tx, _rowToProductMap(result.first));
  });
}

Map<String, Object?> _rowToProductMap(ResultRow row) {
  return {
    'id': row[0],
    'name': row[1],
    'description': row[2],
    'price': _toDouble(row[3]),
    'featured': row[4] == true,
    'category': row[5],
    'available': row[6] == true,
    'image_url': row[7],
    'stock': row[8] == null ? null : (row[8]! as int),
  };
}

Future<Map<String, Object?>> updateProductImage(int id, String imageUrl) async {
  if (id <= 0) {
    throw AdminProductException('Produto inválido.');
  }

  final connection = await getConnection();
  final result = await connection.execute(
    '''
    UPDATE products
    SET image_url = \$2
    WHERE id = \$1
    RETURNING id, name, description, price, featured, category, available, image_url, stock;
    ''',
    parameters: [id, imageUrl],
  );

  if (result.isEmpty) {
    throw AdminProductException('Produto não encontrado.');
  }

  return _withOptions(connection, _rowToProductMap(result.first));
}

Future<Map<String, Object?>> uploadProductImage({
  required int productId,
  required List<int> bytes,
  required String contentType,
  String? filename,
}) async {
  final extension = extensionForContentType(contentType) ??
      extensionForFilename(filename);
  if (extension == null) {
    throw AdminProductException('Formato de imagem inválido. Use JPG, PNG ou WebP.');
  }

  final imageUrl = await saveProductImage(
    productId: productId,
    bytes: bytes,
    extension: extension,
  );
  return updateProductImage(productId, imageUrl);
}

Map<String, Object?> productToAdminJson(Map<String, Object?> product) {
  final available = product['available'] == true;
  return {
    'id': product['id'],
    'name': product['name'],
    'description': product['description'],
    'price': product['price'],
    'featured': product['featured'] == true,
    'category': product['category'],
    'category_label': (product['category_label'] as String?)?.isNotEmpty == true
        ? product['category_label']
        : categoryLabel(product['category'] as String),
    'available': available,
    'availability_label': available ? 'No catálogo' : 'Oculto',
    'image_url': product['image_url'],
    'stock': product['stock'],
    'options': product['options'] ?? const [],
  };
}

String categoryLabel(String category) {
  switch (category) {
    case 'brownies':
      return 'Brownies';
    case 'combos':
      return 'Combos';
    default:
      return category
          .split('-')
          .where((part) => part.isNotEmpty)
          .map((part) => part[0].toUpperCase() + part.substring(1))
          .join(' ');
  }
}

double _toDouble(Object? value) => switch (value) {
      final num n => n.toDouble(),
      final String s => double.parse(s),
      _ => 0.0,
    };
