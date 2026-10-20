import 'package:test/test.dart';
import 'package:tri_docuras_api/admin_products.dart';
import 'package:tri_docuras_api/product_options.dart';

const _productName = 'Ninho c/ Nutella';

ProductOptionRow _row(int id, String kind, String label, double price, int sort) {
  return ProductOptionRow(
    id: id,
    productId: 1,
    kind: kind,
    label: label,
    priceDelta: price,
    sortOrder: sort,
  );
}

final _brownie = [
  _row(10, 'size', '9x9cm', 0, 1),
  _row(11, 'size', 'Fatia grande', 0, 2),
  _row(12, 'addon', 'Sem lactose', 3, 3),
];

Map<String, dynamic> _product({List<Object?>? options}) => {
      'name': 'Brownie',
      'price': 12,
      'category': 'brownies',
      if (options != null) 'options': options,
    };

void main() {
  group('resolveProductOptions', () {
    test('um tamanho, sem adicional: preço base e rótulo do tamanho', () {
      final resolved = resolveProductOptions(
        productName: _productName,
        selectedIds: [11],
        available: _brownie,
      );
      expect(resolved.extraPrice, 0);
      expect(resolved.label, 'Fatia grande');
      expect(resolved.ids, [11]);
    });

    test('tamanho e adicional somam o preço e aparecem no rótulo', () {
      final resolved = resolveProductOptions(
        productName: _productName,
        selectedIds: [12, 10],
        available: _brownie,
      );
      expect(resolved.extraPrice, 3);
      expect(resolved.label, '9x9cm$optionLabelSeparator'
          'Sem lactose');
    });

    test('produto com tamanhos exige exatamente um', () {
      expect(
        () => resolveProductOptions(
          productName: _productName,
          selectedIds: [12],
          available: _brownie,
        ),
        throwsA(isA<ProductOptionException>()),
      );
      expect(
        () => resolveProductOptions(
          productName: _productName,
          selectedIds: [10, 11],
          available: _brownie,
        ),
        throwsA(isA<ProductOptionException>()),
      );
    });

    test('produto sem variações aceita nenhuma escolha', () {
      final resolved = resolveProductOptions(
        productName: 'Caixa',
        selectedIds: const [],
        available: const [],
      );
      expect(resolved.extraPrice, 0);
      expect(resolved.label, isNull);
    });

    test('opção de outro produto ou inativa é recusada', () {
      expect(
        () => resolveProductOptions(
          productName: _productName,
          selectedIds: [10, 99],
          available: _brownie,
        ),
        throwsA(isA<ProductOptionException>()),
      );
    });

    test('opção repetida é recusada', () {
      expect(
        () => resolveProductOptions(
          productName: _productName,
          selectedIds: [10, 10],
          available: _brownie,
        ),
        throwsA(isA<ProductOptionException>()),
      );
    });
  });

  group('parseProductInput (variações)', () {
    test('sem a chave options não mexe nas variações', () {
      expect(parseProductInput(_product()).options, isNull);
    });

    test('lê tipo, nome, preço e ordem, e converte preço com vírgula', () {
      final input = parseProductInput(_product(options: [
        {'kind': 'size', 'label': '9x9cm'},
        {'id': 12, 'kind': 'addon', 'label': 'Sem lactose', 'price_delta': '3,5'},
      ]));
      final options = input.options!;
      expect(options.length, 2);
      expect(options[0].kind, 'size');
      expect(options[0].priceDelta, 0);
      expect(options[0].sortOrder, 1);
      expect(options[1].id, 12);
      expect(options[1].priceDelta, 3.5);
      expect(options[1].sortOrder, 2);
    });

    test('recusa tipo, nome e preço inválidos', () {
      final bad = <Map<String, Object?>>[
        {'kind': 'cobertura', 'label': 'Nutella'},
        {'kind': 'addon', 'label': '   '},
        {'kind': 'addon', 'label': 'Extra', 'price_delta': -1},
        {'kind': 'addon', 'label': 'Extra', 'price_delta': 1000},
      ];
      for (final option in bad) {
        expect(
          () => parseProductInput(_product(options: [option])),
          throwsA(isA<AdminProductException>()),
          reason: 'opção $option',
        );
      }
    });

    test('recusa mais de $maxProductOptions variações', () {
      final tooMany = [
        for (var i = 0; i <= maxProductOptions; i++)
          {'kind': 'addon', 'label': 'Extra $i'},
      ];
      expect(
        () => parseProductInput(_product(options: tooMany)),
        throwsA(isA<AdminProductException>()),
      );
    });
  });
}
