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
    );
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
