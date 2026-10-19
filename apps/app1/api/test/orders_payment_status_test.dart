import 'package:test/test.dart';
import 'package:tri_docuras_api/orders.dart';

void main() {
  group('paymentConfirmableStatuses', () {
    test('só pedido aguardando Pix pode ser marcado como pago', () {
      expect(paymentConfirmableStatuses, ['pending_payment']);
    });

    test('notificação repetida não regride pedidos já avançados', () {
      for (final status in [
        'paid',
        'preparing',
        'ready',
        'completed',
        'cancelled',
      ]) {
        expect(paymentConfirmableStatuses, isNot(contains(status)));
      }
    });
  });
}
