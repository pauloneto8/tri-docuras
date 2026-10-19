import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/models/store_config.dart';
import 'package:tri_docuras/services/store_config_repository.dart';
import 'package:tri_docuras/store_config_holder.dart';

void main() {
  test('fallback não embute número de WhatsApp', () {
    expect(StoreConfigFallback.fallback.storeWhatsApp, isNull);
    expect(StoreConfigFallback.fallback.storeWhatsAppDisplay, isNull);
  });

  test('sem número configurado, o link do comprovante é vazio', () {
    final url = StoreConfigHolder.instance.buildOrderWhatsAppUrl(
      orderId: 'TD-0001',
      customerName: 'Maria',
      formattedTotal: 'R\$ 12,00',
    );
    expect(url, isEmpty);
  });

  test('número vindo da API é usado no link wa.me', () {
    final config = StoreConfig.fromJson({
      'app_name': 'Tri Doçuras',
      'store_whatsapp': '5581999990000',
    });
    expect(config.whatsappForLink, '5581999990000');
  });
}
