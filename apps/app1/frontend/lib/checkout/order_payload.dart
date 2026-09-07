import 'package:tri_docuras/cart/cart_item.dart';
import 'package:tri_docuras/cart/delivery_mode.dart';
import 'package:tri_docuras/checkout/checkout_draft.dart';

Map<String, dynamic> buildCreateOrderPayload({
  required CheckoutDraft draft,
  required List<CartItem> items,
}) {
  return {
    'customer_name': draft.customerName,
    'whatsapp': draft.whatsappDigits,
    'delivery_mode': draft.deliveryMode == DeliveryMode.pickup
        ? 'pickup'
        : 'delivery',
    if (draft.deliveryAddress != null)
      'delivery_address': {
        'street': draft.deliveryAddress!.street,
        'number': draft.deliveryAddress!.number,
        if (draft.deliveryAddress!.complement != null &&
            draft.deliveryAddress!.complement!.isNotEmpty)
          'complement': draft.deliveryAddress!.complement,
        'neighborhood': draft.deliveryAddress!.neighborhood,
        'reference': draft.deliveryAddress!.reference,
      },
    'items': items
        .map(
          (item) => {
            'product_id': item.product.id,
            'quantity': item.quantity,
            if (item.size != null && item.size!.isNotEmpty) 'size': item.size,
            'lactose_free': item.lactoseFree,
          },
        )
        .toList(),
  };
}
