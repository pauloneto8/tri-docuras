import 'package:postgres/postgres.dart';
import 'package:tri_docuras_api/db.dart';

/// Quem mudou o status. Usado como `actor` em [recordOrderEvent].
const actorCustomer = 'Cliente';
const actorMercadoPago = 'Mercado Pago';
const actorSystem = 'Sistema';

Future<void> ensureOrderEventsSchema(Session connection) async {
  await connection.execute('''
    CREATE TABLE IF NOT EXISTS order_events (
      id SERIAL PRIMARY KEY,
      order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
      from_status VARCHAR(30),
      to_status VARCHAR(30) NOT NULL,
      actor VARCHAR(120) NOT NULL,
      note TEXT,
      created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
  ''');
  await connection.execute('''
    CREATE INDEX IF NOT EXISTS order_events_order_idx
      ON order_events (order_id, created_at, id);
  ''');
}

/// Grava uma mudança de status. Chame dentro da mesma transação da mudança
/// (`runTx`) para que o histórico nunca fique diferente do pedido.
Future<void> recordOrderEvent(
  Session db, {
  required int orderId,
  required String? from,
  required String to,
  required String actor,
  String? note,
}) async {
  await db.execute(
    r'''
    INSERT INTO order_events (order_id, from_status, to_status, actor, note)
    VALUES ($1, $2, $3, $4, $5);
    ''',
    parameters: [orderId, from, to, actor, note],
  );
}

/// Histórico de um pedido em ordem cronológica. `null` se o pedido não existe.
Future<List<Map<String, Object?>>?> listOrderEvents(String publicId) async {
  final connection = await getConnection();
  final order = await connection.execute(
    r'SELECT id FROM orders WHERE public_id = $1;',
    parameters: [publicId],
  );
  if (order.isEmpty) return null;

  final result = await connection.execute(
    r'''
    SELECT from_status, to_status, actor, note, created_at
    FROM order_events
    WHERE order_id = $1
    ORDER BY created_at ASC, id ASC;
    ''',
    parameters: [order.first[0]],
  );
  return result
      .map((row) => {
            'from': row[0],
            'to': row[1],
            'actor': row[2],
            'note': row[3],
            'at': (row[4] as DateTime?)?.toIso8601String(),
          })
      .toList();
}
