import 'package:postgres/postgres.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/product_images.dart';

const adminProductCategories = ['brownies', 'combos'];

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
  });

  final String name;
  final String description;
  final double price;
  final bool featured;
  final String category;
  final bool available;
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
  if (!adminProductCategories.contains(category)) {
    throw AdminProductException('Categoria inválida. Use brownies ou combos.');
  }

  return ProductInput(
    name: name,
    description: description,
    price: double.parse(price.toStringAsFixed(2)),
    featured: _parseBool(body['featured'], fallback: false),
    category: category,
    available: _parseBool(body['available'], fallback: true),
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
    SELECT id, name, description, price, featured, category, available, image_url
    FROM products
    ORDER BY available DESC, featured DESC, name ASC;
    ''',
  );
  return result.map(_rowToProductMap).toList();
}

Future<Map<String, Object?>> createProduct(ProductInput input) async {
  final connection = await getConnection();
  final result = await connection.execute(
    '''
    INSERT INTO products (name, description, price, featured, category, available)
    VALUES (\$1, \$2, \$3, \$4, \$5, \$6)
    RETURNING id, name, description, price, featured, category, available, image_url;
    ''',
    parameters: [
      input.name,
      input.description,
      input.price,
      input.featured,
      input.category,
      input.available,
    ],
  );

  if (result.isEmpty) {
    throw AdminProductException('Não foi possível criar o produto.');
  }

  return productToAdminJson(_rowToProductMap(result.first));
}

Future<Map<String, Object?>> updateProduct(int id, ProductInput input) async {
  if (id <= 0) {
    throw AdminProductException('Produto inválido.');
  }

  final connection = await getConnection();
  final result = await connection.execute(
    '''
    UPDATE products
    SET name = \$2,
        description = \$3,
        price = \$4,
        featured = \$5,
        category = \$6,
        available = \$7
    WHERE id = \$1
    RETURNING id, name, description, price, featured, category, available, image_url;
    ''',
    parameters: [
      id,
      input.name,
      input.description,
      input.price,
      input.featured,
      input.category,
      input.available,
    ],
  );

  if (result.isEmpty) {
    throw AdminProductException('Produto não encontrado.');
  }

  return productToAdminJson(_rowToProductMap(result.first));
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
    RETURNING id, name, description, price, featured, category, available, image_url;
    ''',
    parameters: [id, imageUrl],
  );

  if (result.isEmpty) {
    throw AdminProductException('Produto não encontrado.');
  }

  return productToAdminJson(_rowToProductMap(result.first));
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
    'category_label': categoryLabel(product['category'] as String),
    'available': available,
    'availability_label': available ? 'No catálogo' : 'Oculto',
    'image_url': product['image_url'],
  };
}

String categoryLabel(String category) {
  switch (category) {
    case 'brownies':
      return 'Brownies';
    case 'combos':
      return 'Combos';
    default:
      return category;
  }
}

double _toDouble(Object? value) => switch (value) {
      final num n => n.toDouble(),
      final String s => double.parse(s),
      _ => 0.0,
    };
