import 'package:tri_docuras/cart/delivery_mode.dart';

/// Resumo do pedido confirmado — dados em memória, sem PII persistida.
class OrderSummary {
  const OrderSummary({
    required this.orderId,
    required this.customerName,
    required this.total,
    required this.deliveryMode,
  });

  final String orderId;
  final String customerName;
  final double total;
  final DeliveryMode deliveryMode;

  String get formattedTotal =>
      'R\$ ${total.toStringAsFixed(2).replaceAll('.', ',')}';

  String get deliveryLabel =>
      deliveryMode == DeliveryMode.pickup ? 'Retirada' : 'Entrega';

  String get deliveryDetail =>
      deliveryMode == DeliveryMode.pickup
          ? 'Hoje, 16h–17h'
          : 'Receber em casa · Grátis';

  static String generateOrderId() {
    final suffix = DateTime.now().millisecondsSinceEpoch % 9000 + 1000;
    return 'TD-$suffix';
  }
}
