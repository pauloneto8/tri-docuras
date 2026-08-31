import 'package:tri_docuras/cart/delivery_mode.dart';
import 'package:tri_docuras/checkout/delivery_address.dart';

/// Resumo do pedido confirmado — dados em memória, sem PII persistida.
class OrderSummary {
  const OrderSummary({
    required this.orderId,
    required this.customerName,
    required this.total,
    required this.deliveryMode,
    this.deliveryAddress,
  });

  final String orderId;
  final String customerName;
  final double total;
  final DeliveryMode deliveryMode;
  final DeliveryAddress? deliveryAddress;

  String get formattedTotal =>
      'R\$ ${total.toStringAsFixed(2).replaceAll('.', ',')}';

  String get deliveryLabel =>
      deliveryMode == DeliveryMode.pickup ? 'Retirada' : 'Entrega';

  String get deliveryDetail {
    if (deliveryMode == DeliveryMode.pickup) {
      return 'Hoje, 16h–17h';
    }
    if (deliveryAddress != null) {
      return deliveryAddress!.formattedSummary;
    }
    return 'Receber em casa · R\$ 6,00';
  }

  static String generateOrderId() {
    final suffix = DateTime.now().millisecondsSinceEpoch % 9000 + 1000;
    return 'TD-$suffix';
  }
}
