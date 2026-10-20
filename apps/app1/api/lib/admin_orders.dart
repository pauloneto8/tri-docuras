import 'dart:io';

import 'package:postgres/postgres.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/order_events.dart';
import 'package:tri_docuras_api/mercado_pago_client.dart';
import 'package:tri_docuras_api/orders.dart';
import 'package:tri_docuras_api/tracking_token.dart';

const adminOperationalStatuses = ['paid', 'preparing', 'ready'];
const adminAllStatuses = [
  'pending_payment',
  'paid',
  'preparing',
  'ready',
  'completed',
  'cancelled',
  'expired',
];

const _statusTransitions = <String, List<String>>{
  'pending_payment': ['cancelled'],
  'paid': ['preparing', 'ready', 'completed', 'cancelled'],
  'preparing': ['ready', 'completed', 'cancelled'],
  'ready': ['completed', 'cancelled'],
};

enum CancelRefundPlan { notNeeded, refund, skipRefund }

/// Decide o que fazer com o dinheiro ao cancelar um pedido. Pedido já pago
/// (ou em preparo/pronto) exige escolha explícita: estornar ou não.
CancelRefundPlan cancelRefundPlan(String current, bool? refund) {
  const paidStatuses = {'paid', 'preparing', 'ready'};
  if (!paidStatuses.contains(current)) return CancelRefundPlan.notNeeded;
  if (refund == null) {
    throw AdminOrderException(
      'Pedido já pago: informe se o valor deve ser estornado ao cliente.',
    );
  }
  return refund ? CancelRefundPlan.refund : CancelRefundPlan.skipRefund;
}

class AdminOrderException implements Exception {
  AdminOrderException(this.message);

  final String message;

  @override
  String toString() => message;
}

Future<List<Map<String, Object?>>> listOrdersForAdmin({
  String? status,
  String? search,
  String? from,
  String? to,
  int limit = 50,
}) async {
  final connection = await getConnection();
  final normalizedStatus = status?.trim();
  final conditions = <String>[];
  final parameters = <Object?>[];

  if (normalizedStatus != null && normalizedStatus.isNotEmpty) {
    if (normalizedStatus == 'active') {
      parameters.add(adminOperationalStatuses);
      conditions.add('status = ANY(\$${parameters.length}::text[])');
    } else if (normalizedStatus == 'queue') {
      conditions.add("status IN ('paid', 'preparing')");
    } else if (adminAllStatuses.contains(normalizedStatus)) {
      parameters.add(normalizedStatus);
      conditions.add('status = \$${parameters.length}');
    } else {
      throw AdminOrderException('Status inválido: $normalizedStatus.');
    }
  }

  final normalizedSearch = search?.trim();
  if (normalizedSearch != null && normalizedSearch.isNotEmpty) {
    parameters.add('%$normalizedSearch%');
    final index = parameters.length;
    conditions.add('(public_id ILIKE \$$index OR customer_name ILIKE \$$index)');
  }

  final fromDate = _parseDate(from);
  final toDate = _parseDate(to);
  if (fromDate != null || toDate != null) {
    final start = fromDate ?? DateTime(2000, 1, 1);
    final end = toDate ?? DateTime.now();
    if (start.isAfter(end)) {
      throw AdminOrderException('A data inicial não pode ser depois da final.');
    }
    parameters.add(start);
    conditions.add('created_at >= \$${parameters.length}');
    parameters.add(end.add(const Duration(days: 1)));
    conditions.add('created_at < \$${parameters.length}');
  }

  final whereClause =
      conditions.isEmpty ? '' : 'WHERE ${conditions.join(' AND ')}';
  parameters.add(limit);

  final result = await connection.execute(
    '''
    SELECT public_id, status, customer_name, whatsapp, delivery_mode,
           delivery_street, delivery_number, delivery_complement,
           delivery_neighborhood, delivery_reference,
           subtotal, delivery_fee, total, paid_at, created_at,
           refund_status, refunded_at, tracking_token,
           orders.customer_id IS NOT NULL AS has_account,
           (SELECT email FROM customers WHERE id = orders.customer_id) AS customer_email
    FROM orders
    $whereClause
    ORDER BY created_at DESC
    LIMIT \$${parameters.length};
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
  String nextStatus, {
  bool? refund,
  required String actor,
}) async {
  final normalized = nextStatus.trim();
  if (!adminAllStatuses.contains(normalized)) {
    throw AdminOrderException('Status inválido.');
  }

  final order = await getOrderByPublicId(publicId);
  if (order.isEmpty) {
    throw AdminOrderException('Pedido não encontrado.');
  }

  final current = order['status'] as String;
  if (current == 'completed') {
    throw AdminOrderException('Este pedido já foi concluído.');
  }
  if (current == 'cancelled') {
    throw AdminOrderException('Este pedido já foi cancelado.');
  }
  if (current == 'expired') {
    throw AdminOrderException('Este pedido expirou por falta de pagamento.');
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

  final plan = normalized == 'cancelled'
      ? cancelRefundPlan(current, refund)
      : CancelRefundPlan.notNeeded;

  String? refundStatus;
  String? mpRefundId;
  if (plan == CancelRefundPlan.refund) {
    final paymentId = order['mp_payment_id'] as int?;
    if (paymentId == null) {
      throw AdminOrderException(
        'Pedido sem pagamento Mercado Pago registrado: não há o que estornar.',
      );
    }
    final refunded = await _refundPix(publicId, paymentId);
    refundStatus = refunded.status;
    mpRefundId = refunded.id;
  } else if (plan == CancelRefundPlan.skipRefund) {
    refundStatus = 'not_refunded';
  }

  final connection = await getConnection();
  final result = await connection.runTx((tx) async {
    final current = await tx.execute(
      r'SELECT id, status FROM orders WHERE public_id = $1 FOR UPDATE;',
      parameters: [publicId],
    );
    if (current.isEmpty) return null;
    final orderId = current.first[0]! as int;
    final fromStatus = current.first[1]! as String;

    final updated = await tx.execute(
      '''
      UPDATE orders
      SET status = \$2,
          refund_status = COALESCE(\$3::text, refund_status),
          refunded_at = CASE WHEN \$3::text = 'refunded' THEN NOW() ELSE refunded_at END,
          mp_refund_id = COALESCE(\$4::text, mp_refund_id)
      WHERE public_id = \$1
      RETURNING public_id, status, customer_name, whatsapp, delivery_mode,
                delivery_street, delivery_number, delivery_complement,
                delivery_neighborhood, delivery_reference,
                subtotal, delivery_fee, total, paid_at, created_at,
                refund_status, refunded_at, tracking_token,
                customer_id IS NOT NULL AS has_account,
                (SELECT email FROM customers WHERE id = orders.customer_id) AS customer_email;
      ''',
      parameters: [publicId, normalized, refundStatus, mpRefundId],
    );

    await recordOrderEvent(
      tx,
      orderId: orderId,
      from: fromStatus,
      to: normalized,
      actor: actor,
      note: refundStatus == null ? null : 'estorno: $refundStatus',
    );
    if (normalized == 'cancelled') {
      await restockOrderItems(tx, orderId);
    }
    return updated;
  });

  if (result == null) {
    throw AdminOrderException('Pedido não encontrado.');
  }

  final updated = _rowToAdminOrderMap(result.first);
  final items = await _fetchItemsForPublicId(publicId);
  return orderToAdminJson(updated, items);
}

/// Estorna o Pix no Mercado Pago. Se o MP recusar, lança e o pedido não é
/// cancelado. Pode devolver `pending_refund` (estorno em análise).
Future<({String status, String id})> _refundPix(
  String publicId,
  int paymentId,
) async {
  try {
    final data = await MercadoPagoClient().refundPayment(
      paymentId,
      idempotencyKey: 'refund-$publicId',
    );
    final mpStatus = data['status']?.toString();
    if (mpStatus == 'approved') {
      return (status: 'refunded', id: '${data['id']}');
    }
    if (mpStatus == 'pending') {
      return (status: 'pending_refund', id: '${data['id']}');
    }
    throw AdminOrderException(
      'O Mercado Pago recusou o estorno ($mpStatus). O pedido não foi cancelado.',
    );
  } on MercadoPagoException catch (error) {
    stderr.writeln('[mp] estorno do pedido $publicId falhou: ${error.message}');
    throw AdminOrderException(
      'Não foi possível estornar: ${error.message} O pedido não foi cancelado.',
    );
  }
}

Future<List<Map<String, Object?>>> _fetchItemsForPublicId(
  String publicId,
) async {
  final connection = await getConnection();
  final result = await connection.execute(
    '''
    SELECT oi.product_name, oi.quantity, oi.unit_price, oi.size,
           oi.lactose_free, oi.line_total, oi.options
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
          'options': row[6],
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
    'refund_status': row[15],
    'refunded_at': row[16],
    'tracking_token': row[17] as String?,
    'has_account': row[18] == true,
    'customer_email': row[19] as String?,
  };
}

/// Link para o painel mandar ao cliente. Pedido sem token devolve `null`.
String? _trackingLink(Map<String, Object?> order) {
  final token = order['tracking_token'] as String?;
  if (token == null || token.isEmpty) return null;
  return trackingUrl(order['id']! as String, token);
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
    'refund_status': order['refund_status'],
    'refund_label': refundLabel(order['refund_status'] as String?),
    'customer_name': order['customer_name'],
    'whatsapp': order['whatsapp'],
    'whatsapp_link': whatsappLink(order['whatsapp'] as String),
    'tracking_link': _trackingLink(order),
    'customer_account': order['has_account'] == true
        ? {'email': order['customer_email']}
        : null,
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
    case 'cancelled':
      return 'Cancelado';
    case 'expired':
      return 'Expirado';
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
    case 'cancelled':
      return 'Cancelar pedido';
    default:
      return status;
  }
}

String? refundLabel(String? refundStatus) {
  switch (refundStatus) {
    case 'refunded':
      return 'Estornado';
    case 'pending_refund':
      return 'Estorno em análise';
    case 'not_refunded':
      return 'Cancelado sem estorno';
    default:
      return null;
  }
}

String whatsappLink(String digits) => 'https://wa.me/55$digits';

DateTime? _parseDate(String? value) {
  if (value == null || value.trim().isEmpty) return null;
  final parsed = DateTime.tryParse(value.trim());
  if (parsed == null) {
    throw AdminOrderException('Data inválida: use o formato AAAA-MM-DD.');
  }
  return DateTime(parsed.year, parsed.month, parsed.day);
}

double _toDouble(Object? value) => switch (value) {
      final num n => n.toDouble(),
      final String s => double.parse(s),
      _ => 0.0,
    };
