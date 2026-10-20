import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/cart/cart_item.dart';
import 'package:tri_docuras/models/product.dart';
import 'package:tri_docuras/models/product_option.dart';

void main() {
  const product = Product(
    id: 1,
    name: 'Brownie',
    description: '',
    price: 12,
    featured: false,
    category: 'brownies',
  );

  test('sem opções, o preço é o do produto', () {
    const item = CartItem(product: product, quantity: 2);
    expect(item.unitPrice, 12);
    expect(item.optionIds, isEmpty);
    expect(item.optionsLabel, isNull);
  });

  test('adicionais somam ao preço e tamanho entra no rótulo', () {
    const item = CartItem(
      product: product,
      quantity: 2,
      options: [
        ProductOption(id: 10, kind: 'size', label: '9x9cm'),
        ProductOption(id: 12, kind: 'addon', label: 'Sem lactose', priceDelta: 3),
      ],
    );
    expect(item.unitPrice, 15);
    expect(item.lineTotal, 30);
    expect(item.optionIds, [10, 12]);
    expect(item.optionsLabel, '9x9cm · Sem lactose');
  });

  test('copyWith mantém as opções ao trocar a quantidade', () {
    const item = CartItem(
      product: product,
      quantity: 1,
      options: [ProductOption(id: 10, kind: 'size', label: 'Fatia grande')],
    );
    final updated = item.copyWith(quantity: 4);
    expect(updated.quantity, 4);
    expect(updated.optionIds, [10]);
  });

  test('chip de adicional mostra o preço quando ele é maior que zero', () {
    const addon = ProductOption(id: 12, kind: 'addon', label: 'Sem lactose', priceDelta: 3);
    const free = ProductOption(id: 13, kind: 'addon', label: 'Cobertura');
    const decimal = ProductOption(id: 14, kind: 'addon', label: 'Extra', priceDelta: 2.5);
    expect(addon.chipLabel, 'Sem lactose +R\$3');
    expect(free.chipLabel, 'Cobertura');
    expect(decimal.chipLabel, 'Extra +R\$2,50');
  });
}
