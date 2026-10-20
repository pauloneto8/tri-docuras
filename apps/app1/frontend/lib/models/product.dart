import 'package:tri_docuras/models/product_option.dart';

class Product {
  const Product({
    required this.id,
    required this.name,
    required this.description,
    required this.price,
    required this.featured,
    required this.category,
    this.available = true,
    this.imageUrl,
    this.stock,
    this.options = const [],
  });

  factory Product.fromJson(Map<String, dynamic> json) {
    return Product(
      id: (json['id'] as num).toInt(),
      name: json['name'] as String,
      description: json['description'] as String? ?? '',
      price: (json['price'] as num).toDouble(),
      featured: json['featured'] == true,
      category: json['category'] as String? ?? 'brownies',
      available: json['available'] != false,
      imageUrl: json['image_url'] as String?,
      stock: (json['stock'] as num?)?.toInt(),
      options: _parseOptions(json['options']),
    );
  }

  static List<ProductOption> _parseOptions(Object? raw) {
    if (raw is! List) return const [];
    return raw
        .whereType<Map<String, dynamic>>()
        .map(ProductOption.fromJson)
        .toList();
  }

  final int id;
  final String name;
  final String description;
  final double price;
  final bool featured;
  final String category;
  final bool available;
  final String? imageUrl;

  /// Unidades em estoque; nulo significa sem controle de estoque.
  final int? stock;

  /// Tamanhos e adicionais cadastrados no painel (vazio = sem variações).
  final List<ProductOption> options;

  List<ProductOption> get sizeOptions =>
      options.where((option) => option.isSize).toList();

  List<ProductOption> get addonOptions =>
      options.where((option) => !option.isSize).toList();

  /// Esgotado: há controle de estoque e nada sobrou.
  bool get soldOut => stock != null && stock! <= 0;

  /// Pode entrar no carrinho agora.
  bool get canBuy => available && !soldOut;

  String get formattedPrice => 'R\$ ${price.toStringAsFixed(2).replaceAll('.', ',')}';

  bool matchesCategory(String filter) {
    if (filter == 'todos') return true;
    return category == filter;
  }
}
