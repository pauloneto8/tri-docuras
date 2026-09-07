import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/models/order_tracking.dart';

void main() {
  test('OrderTracking.fromJson parseia timeline', () {
    final tracking = OrderTracking.fromJson({
      'order': {
        'id': 'TD-0009',
        'status': 'preparing',
        'status_label': 'Em preparo',
        'delivery_label': 'Retirada',
        'total': 24.0,
        'is_completed': false,
      },
      'timeline': [
        {'key': 'received', 'label': 'Pedido recebido', 'done': true, 'current': false},
        {'key': 'paid', 'label': 'Pagamento confirmado', 'done': true, 'current': false},
        {'key': 'preparing', 'label': 'Em preparo', 'done': true, 'current': true},
      ],
    });

    expect(tracking.id, 'TD-0009');
    expect(tracking.timeline, hasLength(3));
    expect(tracking.timeline.last.current, isTrue);
  });
}
