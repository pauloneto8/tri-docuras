import 'package:tri_docuras/models/product.dart';
import 'package:tri_docuras/models/product_option.dart';

class CartItem {
  const CartItem({
    required this.product,
    required this.quantity,
    this.options = const [],
  });

  final Product product;
  final int quantity;

  /// Tamanho e adicionais escolhidos, na ordem do cadastro.
  final List<ProductOption> options;

  double get extraPrice =>
      options.fold<double>(0, (sum, option) => sum + option.priceDelta);

  double get unitPrice => product.price + extraPrice;

  double get lineTotal => unitPrice * quantity;

  List<int> get optionIds => [for (final option in options) option.id];

  /// Texto das escolhas, ex.: `9x9cm · Sem lactose`; nulo sem escolhas.
  String? get optionsLabel => options.isEmpty
      ? null
      : options.map((option) => option.label).join(' · ');

  String get formattedUnitPrice =>
      'R\$ ${unitPrice.toStringAsFixed(2).replaceAll('.', ',')}';

  String get formattedLineTotal =>
      'R\$ ${lineTotal.toStringAsFixed(2).replaceAll('.', ',')}';

  CartItem copyWith({int? quantity}) {
    return CartItem(
      product: product,
      quantity: quantity ?? this.quantity,
      options: options,
    );
  }
}
