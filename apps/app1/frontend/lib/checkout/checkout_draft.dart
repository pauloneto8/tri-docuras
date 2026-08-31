import 'package:tri_docuras/cart/delivery_mode.dart';
import 'package:tri_docuras/checkout/delivery_address.dart';
import 'package:tri_docuras/checkout/order_summary.dart';

/// Rascunho de checkout em memória — não persistir (PII).
class CheckoutDraft {
  const CheckoutDraft({
    required this.customerName,
    required this.whatsappDigits,
    required this.total,
    required this.deliveryMode,
    this.deliveryAddress,
  });

  /// Nome já sanitizado (trim + espaços normalizados).
  final String customerName;

  /// WhatsApp só dígitos (11).
  final String whatsappDigits;

  /// Total lido do [CartController] no momento do Gerar Pix.
  final double total;

  final DeliveryMode deliveryMode;

  /// Preenchido quando [deliveryMode] é entrega em casa.
  final DeliveryAddress? deliveryAddress;

  String get formattedTotal =>
      'R\$ ${total.toStringAsFixed(2).replaceAll('.', ',')}';

  OrderSummary toOrderSummary(String orderId) => OrderSummary(
        orderId: orderId,
        customerName: customerName,
        total: total,
        deliveryMode: deliveryMode,
        deliveryAddress: deliveryAddress,
      );
}
