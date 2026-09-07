import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/models/created_order.dart';

void main() {
  test('CreatedOrder.fromJson parseia pedido com Pix', () {
    final order = CreatedOrder.fromJson({
      'order': {
        'id': 'TD-0042',
        'status': 'pending_payment',
        'subtotal': 24.0,
        'delivery_fee': 0.0,
        'total': 24.0,
      },
      'pix': {
        'payment_id': 123,
        'copy_code': '00020126',
        'qr_code_base64': 'aGVsbG8=',
        'expires_at': '2026-09-07T12:00:00.000Z',
        'status': 'pending',
      },
    });

    expect(order.id, 'TD-0042');
    expect(order.pix?.copyCode, '00020126');
    expect(order.pix?.hasQrImage, isTrue);
  });

  test('OrderStatus.isPaid', () {
    final paid = OrderStatus.fromJson({
      'order': {'id': 'TD-0001', 'status': 'paid'},
    });
    expect(paid.isPaid, isTrue);
  });
}
