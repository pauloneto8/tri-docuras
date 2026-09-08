import 'package:test/test.dart';
import 'package:tri_docuras_api/whatsapp_notify.dart';

void main() {
  group('buildStorePaidOrderMessage', () {
    test('inclui dados do pedido', () {
      final message = buildStorePaidOrderMessage(
        publicId: 'TD-0013',
        customerName: 'Maria Silva',
        whatsapp: '81991234567',
        deliveryLabel: 'Retirada',
        total: 24.0,
        itemLines: ['2× Brownie Tradicional — R\$ 24,00'],
      );

      expect(message, contains('TD-0013'));
      expect(message, contains('Maria Silva'));
      expect(message, contains('81991234567'));
      expect(message, contains('Retirada'));
      expect(message, contains('R\$ 24,00'));
      expect(message, contains('Brownie Tradicional'));
    });
  });

  group('formatMoneyBrl', () {
    test('formata com vírgula', () {
      expect(formatMoneyBrl(12.5), 'R\$ 12,50');
    });
  });
}
