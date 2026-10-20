import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/legal/legal_texts.dart';
import 'package:tri_docuras/models/store_config.dart';

void main() {
  test('sellerText usa nome e documento quando configurados', () {
    const config = StoreConfig(
      appName: 'Tri Doçuras',
      sellerName: 'Maria Silva ME',
      sellerDocument: '12.345.678/0001-90',
    );
    expect(sellerText(config), 'Maria Silva ME, 12.345.678/0001-90');
  });

  test('sellerText cai no nome da loja sem configuração', () {
    const config = StoreConfig(appName: 'Tri Doçuras');
    expect(sellerText(config), 'a Tri Doçuras');
  });

  test('os Termos citam o prazo do Pix e o vendedor configurado', () {
    const config = StoreConfig(
      appName: 'Tri Doçuras',
      sellerName: 'Maria Silva ME',
    );
    final text = termsSections(config)
        .expand((section) => section.paragraphs)
        .join(' ');
    expect(text, contains('validade de 10 minutos'));
    expect(text, contains('Maria Silva ME'));
  });
}
