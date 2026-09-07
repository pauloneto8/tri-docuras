import 'package:postgres/postgres.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/orders.dart';

const adminOperationalStatuses = ['paid', 'preparing', 'ready'];
const adminAllStatuses = [
  'pending_payment',
  'paid',
  'preparing',
  'ready',
  'completed',
];

const _statusTransitions = <String, List<String>>{
  'paid': ['preparing', 'ready', 'completed'],
  'preparing': ['ready', 'completed'],
  'ready': ['completed'],
};

class AdminOrderException implements Exception {
  AdminOrderException(this.message);

  final String message;

  @override
  String toString() => message;
}

Future<List<Map<String, Object?>>> listOrdersForAdmin({
  String? status,
  int limit = 50,
}) async {
  final connection = await getConnection();
  final normalizedStatus = status?.trim();
  final parameters = <Object?>[limit];
  var whereClause = '';

  if (normalizedStatus != null && normalizedStatus.isNotEmpty) {
    if (normalizedStatus == 'active') {
      whereClause = "WHERE status = ANY(\$2::text[])";
      parameters.add(adminOperationalStatuses);
    } else if (normalizedStatus == 'queue') {
      whereClause = "WHERE status IN ('paid', 'preparing')";
    } else {
      whereClause = 'WHERE status = \$2';
      parameters.add(normalizedStatus);
    }
  }

  final result = await connection.execute(
    '''
    SELECT public_id, status, customer_name, whatsapp, delivery_mode,
           delivery_street, delivery_number, delivery_complement,
           delivery_neighborhood, delivery_reference,
           subtotal, delivery_fee, total, paid_at, created_at
    FROM orders
    $whereClause
    ORDER BY created_at DESC
    LIMIT \$1;
    ''',
    parameters: parameters,
  );

  final orders = result.map(_rowToAdminOrderMap).toList();
  for (final order in orders) {
    order['items'] = await _fetchItemsForPublicId(order['id'] as String);
  }
  return orders;
}

Future<Map<String, Object?>> updateOrderStatus(
  String publicId,
  String nextStatus,
) async {
  final normalized = nextStatus.trim();
  if (!adminAllStatuses.contains(normalized)) {
    throw AdminOrderException('Status inválido.');
  }

  final order = await getOrderByPublicId(publicId);
  if (order.isEmpty) {
    throw AdminOrderException('Pedido não encontrado.');
  }

  final current = order['status'] as String;
  if (current == 'pending_payment') {
    throw AdminOrderException('Aguarde a confirmação do pagamento Pix.');
  }
  if (current == 'completed') {
    throw AdminOrderException('Este pedido já foi concluído.');
  }
  if (current == normalized) {
    return orderToAdminJson(order, await _fetchItemsForPublicId(publicId));
  }

  final allowed = _statusTransitions[current];
  if (allowed == null || !allowed.contains(normalized)) {
    throw AdminOrderException(
      'Não é possível alterar de "$current" para "$normalized".',
    );
  }

  final connection = await getConnection();
  final result = await connection.execute(
    '''
    UPDATE orders
    SET status = \$2
    WHERE public_id = \$1
    RETURNING public_id, status, customer_name, whatsapp, delivery_mode,
              delivery_street, delivery_number, delivery_complement,
              delivery_neighborhood, delivery_reference,
              subtotal, delivery_fee, total, paid_at, created_at;
    ''',
    parameters: [publicId, normalized],
  );

  if (result.isEmpty) {
    throw AdminOrderException('Pedido não encontrado.');
  }

  final updated = _rowToAdminOrderMap(result.first);
  final items = await _fetchItemsForPublicId(publicId);
  return orderToAdminJson(updated, items);
}

Future<List<Map<String, Object?>>> _fetchItemsForPublicId(
  String publicId,
) async {
  final connection = await getConnection();
  final result = await connection.execute(
    '''
    SELECT oi.product_name, oi.quantity, oi.unit_price, oi.size,
           oi.lactose_free, oi.line_total
    FROM order_items oi
    JOIN orders o ON o.id = oi.order_id
    WHERE o.public_id = \$1
    ORDER BY oi.id ASC;
    ''',
    parameters: [publicId],
  );

  return result
      .map(
        (row) => {
          'product_name': row[0],
          'quantity': (row[1] as num).toInt(),
          'unit_price': _toDouble(row[2]),
          'size': row[3],
          'lactose_free': row[4] == true,
          'line_total': _toDouble(row[5]),
        },
      )
      .toList();
}

Map<String, Object?> _rowToAdminOrderMap(ResultRow row) {
  return {
    'id': row[0],
    'status': row[1],
    'customer_name': row[2],
    'whatsapp': row[3],
    'delivery_mode': row[4],
    'delivery_street': row[5],
    'delivery_number': row[6],
    'delivery_complement': row[7],
    'delivery_neighborhood': row[8],
    'delivery_reference': row[9],
    'subtotal': _toDouble(row[10]),
    'delivery_fee': _toDouble(row[11]),
    'total': _toDouble(row[12]),
    'paid_at': row[13],
    'created_at': row[14],
  };
}

Map<String, Object?> orderToAdminJson(
  Map<String, Object?> order,
  List<Map<String, Object?>> items,
) {
  final deliveryMode = order['delivery_mode'] as String;
  final address = deliveryMode == 'delivery'
      ? {
          'street': order['delivery_street'],
          'number': order['delivery_number'],
          'complement': order['delivery_complement'],
          'neighborhood': order['delivery_neighborhood'],
          'reference': order['delivery_reference'],
        }
      : null;

  return {
    'id': order['id'],
    'status': order['status'],
    'status_label': statusLabel(order['status'] as String, deliveryMode),
    'customer_name': order['customer_name'],
    'whatsapp': order['whatsapp'],
    'whatsapp_link': whatsappLink(order['whatsapp'] as String),
    'delivery_mode': deliveryMode,
    'delivery_label': deliveryMode == 'pickup' ? 'Retirada' : 'Entrega',
    'delivery_address': address,
    'subtotal': order['subtotal'],
    'delivery_fee': order['delivery_fee'],
    'total': order['total'],
    'paid_at': order['paid_at']?.toString(),
    'created_at': order['created_at']?.toString(),
    'items': items,
    'next_actions': nextActionsFor(
      order['status'] as String,
      deliveryMode,
    ),
  };
}

String statusLabel(String status, String deliveryMode) {
  switch (status) {
    case 'pending_payment':
      return 'Aguardando Pix';
    case 'paid':
      return 'Pago — na fila';
    case 'preparing':
      return 'Em preparo';
    case 'ready':
      return deliveryMode == 'pickup' ? 'Pronto para retirada' : 'Pronto para entrega';
    case 'completed':
      return deliveryMode == 'pickup' ? 'Retirado' : 'Entregue';
    default:
      return status;
  }
}

List<Map<String, String>> nextActionsFor(String status, String deliveryMode) {
  final allowed = _statusTransitions[status] ?? const <String>[];
  return allowed
      .map(
        (value) => {
          'status': value,
          'label': actionLabel(value, deliveryMode),
        },
      )
      .toList();
}

String actionLabel(String status, String deliveryMode) {
  switch (status) {
    case 'preparing':
      return 'Marcar em preparo';
    case 'ready':
      return deliveryMode == 'pickup'
          ? 'Marcar pronto para retirada'
          : 'Marcar pronto para entrega';
    case 'completed':
      return deliveryMode == 'pickup' ? 'Confirmar retirada' : 'Confirmar entrega';
    default:
      return status;
  }
}

String whatsappLink(String digits) => 'https://wa.me/55$digits';

double _toDouble(Object? value) => switch (value) {
      final num n => n.toDouble(),
      final String s => double.parse(s),
      _ => 0.0,
    };
