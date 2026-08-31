import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/cart/cart_controller.dart';
import 'package:tri_docuras/cart/cart_item.dart';
import 'package:tri_docuras/cart/delivery_mode.dart';
import 'package:tri_docuras/models/product.dart';

void main() {
  group('CartController delivery fee', () {
    late CartController cart;

    setUp(() => cart = CartController());

    test('retirada na loja sem taxa', () {
      expect(cart.deliveryMode, DeliveryMode.pickup);
      expect(cart.deliveryFee, 0);
      expect(cart.deliveryFeeLabel, 'Grátis');
    });

    test('receber em casa com taxa de R\$ 6,00', () {
      cart.setDeliveryMode(DeliveryMode.delivery);
      expect(cart.deliveryFee, CartController.deliveryFeeAmount);
      expect(cart.deliveryFeeLabel, 'R\$ 6,00');
    });

    test('total inclui taxa de entrega', () {
      cart.setDeliveryMode(DeliveryMode.delivery);
      expect(cart.total, cart.subtotal + 6);
    });

    test('removeAt remove item pelo índice', () {
      const product = Product(
        id: 1,
        name: 'Brownie',
        description: 'Test',
        price: 12,
        featured: false,
        category: 'brownies',
      );
      cart.add(CartItem(product: product, quantity: 2));
      expect(cart.itemCount, 2);
      cart.removeAt(0);
      expect(cart.items.isEmpty);
      expect(cart.itemCount, 0);
    });
  });
}
