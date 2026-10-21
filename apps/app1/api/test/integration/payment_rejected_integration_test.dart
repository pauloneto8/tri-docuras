// Integração: precisa de DATABASE_URL (ver stock_integration_test.dart).
import 'dart:io';

import 'package:test/test.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/orders.dart';

final _skip = (Platform.environment['DATABASE_URL'] ?? '').isEmpty
    ? 'defina DATABASE_URL para rodar os testes de integração'
    : null;

void main() {
  group('pagamento recusado pelo Mercado Pago', skip: _skip, () {
    late int customerId;
    late int productId;

    setUpAll(() async {
      await initializeDatabase();
      final connection = await getConnection();
      final customer = await connection.execute(
        r'''
        INSERT INTO customers (email, password_hash, name, whatsapp)
        VALUES ('recusa-integracao@test.invalid', 'x', 'Cliente Recusa', '81999990000')
        ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
        RETURNING id;
        ''',
      );
      customerId = (customer.first.first as num).toInt();
      final product = await connection.execute(
        r'''
        INSERT INTO products (name, description, price, stock)
        VALUES ('Brownie de recusa (integração)', '', 10, 5)
        RETURNING id;
        ''',
      );
      productId = (product.first.first as num).toInt();
    });

    Future<String> pendingOrderWithPayment(int paymentId) async {
      final order = await createOrder(
        CreateOrderInput(
          customerName: 'Cliente Recusa',
          whatsapp: '81999990000',
          deliveryMode: 'pickup',
          items: [
            OrderItemInput(
              productId: productId,
              quantity: 1,
              unitPrice: 10,
              productName: 'Brownie de recusa (integração)',
            ),
          ],
          subtotal: 10,
          deliveryFee: 0,
          total: 10,
        ),
        customerId: customerId,
      );
      final publicId = order['id']! as String;
      final connection = await getConnection();
      await connection.execute(
        r'UPDATE orders SET mp_payment_id = $2 WHERE public_id = $1;',
        parameters: [publicId, paymentId],
      );
      return publicId;
    }

    Future<int> stock() async {
      final connection = await getConnection();
      final rows = await connection.execute(
        r'SELECT stock FROM products WHERE id = $1;',
        parameters: [productId],
      );
      return (rows.first.first! as num).toInt();
    }

    test('cancela o pedido, devolve o estoque e registra o motivo', () async {
      final publicId = await pendingOrderWithPayment(777001);
      final before = await stock();

      final updated = await markOrderPaymentRejected(
        publicId,
        paymentId: 777001,
        detail: 'rejected_high_risk',
      );

      expect(updated, isTrue);
      expect(await stock(), before + 1);
      final connection = await getConnection();
      final rows = await connection.execute(
        r'''
        SELECT o.status, e.note
        FROM orders o
        JOIN order_events e ON e.order_id = o.id AND e.to_status = 'cancelled'
        WHERE o.public_id = $1;
        ''',
        parameters: [publicId],
      );
      expect(rows.first[0], 'cancelled');
      expect(rows.first[1], contains('rejected_high_risk'));
    });

    test('ignora recusa de um pagamento que não é o atual do pedido', () async {
      final publicId = await pendingOrderWithPayment(777002);

      final updated = await markOrderPaymentRejected(
        publicId,
        paymentId: 999999,
      );

      expect(updated, isFalse);
      final order = await getOrderByPublicId(publicId);
      expect(order['status'], 'pending_payment');
    });
  });
}
