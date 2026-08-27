import 'package:tri_docuras/models/product.dart';

class CartItem {
  const CartItem({
    required this.product,
    required this.quantity,
    this.size,
    this.lactoseFree = false,
  });

  final Product product;
  final int quantity;
  final String? size;
  final bool lactoseFree;

  static const lactoseExtraPrice = 3.0;

  double get unitPrice => product.price + (lactoseFree ? lactoseExtraPrice : 0);

  double get lineTotal => unitPrice * quantity;

  String get formattedUnitPrice =>
      'R\$ ${unitPrice.toStringAsFixed(2).replaceAll('.', ',')}';

  String get formattedLineTotal =>
      'R\$ ${lineTotal.toStringAsFixed(2).replaceAll('.', ',')}';

  CartItem copyWith({int? quantity}) {
    return CartItem(
      product: product,
      quantity: quantity ?? this.quantity,
      size: size,
      lactoseFree: lactoseFree,
    );
  }
}
