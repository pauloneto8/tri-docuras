import 'package:test/test.dart';
import 'package:tri_docuras_api/admin_products.dart';

void main() {
  group('parseProductInput', () {
    test('aceita payload válido', () {
      final input = parseProductInput({
        'name': 'Brownie Especial',
        'description': 'Com cobertura',
        'price': 18.5,
        'featured': true,
        'category': 'brownies',
        'available': true,
      });

      expect(input.name, 'Brownie Especial');
      expect(input.price, 18.5);
      expect(input.category, 'brownies');
      expect(input.featured, isTrue);
    });

    test('rejeita nome vazio', () {
      expect(
        () => parseProductInput({'name': '', 'price': 10, 'category': 'brownies'}),
        throwsA(isA<AdminProductException>()),
      );
    });

    test('rejeita preço inválido', () {
      expect(
        () => parseProductInput({
          'name': 'Teste',
          'price': 0,
          'category': 'brownies',
        }),
        throwsA(isA<AdminProductException>()),
      );
    });

    test('rejeita categoria vazia', () {
      expect(
        () => parseProductInput({
          'name': 'Teste',
          'price': 12,
          'category': '',
        }),
        throwsA(isA<AdminProductException>()),
      );
    });

    test('rejeita categoria com formato inválido', () {
      expect(
        () => parseProductInput({
          'name': 'Teste',
          'price': 12,
          'category': 'Doces Especiais',
        }),
        throwsA(isA<AdminProductException>()),
      );
    });

    test('aceita slug de categoria novo', () {
      final input = parseProductInput({
        'name': 'Teste',
        'price': 12,
        'category': 'bolos-caseiros',
      });
      expect(input.category, 'bolos-caseiros');
    });
  });

  group('productToAdminJson', () {
    test('formata labels', () {
      final json = productToAdminJson({
        'id': 1,
        'name': 'Brownie',
        'description': '',
        'price': 12.0,
        'featured': false,
        'category': 'brownies',
        'available': false,
      });

      expect(json['category_label'], 'Brownies');
      expect(json['availability_label'], 'Oculto');
    });
  });
}
