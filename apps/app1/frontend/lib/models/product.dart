class Product {
  const Product({
    required this.id,
    required this.name,
    required this.description,
    required this.price,
    required this.featured,
    required this.category,
    this.available = true,
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
    );
  }

  final int id;
  final String name;
  final String description;
  final double price;
  final bool featured;
  final String category;
  final bool available;

  String get formattedPrice => 'R\$ ${price.toStringAsFixed(2).replaceAll('.', ',')}';

  bool matchesCategory(String filter) {
    if (filter == 'todos') return true;
    return category == filter;
  }
}
