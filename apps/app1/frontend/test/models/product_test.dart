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

  test('indisponível continua sem compra, mesmo com estoque', () {
    final product = Product.fromJson(_json(stock: 5, available: false));
    expect(product.soldOut, isFalse);
    expect(product.canBuy, isFalse);
  });
}
