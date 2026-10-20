import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/models/product.dart';

Map<String, dynamic> _json({Object? stock, bool available = true}) => {
      'id': 1,
      'name': 'Brownie',
      'price': 12,
      'category': 'brownies',
      'available': available,
      'stock': stock,
    };

void main() {
  test('sem estoque informado, o produto não está esgotado', () {
    final product = Product.fromJson(_json());
    expect(product.stock, isNull);
    expect(product.soldOut, isFalse);
    expect(product.canBuy, isTrue);
  });

  test('estoque zero está esgotado e não pode ser comprado', () {
    final product = Product.fromJson(_json(stock: 0));
    expect(product.soldOut, isTrue);
    expect(product.canBuy, isFalse);
  });

  test('estoque positivo pode ser comprado', () {
    final product = Product.fromJson(_json(stock: 3));
    expect(product.stock, 3);
    expect(product.canBuy, isTrue);
  });

  test('lê as variações e separa tamanhos de adicionais', () {
    final product = Product.fromJson({
      ..._json(),
      'options': [
        {'id': 10, 'kind': 'size', 'label': '9x9cm', 'price_delta': 0},
        {'id': 12, 'kind': 'addon', 'label': 'Sem lactose', 'price_delta': 3},
      ],
    });
    expect(product.options.length, 2);
    expect(product.sizeOptions.map((o) => o.id), [10]);
    expect(product.addonOptions.map((o) => o.id), [12]);
  });

  test('produto sem a chave options não tem variações', () {
    expect(Product.fromJson(_json()).options, isEmpty);
  });

  test('indisponível continua sem compra, mesmo com estoque', () {
    final product = Product.fromJson(_json(stock: 5, available: false));
    expect(product.soldOut, isFalse);
    expect(product.canBuy, isFalse);
  });
}
