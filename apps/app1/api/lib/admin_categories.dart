import 'package:postgres/postgres.dart';
import 'package:tri_docuras_api/db.dart';

class AdminCategoryException implements Exception {
  AdminCategoryException(this.message);

  final String message;

  @override
  String toString() => message;
}

class CategoryInput {
  CategoryInput({
    required this.label,
    required this.slug,
    required this.sortOrder,
    required this.active,
  });

  final String label;
  final String slug;
  final int sortOrder;
  final bool active;
}

const _accentMap = {
  'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a', 'ä': 'a',
  'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
  'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
  'ó': 'o', 'ò': 'o', 'õ': 'o', 'ô': 'o', 'ö': 'o',
  'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
  'ç': 'c', 'ñ': 'n',
};

String slugify(String value) {
  final buffer = StringBuffer();
  for (final rune in value.toLowerCase().runes) {
    final char = String.fromCharCode(rune);
    buffer.write(_accentMap[char] ?? char);
  }
  return buffer
      .toString()
      .replaceAll(RegExp(r'[^a-z0-9]+'), '-')
      .replaceAll(RegExp(r'^-+|-+$'), '');
}

final _slugPattern = RegExp(r'^[a-z0-9]+(-[a-z0-9]+)*$');

/// Valida o corpo de criação/edição de categoria.
///
/// [requireSlug] deve ser `true` na criação (slug derivado do label quando
/// ausente). Na edição o slug é imutável e ignorado.
CategoryInput parseCategoryInput(
  Map<String, dynamic> body, {
  bool requireSlug = true,
}) {
  final label = body['label']?.toString().trim() ?? '';
  if (label.isEmpty) {
    throw AdminCategoryException('Informe o nome da categoria.');
  }
  if (label.length > 100) {
    throw AdminCategoryException('Nome muito longo (máx. 100 caracteres).');
  }

  final rawSlug = body['slug']?.toString().trim() ?? '';
  final slug = rawSlug.isNotEmpty ? rawSlug.toLowerCase() : slugify(label);
  if (requireSlug) {
    if (slug.isEmpty) {
      throw AdminCategoryException('Não foi possível gerar a identificação.');
    }
    if (slug.length > 50) {
      throw AdminCategoryException('Identificação muito longa (máx. 50).');
    }
    if (!_slugPattern.hasMatch(slug)) {
      throw AdminCategoryException(
        'Identificação inválida. Use apenas letras minúsculas, números e hífen.',
      );
    }
  }

  final sortRaw = body['sort_order'];
  final sortOrder = switch (sortRaw) {
    final num value => value.toInt(),
    final String value => int.tryParse(value) ?? 0,
    _ => 0,
  };

  return CategoryInput(
    label: label,
    slug: slug,
    sortOrder: sortOrder,
    active: _parseBool(body['active'], fallback: true),
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

Future<List<Map<String, Object?>>> listCategoriesForAdmin() async {
  final connection = await getConnection();
  final result = await connection.execute(
    '''
    SELECT id, slug, label, sort_order, active
    FROM product_categories
    ORDER BY sort_order ASC, label ASC;
    ''',
  );
  return result.map(_rowToCategoryMap).toList();
}

/// Categorias ativas para consumo público (app cliente).
Future<List<Map<String, Object?>>> listActiveCategories() async {
  final connection = await getConnection();
  final result = await connection.execute(
    '''
    SELECT id, slug, label, sort_order, active
    FROM product_categories
    WHERE active = TRUE
    ORDER BY sort_order ASC, label ASC;
    ''',
  );
  return result.map(_rowToCategoryMap).toList();
}

Future<Map<String, Object?>> createCategory(CategoryInput input) async {
  final connection = await getConnection();
  await _ensureSlugAvailable(connection, input.slug);

  final result = await connection.execute(
    '''
    INSERT INTO product_categories (slug, label, sort_order, active)
    VALUES (\$1, \$2, \$3, \$4)
    RETURNING id, slug, label, sort_order, active;
    ''',
    parameters: [input.slug, input.label, input.sortOrder, input.active],
  );

  if (result.isEmpty) {
    throw AdminCategoryException('Não foi possível criar a categoria.');
  }
  return categoryToAdminJson(_rowToCategoryMap(result.first));
}

Future<Map<String, Object?>> updateCategory(int id, CategoryInput input) async {
  if (id <= 0) {
    throw AdminCategoryException('Categoria inválida.');
  }

  final connection = await getConnection();
  final result = await connection.execute(
    '''
    UPDATE product_categories
    SET label = \$2,
        sort_order = \$3,
        active = \$4
    WHERE id = \$1
    RETURNING id, slug, label, sort_order, active;
    ''',
    parameters: [id, input.label, input.sortOrder, input.active],
  );

  if (result.isEmpty) {
    throw AdminCategoryException('Categoria não encontrada.');
  }
  return categoryToAdminJson(_rowToCategoryMap(result.first));
}

Future<void> deleteCategory(int id) async {
  if (id <= 0) {
    throw AdminCategoryException('Categoria inválida.');
  }

  final connection = await getConnection();
  final category = await connection.execute(
    'SELECT slug FROM product_categories WHERE id = \$1 LIMIT 1;',
    parameters: [id],
  );
  if (category.isEmpty) {
    throw AdminCategoryException('Categoria não encontrada.');
  }

  final slug = category.first.first as String;
  final usage = await connection.execute(
    'SELECT COUNT(*) FROM products WHERE category = \$1;',
    parameters: [slug],
  );
  final count = usage.isEmpty ? 0 : (usage.first.first as num).toInt();
  if (count > 0) {
    throw AdminCategoryException(
      'Há $count produto(s) nesta categoria. Mova-os antes de excluir.',
    );
  }

  await connection.execute(
    'DELETE FROM product_categories WHERE id = \$1;',
    parameters: [id],
  );
}

Future<void> _ensureSlugAvailable(Connection connection, String slug) async {
  final existing = await connection.execute(
    'SELECT id FROM product_categories WHERE slug = \$1 LIMIT 1;',
    parameters: [slug],
  );
  if (existing.isNotEmpty) {
    throw AdminCategoryException('Já existe uma categoria com essa identificação.');
  }
}

Map<String, Object?> _rowToCategoryMap(ResultRow row) {
  return {
    'id': row[0],
    'slug': row[1],
    'label': row[2],
    'sort_order': (row[3] as num).toInt(),
    'active': row[4] == true,
  };
}

Map<String, Object?> categoryToAdminJson(Map<String, Object?> category) {
  final active = category['active'] == true;
  return {
    'id': category['id'],
    'slug': category['slug'],
    'label': category['label'],
    'sort_order': category['sort_order'],
    'active': active,
    'status_label': active ? 'Ativa' : 'Oculta',
  };
}
