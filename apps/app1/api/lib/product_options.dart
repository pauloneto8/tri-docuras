import 'package:postgres/postgres.dart';

/// Variações cadastradas por produto: tamanhos (escolha obrigatória, um só)
/// e adicionais (opcionais, vários, com preço).
const productOptionKinds = ['size', 'addon'];
const maxProductOptions = 20;
const maxOptionLabelLength = 80;
const maxOptionPrice = 999.99;

/// Separador usado para mostrar as opções escolhidas no pedido.
const optionLabelSeparator = ' · ';

class ProductOptionRow {
  const ProductOptionRow({
    required this.id,
    required this.productId,
    required this.kind,
    required this.label,
    required this.priceDelta,
    required this.sortOrder,
  });

  final int id;
  final int productId;
  final String kind;
  final String label;
  final double priceDelta;
  final int sortOrder;
}

class ResolvedOptions {
  const ResolvedOptions({
    required this.extraPrice,
    required this.label,
    required this.ids,
  });

  /// Soma dos adicionais escolhidos, a somar ao preço do produto.
  final double extraPrice;

  /// Texto gravado no pedido (ex.: `9x9cm · Sem lactose`); nulo sem escolhas.
  final String? label;

  final List<int> ids;
}

class ProductOptionException implements Exception {
  ProductOptionException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Confere as opções escolhidas no carrinho contra as opções ativas do
/// produto e calcula o adicional. Regras: sem repetidas, só opções do próprio
/// produto, e exatamente um tamanho quando o produto tem tamanhos.
ResolvedOptions resolveProductOptions({
  required String productName,
  required List<int> selectedIds,
  required List<ProductOptionRow> available,
}) {
  if (selectedIds.toSet().length != selectedIds.length) {
    throw ProductOptionException('Opção repetida no carrinho.');
  }

  final chosen = <ProductOptionRow>[];
  for (final id in selectedIds) {
    final match = available.where((option) => option.id == id);
    if (match.isEmpty) {
      throw ProductOptionException(
        'Opção indisponível para $productName. Atualize a página e tente de novo.',
      );
    }
    chosen.add(match.first);
  }

  final hasSizes = available.any((option) => option.kind == 'size');
  final sizesChosen = chosen.where((option) => option.kind == 'size').length;
  if (hasSizes && sizesChosen == 0) {
    throw ProductOptionException('Escolha o tamanho de $productName.');
  }
  if (sizesChosen > 1) {
    throw ProductOptionException('Escolha só um tamanho de $productName.');
  }

  chosen.sort((a, b) => a.sortOrder.compareTo(b.sortOrder));
  final extra = chosen.fold<double>(0, (sum, option) => sum + option.priceDelta);
  return ResolvedOptions(
    extraPrice: extra,
    label: chosen.isEmpty
        ? null
        : chosen.map((option) => option.label).join(optionLabelSeparator),
    ids: [for (final option in chosen) option.id],
  );
}

Future<void> ensureProductOptionsSchema(Connection connection) async {
  final existed = await connection.execute(
    "SELECT to_regclass('product_options') IS NOT NULL;",
  );
  final alreadyCreated = existed.first.first == true;

  await connection.execute('''
    CREATE TABLE IF NOT EXISTS product_options (
      id SERIAL PRIMARY KEY,
      product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
      kind VARCHAR(20) NOT NULL CHECK (kind IN ('size', 'addon')),
      label VARCHAR(80) NOT NULL,
      price_delta NUMERIC(10, 2) NOT NULL DEFAULT 0 CHECK (price_delta >= 0),
      active BOOLEAN NOT NULL DEFAULT TRUE,
      sort_order INTEGER NOT NULL DEFAULT 0
    );
  ''');
  await connection.execute('''
    CREATE INDEX IF NOT EXISTS idx_product_options_product ON product_options (product_id);
  ''');
  await connection.execute('''
    ALTER TABLE order_items ADD COLUMN IF NOT EXISTS options TEXT;
  ''');

  // Primeira criação da tabela: leva para as brownies as opções que o app
  // tinha fixas no código (9x9cm, Fatia grande e sem lactose +R$ 3). Só roda
  // uma vez, para não recriar opções que o dono apagar depois.
  if (!alreadyCreated) {
    await seedDefaultBrownieOptions(connection);
  }
}

Future<void> seedDefaultBrownieOptions(Connection connection) async {
  await connection.execute(r'''
    INSERT INTO product_options (product_id, kind, label, price_delta, active, sort_order)
    SELECT p.id, v.kind, v.label, v.price_delta, TRUE, v.sort_order
    FROM products p
    CROSS JOIN (VALUES
      ('size', '9x9cm', 0.00::numeric, 1),
      ('size', 'Fatia grande', 0.00::numeric, 2),
      ('addon', 'Sem lactose', 3.00::numeric, 3)
    ) AS v(kind, label, price_delta, sort_order)
    WHERE p.category = 'brownies';
  ''');
}

/// Opções ativas dos produtos pedidos, agrupadas pelo id do produto.
Future<Map<int, List<ProductOptionRow>>> fetchActiveOptionsByProduct(
  Session session,
  List<int> productIds,
) async {
  final result = await session.execute(
    r'''
    SELECT id, product_id, kind, label, price_delta, sort_order
    FROM product_options
    WHERE active = TRUE AND product_id = ANY($1::int[])
    ORDER BY sort_order ASC, id ASC;
    ''',
    parameters: [productIds],
  );

  final byProduct = <int, List<ProductOptionRow>>{};
  for (final row in result) {
    final option = ProductOptionRow(
      id: (row[0] as num).toInt(),
      productId: (row[1] as num).toInt(),
      kind: row[2] as String,
      label: row[3] as String,
      priceDelta: _toDouble(row[4]),
      sortOrder: (row[5] as num).toInt(),
    );
    byProduct.putIfAbsent(option.productId, () => []).add(option);
  }
  return byProduct;
}

double _toDouble(Object? value) => switch (value) {
      final num n => n.toDouble(),
      final String s => double.parse(s),
      _ => 0.0,
    };
