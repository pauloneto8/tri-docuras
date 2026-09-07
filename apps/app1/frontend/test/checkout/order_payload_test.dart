import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/cart/cart_item.dart';
import 'package:tri_docuras/cart/delivery_mode.dart';
import 'package:tri_docuras/checkout/checkout_draft.dart';
import 'package:tri_docuras/checkout/delivery_address.dart';
import 'package:tri_docuras/checkout/order_payload.dart';
import 'package:tri_docuras/models/product.dart';

void main() {
  test('buildCreateOrderPayload inclui itens e entrega', () {
    const product = Product(
      id: 4,
      name: 'Brownie Tradicional',
      description: 'Test',
      price: 12,
      featured: true,
      category: 'brownies',
    );
    final draft = CheckoutDraft(
      customerName: 'Maria Silva',
      whatsappDigits: '81991234567',
      total: 30,
      deliveryMode: DeliveryMode.delivery,
      deliveryAddress: const DeliveryAddress(
        street: 'Rua A',
        number: '10',
        neighborhood: 'Centro',
        reference: 'Próximo à praça',
      ),
    );

    final payload = buildCreateOrderPayload(
      draft: draft,
      items: [
        CartItem(product: product, quantity: 2, size: '9x9cm', lactoseFree: true),
      ],
    );

    expect(payload['customer_name'], 'Maria Silva');
    expect(payload['whatsapp'], '81991234567');
    expect(payload['delivery_mode'], 'delivery');
    expect(payload['delivery_address'], isNotNull);
    final items = payload['items'] as List<dynamic>;
    expect(items, hasLength(1));
    expect(items.first['product_id'], 4);
    expect(items.first['quantity'], 2);
    expect(items.first['size'], '9x9cm');
    expect(items.first['lactose_free'], isTrue);
  });

  test('buildCreateOrderPayload omite endereço na retirada', () {
    final draft = CheckoutDraft(
      customerName: 'João',
      whatsappDigits: '81991234567',
      total: 12,
      deliveryMode: DeliveryMode.pickup,
    );

    final payload = buildCreateOrderPayload(
      draft: draft,
      items: [
        CartItem(
          product: const Product(
            id: 4,
            name: 'Brownie',
            description: '',
            price: 12,
            featured: false,
            category: 'brownies',
          ),
          quantity: 1,
        ),
      ],
    );

    expect(payload['delivery_mode'], 'pickup');
    expect(payload.containsKey('delivery_address'), isFalse);
  });
}
