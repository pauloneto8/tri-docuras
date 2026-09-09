import 'package:test/test.dart';
import 'package:tri_docuras_api/app_public_config.dart';

void main() {
  group('buildCustomerStoreWhatsAppUrl', () {
    test('monta link wa.me com mensagem', () {
      final url = buildCustomerStoreWhatsAppUrl(
        storeWhatsApp: '5581999887766',
        orderId: 'TD-0013',
        customerName: 'Maria',
        formattedTotal: 'R\$ 24,00',
      );

      expect(url, contains('wa.me/5581999887766'));
      expect(url, contains('TD-0013'));
      expect(url, contains('Maria'));
    });
  });
}
