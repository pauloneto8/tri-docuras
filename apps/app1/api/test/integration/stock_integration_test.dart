// Testes de integração: rodam contra um Postgres de verdade. Sem DATABASE_URL
// eles são pulados, e a suíte normal segue igual. No CI há um job próprio
// com um serviço Postgres (ver .github/workflows/app1-tests.yml).
import 'dart:io';

import 'package:test/test.dart';
import 'package:tri_docuras_api/admin_orders.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/orders.dart';

final _skip = (Platform.environment['DATABASE_URL'] ?? '').isEmpty
    ? 'defina DATABASE_URL para rodar os testes de integração'
    : null;

CreateOrderInput _pickupOrder({
  required int productId,
  required String productName,
  required double price,
}) {
  return CreateOrderInput(
    customerName: 'Cliente Teste',
    whatsapp: '81999990000',
    deliveryMode: 'pickup',
    items: [
      OrderItemInput(
        productId: productId,
        quantity: 1,
        unitPrice: price,
        productName: productName,
      ),
    ],
    subtotal: price,
    deliveryFee: 0,
    total: price,
  );
}

void main() {
  group('estoque com Postgres real', skip: _skip, () {
    late int customerId;
    late int productId;
    const productName = 'Brownie de teste (integração)';
    const price = 10.0;

    Future<int?> stockOf(int id) async {
      final connection = await getConnection();
      final result = await connection.execute(
        r'SELECT stock FROM products WHERE id = $1;',
        parameters: [id],
      );
      final value = result.first.first;
      return value == null ? null : (value as num).toInt();
    }

    setUpAll(() async {
      await initializeDatabase();
      final connection = await getConnection();

      final customer = await connection.execute(
        r'''
        INSERT INTO customers (email, password_hash, name, whatsapp)
        VALUES ('estoque-integracao@test.invalid', 'x', 'Cliente Teste', '81999990000')
        ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
        RETURNING id;
        ''',
      );
      customerId = (customer.first.first as num).toInt();

      // Produto próprio dos testes, com uma única unidade em estoque.
      final product = await connection.execute(
        r'''
        INSERT INTO products (name, description, price, stock)
        VALUES ($1, '', $2, 1)
        RETURNING id;
        ''',
        parameters: [productName, price],
      );
      productId = (product.first.first as num).toInt();
    });

    test('pedidos simultâneos pela última unidade: um passa, o outro recusa',
        () async {
      final input = _pickupOrder(
        productId: productId,
        productName: productName,
        price: price,
      );

      final outcomes = await Future.wait([
        createOrder(input, customerId: customerId).then<Object>((order) => order)
            .catchError((Object error) => error),
        createOrder(input, customerId: customerId).then<Object>((order) => order)
            .catchError((Object error) => error),
      ]);

      expect(outcomes.whereType<Map<String, Object?>>(), hasLength(1));
      final failure = outcomes.whereType<OrderValidationException>().single;
      expect(failure.message, contains('Sem estoque'));
      expect(await stockOf(productId), 0);
    });

    test('cancelar pedido pendente devolve a unidade ao estoque', () async {
      // Repõe a unidade: o teste anterior deixou o produto sem estoque.
      final connection = await getConnection();
      await connection.execute(
        r'UPDATE products SET stock = 1 WHERE id = $1;',
        parameters: [productId],
      );

      final order = await createOrder(
        _pickupOrder(
          productId: productId,
          productName: productName,
          price: price,
        ),
        customerId: customerId,
      );
      expect(await stockOf(productId), 0);
      final publicId = order['id']! as String;

      await updateOrderStatus(publicId, 'cancelled', actor: 'teste-integracao');

      expect(await stockOf(productId), 1);
    });
  });
}
