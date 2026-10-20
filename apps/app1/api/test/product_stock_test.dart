import 'package:test/test.dart';
import 'package:tri_docuras_api/admin_products.dart';

Map<String, dynamic> _product({Object? stock = ''}) => {
      'name': 'Brownie',
      'price': 12,
      'category': 'brownies',
      'stock': stock,
    };

void main() {
  group('parseProductInput (estoque)', () {
    test('vazio significa sem controle de estoque', () {
      expect(parseProductInput(_product()).stock, isNull);
      expect(parseProductInput(_product(stock: null)).stock, isNull);
    });

    test('aceita zero e números inteiros', () {
      expect(parseProductInput(_product(stock: 0)).stock, 0);
      expect(parseProductInput(_product(stock: '12')).stock, 12);
    });

    test('recusa negativo, decimal, texto e acima do limite', () {
      for (final bad in [-1, '3,5', 'dez', maxStock + 1]) {
        expect(
          () => parseProductInput(_product(stock: bad)),
          throwsA(isA<AdminProductException>()),
          reason: 'valor $bad',
        );
      }
    });
  });
}
