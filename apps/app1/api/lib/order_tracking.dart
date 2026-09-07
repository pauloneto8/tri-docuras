import 'package:tri_docuras_api/admin_orders.dart';
import 'package:tri_docuras_api/orders.dart';

const _statusOrder = [
  'pending_payment',
  'paid',
  'preparing',
  'ready',
  'completed',
];

Future<Map<String, Object?>> getOrderTracking(String publicId) async {
  final order = await getOrderByPublicId(publicId);
  if (order.isEmpty) {
    throw OrderValidationException('Pedido não encontrado.');
  }

  final status = order['status'] as String;
  final deliveryMode = order['delivery_mode'] as String;

  return {
    'order': {
      'id': order['id'],
      'status': status,
      'status_label': statusLabel(status, deliveryMode),
      'delivery_mode': deliveryMode,
      'delivery_label': deliveryMode == 'pickup' ? 'Retirada' : 'Entrega',
      'total': order['total'],
      'created_at': order['created_at']?.toString(),
      'paid_at': order['paid_at']?.toString(),
      'is_paid': status != 'pending_payment',
      'is_completed': status == 'completed',
    },
    'timeline': buildCustomerTimeline(status, deliveryMode),
  };
}

List<Map<String, Object?>> buildCustomerTimeline(
  String status,
  String deliveryMode,
) {
  final currentIndex = _statusOrder.indexOf(status);
  final steps = <Map<String, String>>[
    {'key': 'received', 'label': 'Pedido recebido'},
    {'key': 'paid', 'label': 'Pagamento confirmado'},
    {'key': 'preparing', 'label': 'Em preparo'},
    {
      'key': 'ready',
      'label': deliveryMode == 'pickup'
          ? 'Pronto para retirada'
          : 'Pronto para entrega',
    },
    {
      'key': 'completed',
      'label': deliveryMode == 'pickup' ? 'Retirado' : 'Entregue',
    },
  ];

  return List.generate(steps.length, (index) {
    final done = currentIndex >= 0 && index <= currentIndex;
    final current = currentIndex >= 0 && index == currentIndex;
    return {
      'key': steps[index]['key'],
      'label': steps[index]['label'],
      'done': done,
      'current': current,
    };
  });
}
