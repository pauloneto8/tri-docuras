// Integração: precisa de DATABASE_URL (ver stock_integration_test.dart).
import 'dart:io';

import 'package:test/test.dart';
import 'package:tri_docuras_api/customers.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/orders.dart';

final _skip = (Platform.environment['DATABASE_URL'] ?? '').isEmpty
    ? 'defina DATABASE_URL para rodar os testes de integração'
    : null;

const _password = 'senha-boa-1';

void main() {
  group('exclusão de conta com Postgres real', skip: _skip, () {
    late int productId;

    setUpAll(() async {
      await initializeDatabase();
      final connection = await getConnection();
      final product = await connection.execute(
        r'''
        INSERT INTO products (name, description, price)
        VALUES ('Brownie de exclusão (integração)', '', 10)
        RETURNING id;
        ''',
      );
      productId = (product.first.first as num).toInt();
    });

    Future<int> newCustomer() async {
      final email =
          'exclusao-${DateTime.now().microsecondsSinceEpoch}@test.invalid';
      final customer = await createCustomer(
        CustomerInput(
          email: email,
          password: _password,
          name: 'Cliente Exclusão',
          whatsapp: '81999990000',
        ),
      );
      return customer['id']! as int;
    }

    CreateOrderInput order() => CreateOrderInput(
          customerName: 'Cliente Exclusão',
          whatsapp: '81999990000',
          deliveryMode: 'pickup',
          items: [
            OrderItemInput(
              productId: productId,
              quantity: 1,
              unitPrice: 10,
              productName: 'Brownie de exclusão (integração)',
            ),
          ],
          subtotal: 10,
          deliveryFee: 0,
          total: 10,
        );

    test('recusa com pedido em andamento e com senha errada', () async {
      final customerId = await newCustomer();
      final created = await createOrder(order(), customerId: customerId);
      final publicId = created['id']! as String;

      await expectLater(
        deleteCustomerAccount(customerId, password: _password),
        throwsA(
          isA<CustomerException>().having((e) => e.statusCode, 'status', 409),
        ),
      );

      final connection = await getConnection();
      await connection.execute(
        r"UPDATE orders SET status = 'completed' WHERE public_id = $1;",
        parameters: [publicId],
      );
      await expectLater(
        deleteCustomerAccount(customerId, password: 'senha-errada-1'),
        throwsA(isA<CustomerException>()),
      );
    });

    test('apaga a conta, mantém os pedidos anonimizados e sem vínculo',
        () async {
      final customerId = await newCustomer();
      final created = await createOrder(order(), customerId: customerId);
      final publicId = created['id']! as String;
      final connection = await getConnection();
      await connection.execute(
        r"UPDATE orders SET status = 'completed' WHERE public_id = $1;",
        parameters: [publicId],
      );

      await deleteCustomerAccount(customerId, password: _password);

      final customers = await connection.execute(
        r'SELECT COUNT(*) FROM customers WHERE id = $1;',
        parameters: [customerId],
      );
      expect((customers.first.first as num).toInt(), 0);

      final orders = await connection.execute(
        r'''
        SELECT customer_id, customer_name, whatsapp, total
        FROM orders WHERE public_id = $1;
        ''',
        parameters: [publicId],
      );
      final row = orders.first;
      expect(row[0], isNull);
      expect(row[1], 'Cliente excluído');
      expect(row[2], '00000000000');
      expect(double.parse(row[3].toString()), 10.0);
    });
  });
}
