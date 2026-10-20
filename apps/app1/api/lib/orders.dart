import 'dart:io';

import 'package:postgres/postgres.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/mercado_pago_client.dart';
import 'package:tri_docuras_api/mercado_pago_config.dart';
import 'package:tri_docuras_api/order_events.dart';
import 'package:tri_docuras_api/payment_check_throttle.dart';
import 'package:tri_docuras_api/product_options.dart';
import 'package:tri_docuras_api/store_settings.dart';
import 'package:tri_docuras_api/whatsapp_notify.dart';

/// Únicos status a partir dos quais uma confirmação do Mercado Pago pode
/// marcar o pedido como pago. Notificações repetidas sobre pedidos já
/// pagos/em preparo/prontos/concluídos/cancelados são ignoradas.
const paymentConfirmableStatuses = ['pending_payment'];

final _paymentCheckThrottle = PaymentCheckThrottle();

class OrderValidationException implements Exception {
  OrderValidationException(this.message);

  final String message;

  @override
  String toString() => message;
}

class OrderItemInput {
  OrderItemInput({
    required this.productId,
    required this.quantity,
    required this.unitPrice,
    required this.productName,
    this.options,
  });

  final int productId;
  final int quantity;
  final double unitPrice;
  final String productName;

  /// Opções escolhidas em texto (ex.: `9x9cm · Sem lactose`), para o pedido.
  final String? options;

  double get lineTotal => unitPrice * quantity;
}

class CreateOrderInput {
  CreateOrderInput({
    required this.customerName,
    required this.whatsapp,
    required this.deliveryMode,
    required this.items,
    required this.subtotal,
    required this.deliveryFee,
    required this.total,
    this.deliveryStreet,
    this.deliveryNumber,
    this.deliveryComplement,
    this.deliveryNeighborhood,
    this.deliveryReference,
  });

  final String customerName;
  final String whatsapp;
  final String deliveryMode;
  final List<OrderItemInput> items;
  final double subtotal;
  final double deliveryFee;
  final double total;
  final String? deliveryStreet;
  final String? deliveryNumber;
  final String? deliveryComplement;
  final String? deliveryNeighborhood;
  final String? deliveryReference;
}

/// Carrinho salvo antes das variações cadastráveis: mandava `size` e
/// `lactose_free` em vez de `option_ids`. Recusamos para o cliente recarregar
/// a página, em vez de cobrar um preço diferente do que ele viu.
bool _usesLegacyOptions(Map<dynamic, dynamic> entry) {
  final size = entry['size']?.toString().trim() ?? '';
  return entry['lactose_free'] == true || size.isNotEmpty;
}

List<int> _parseOptionIds(Object? raw) {
  if (raw == null) return const [];
  if (raw is! List) {
    throw OrderValidationException('Opções inválidas no carrinho.');
  }
  return [
    for (final id in raw)
      if (id is num)
        id.toInt()
      else
        throw OrderValidationException('Opções inválidas no carrinho.'),
  ];
}

Future<CreateOrderInput> parseCreateOrderInput(Map<String, dynamic> body) async {
  final customerName = _normalizeName(body['customer_name']);
  if (customerName.length < 2) {
    throw OrderValidationException('Informe o nome completo.');
  }

  final whatsapp = _digitsOnly(body['whatsapp']);
  if (whatsapp.length != 11) {
    throw OrderValidationException('Informe um WhatsApp válido com 11 dígitos.');
  }

  final deliveryModeRaw = body['delivery_mode']?.toString().trim();
  if (deliveryModeRaw != 'pickup' && deliveryModeRaw != 'delivery') {
    throw OrderValidationException('Modo de entrega inválido.');
  }
  final deliveryMode = deliveryModeRaw!;

  final address = body['delivery_address'];
  String? street;
  String? number;
  String? complement;
  String? neighborhood;
  String? reference;

  if (deliveryMode == 'delivery') {
    if (address is! Map) {
      throw OrderValidationException('Endereço de entrega é obrigatório.');
    }
    street = _trimmed(address['street']);
    number = _trimmed(address['number']);
    neighborhood = _trimmed(address['neighborhood']);
    reference = _trimmed(address['reference']);
    final complementRaw = address['complement'];
    complement = complementRaw == null ? null : _trimmed(complementRaw);
    if (street.isEmpty ||
        number.isEmpty ||
        neighborhood.isEmpty ||
        reference.isEmpty) {
      throw OrderValidationException('Preencha o endereço de entrega.');
    }
  }

  final rawItems = body['items'];
  if (rawItems is! List || rawItems.isEmpty) {
    throw OrderValidationException('O carrinho está vazio.');
  }

  final productIds = <int>{};
  final parsedItems = <Map<String, dynamic>>[];
  for (final entry in rawItems) {
    if (entry is! Map) {
      throw OrderValidationException('Item do pedido inválido.');
    }
    final productId = entry['product_id'];
    if (productId is! num) {
      throw OrderValidationException('Produto inválido no carrinho.');
    }
    final quantity = entry['quantity'];
    if (quantity is! num || quantity < 1) {
      throw OrderValidationException('Quantidade inválida.');
    }
    if (entry['option_ids'] == null && _usesLegacyOptions(entry)) {
      throw OrderValidationException('Atualize a página e refaça o carrinho.');
    }
    parsedItems.add({
      'product_id': productId.toInt(),
      'quantity': quantity.toInt(),
      'option_ids': _parseOptionIds(entry['option_ids']),
    });
    productIds.add(productId.toInt());
  }

  final connection = await getConnection();
  final productsResult = await connection.execute(
    '''
    SELECT id, name, price, available
    FROM products
    WHERE id = ANY(\$1::int[]);
    ''',
    parameters: [productIds.toList()],
  );

  if (productsResult.length != productIds.length) {
    throw OrderValidationException('Um ou mais produtos não estão disponíveis.');
  }

  final productsById = <int, Map<String, Object?>>{};
  for (final row in productsResult) {
    final id = (row[0] as num).toInt();
    final available = row[3] == true;
    if (!available) {
      throw OrderValidationException('Produto indisponível no momento.');
    }
    productsById[id] = {
      'name': row[1] as String,
      'price': switch (row[2]) {
        final num value => value.toDouble(),
        final String value => double.parse(value),
        _ => 0.0,
      },
    };
  }

  final optionsByProduct = await fetchActiveOptionsByProduct(
    connection,
    productIds.toList(),
  );

  final items = <OrderItemInput>[];
  for (final entry in parsedItems) {
    final productId = entry['product_id'] as int;
    final product = productsById[productId]!;
    final basePrice = product['price']! as double;
    final productName = product['name']! as String;
    final ResolvedOptions resolved;
    try {
      resolved = resolveProductOptions(
        productName: productName,
        selectedIds: entry['option_ids'] as List<int>,
        available: optionsByProduct[productId] ?? const [],
      );
    } on ProductOptionException catch (error) {
      throw OrderValidationException(error.message);
    }
    items.add(
      OrderItemInput(
        productId: productId,
        quantity: entry['quantity'] as int,
        unitPrice: basePrice + resolved.extraPrice,
        productName: productName,
        options: resolved.label,
      ),
    );
  }

  final settings = await getStoreSettings();
  if (!settings.storeOpen) {
    throw OrderValidationException('A loja está fechada no momento.');
  }

  final subtotal = items.fold<double>(0, (sum, item) => sum + item.lineTotal);
  final deliveryFee = deliveryMode == 'delivery' ? settings.deliveryFee : 0.0;
  final total = subtotal + deliveryFee;

  return CreateOrderInput(
    customerName: customerName,
    whatsapp: whatsapp,
    deliveryMode: deliveryMode,
    items: items,
    subtotal: subtotal,
    deliveryFee: deliveryFee,
    total: total,
    deliveryStreet: street,
    deliveryNumber: number,
    deliveryComplement: complement,
    deliveryNeighborhood: neighborhood,
    deliveryReference: reference,
  );
}

/// [customerId] é obrigatório para pedidos novos: a rota só chama aqui
/// depois de validar a sessão do cliente.
Future<Map<String, Object?>> createOrder(
  CreateOrderInput input, {
  required int customerId,
}) async {
  final connection = await getConnection();

  return connection.runTx((tx) async {
    final tempPublicId = 'TMP-${DateTime.now().microsecondsSinceEpoch}';
    final orderResult = await tx.execute(
      r'''
      INSERT INTO orders (
        public_id, status, customer_name, whatsapp, delivery_mode,
        delivery_street, delivery_number, delivery_complement,
        delivery_neighborhood, delivery_reference,
        subtotal, delivery_fee, total, customer_id
      ) VALUES (
        $1, 'pending_payment', $2, $3, $4,
        $5, $6, $7, $8, $9, $10, $11, $12, $13
      )
      RETURNING id;
      ''',
      parameters: [
        tempPublicId,
        input.customerName,
        input.whatsapp,
        input.deliveryMode,
        input.deliveryStreet,
        input.deliveryNumber,
        input.deliveryComplement,
        input.deliveryNeighborhood,
        input.deliveryReference,
        input.subtotal,
        input.deliveryFee,
        input.total,
        customerId,
      ],
    );

    final orderId = (orderResult.first.first as num).toInt();
    final publicId = 'TD-${orderId.toString().padLeft(4, '0')}';

    await tx.execute(
      'UPDATE orders SET public_id = \$1 WHERE id = \$2;',
      parameters: [publicId, orderId],
    );
    await recordOrderEvent(
      tx,
      orderId: orderId,
      from: null,
      to: 'pending_payment',
      actor: actorCustomer,
    );

    for (final item in input.items) {
      // Reserva o estoque na mesma transação do pedido. Produto sem controle
      // (stock NULL) não é alterado. Se faltar, a transação inteira é desfeita.
      final reserved = await tx.execute(
        r'''
        UPDATE products
        SET stock = stock - $2
        WHERE id = $1 AND (stock IS NULL OR stock >= $2)
        RETURNING id;
        ''',
        parameters: [item.productId, item.quantity],
      );
      if (reserved.isEmpty) {
        throw OrderValidationException(
          'Sem estoque de ${item.productName}. Ajuste a quantidade.',
        );
      }

      await tx.execute(
        r'''
        INSERT INTO order_items (
          order_id, product_id, product_name, quantity,
          unit_price, options, line_total
        ) VALUES ($1, $2, $3, $4, $5, $6, $7);
        ''',
        parameters: [
          orderId,
          item.productId,
          item.productName,
          item.quantity,
          item.unitPrice,
          item.options,
          item.lineTotal,
        ],
      );
    }

    return {
      'id': publicId,
      'status': 'pending_payment',
      'subtotal': input.subtotal,
      'delivery_fee': input.deliveryFee,
      'total': input.total,
      'customer_name': input.customerName,
      'whatsapp': input.whatsapp,
    };
  });
}

Future<Map<String, Object?>> getOrderByPublicId(String publicId) async {
  final connection = await getConnection();
  final result = await connection.execute(
    '''
    SELECT public_id, status, customer_name, whatsapp, delivery_mode,
           delivery_street, delivery_number, delivery_complement,
           delivery_neighborhood, delivery_reference,
           subtotal, delivery_fee, total, mp_payment_id, pix_copy_code,
           pix_qr_base64, pix_expires_at, paid_at, created_at, customer_id
    FROM orders
    WHERE public_id = \$1
    LIMIT 1;
    ''',
    parameters: [publicId],
  );
  if (result.isEmpty) return {};
  return _rowToOrderMap(result.first);
}

Future<Map<String, Object?>> createPixForOrder(String publicId) async {
  final order = await getOrderByPublicId(publicId);
  if (order.isEmpty) {
    throw OrderValidationException('Pedido não encontrado.');
  }

  final status = order['status'] as String;
  if (status == 'paid') {
    throw OrderValidationException('Este pedido já foi pago.');
  }
  if (status == 'cancelled') {
    throw OrderValidationException('Este pedido foi cancelado.');
  }
  if (status == 'expired') {
    throw OrderValidationException(
      'Este pedido expirou por falta de pagamento. Faça um novo pedido.',
    );
  }

  final expiresAt = order['pix_expires_at'] as DateTime?;
  final copyCode = order['pix_copy_code'] as String?;
  final qrBase64 = order['pix_qr_base64'] as String?;
  final paymentId = order['mp_payment_id'] as int?;

  if (paymentId != null &&
      copyCode != null &&
      copyCode.isNotEmpty &&
      expiresAt != null &&
      expiresAt.isAfter(DateTime.now().toUtc())) {
    return MercadoPagoConfig.enrichPixPayload(
      PixChargeResult.fromStored(
        paymentId: paymentId,
        copyCode: copyCode,
        qrCodeBase64: qrBase64 ?? '',
        expiresAt: expiresAt,
        status: 'pending',
      ).toJson(),
    );
  }

  final client = MercadoPagoClient();
  final pix = await client.createPixPayment(
    orderPublicId: publicId,
    amount: (order['total'] as num).toDouble(),
    customerName: order['customer_name'] as String,
    whatsapp: order['whatsapp'] as String,
  );

  final connection = await getConnection();
  await connection.execute(
    '''
    UPDATE orders
    SET mp_payment_id = \$1,
        pix_copy_code = \$2,
        pix_qr_base64 = \$3,
        pix_expires_at = \$4
    WHERE public_id = \$5;
    ''',
    parameters: [
      pix.paymentId,
      pix.copyCode,
      pix.qrCodeBase64,
      pix.expiresAt,
      publicId,
    ],
  );

  return MercadoPagoConfig.enrichPixPayload(pix.toJson());
}

Future<bool> syncOrderPaymentFromMercadoPago(int paymentId) async {
  final client = MercadoPagoClient();
  final payment = await client.fetchPayment(paymentId);
  final externalRef = payment['external_reference']?.toString();
  if (externalRef == null || externalRef.isEmpty) return false;

  if (!mercadoPagoStatusIsPaid(payment['status']?.toString())) {
    return false;
  }

  return markOrderPaid(externalRef, paymentId: paymentId);
}

/// Rede de segurança para o webhook: enquanto o pedido está aguardando Pix,
/// o polling do app reconsulta o Mercado Pago (no máximo a cada 15 s por
/// pedido). Nunca lança: falha do MP não pode quebrar o `GET` do pedido.
Future<Map<String, Object?>> refreshOrderPaymentIfStale(
  Map<String, Object?> order,
) async {
  final paymentId = order['mp_payment_id'];
  if (order['status'] != 'pending_payment' || paymentId is! int) {
    return order;
  }
  final publicId = order['id']! as String;
  if (!_paymentCheckThrottle.shouldCheck(publicId, DateTime.now())) {
    return order;
  }
  try {
    final updated = await syncOrderPaymentFromMercadoPago(paymentId);
    if (updated) return await getOrderByPublicId(publicId);
  } catch (e) {
    stderr.writeln('[mp] reconsulta do pedido $publicId falhou: $e');
  }
  return order;
}

/// Devolve ao estoque os itens do pedido. Chamar uma única vez por pedido,
/// ao expirar ou cancelar (a máquina de estados impede o segundo cancelamento).
Future<void> restockOrderItems(Session db, int orderId) async {
  await db.execute(
    r'''
    UPDATE products p
    SET stock = p.stock + totals.quantity
    FROM (
      SELECT product_id, SUM(quantity)::int AS quantity
      FROM order_items
      WHERE order_id = $1
      GROUP BY product_id
    ) totals
    WHERE p.id = totals.product_id AND p.stock IS NOT NULL;
    ''',
    parameters: [orderId],
  );
}

/// Carência após o vencimento do Pix antes de o pedido virar `expired`.
const expiredOrderGrace = Duration(hours: 24);

/// Marca como `expired` os pedidos `pending_payment` cujo Pix venceu há mais
/// de [expiredOrderGrace] (sem Pix gerado, conta a partir da criação).
/// Devolve quantos pedidos foram expirados.
Future<int> expireStaleOrders() async {
  final connection = await getConnection();
  return connection.runTx((tx) async {
    final result = await tx.execute(
      '''
      UPDATE orders
      SET status = 'expired'
      WHERE status = 'pending_payment'
        AND COALESCE(pix_expires_at, created_at)
            < (NOW() AT TIME ZONE 'UTC') - make_interval(secs => \$1)
      RETURNING id;
      ''',
      parameters: [expiredOrderGrace.inSeconds.toDouble()],
    );
    for (final row in result) {
      final orderId = row[0]! as int;
      await recordOrderEvent(
        tx,
        orderId: orderId,
        from: 'pending_payment',
        to: 'expired',
        actor: actorSystem,
        note: 'Pix vencido há mais de 24 h',
      );
      await restockOrderItems(tx, orderId);
    }
    return result.length;
  });
}

Future<bool> markOrderPaid(String publicId, {int? paymentId}) async {
  final connection = await getConnection();
  final updated = await connection.runTx((tx) async {
    final result = await tx.execute(
      '''
      UPDATE orders
      SET status = 'paid',
          paid_at = NOW(),
          mp_payment_id = COALESCE(\$2, mp_payment_id)
      WHERE public_id = \$1 AND status = ANY(\$3::text[])
      RETURNING id, status;
      ''',
      parameters: [publicId, paymentId, paymentConfirmableStatuses],
    );
    if (result.isEmpty) return false;
    await recordOrderEvent(
      tx,
      orderId: result.first[0]! as int,
      from: 'pending_payment',
      to: 'paid',
      actor: actorMercadoPago,
      note: paymentId == null ? null : 'pagamento $paymentId',
    );
    return true;
  });
  if (!updated) {
    stderr.writeln(
      '[mp] pagamento $paymentId ignorado: pedido $publicId '
      'não está em pending_payment',
    );
  }
  if (updated) {
    try {
      await notifyOrderPaid(publicId);
    } catch (_) {
      // Notificação não deve bloquear confirmação do pagamento.
    }
  }
  return updated;
}

Map<String, Object?> _rowToOrderMap(ResultRow row) {
  return {
    'id': row[0],
    'status': row[1],
    'customer_name': row[2],
    'whatsapp': row[3],
    'delivery_mode': row[4],
    'delivery_street': row[5],
    'delivery_number': row[6],
    'delivery_complement': row[7],
    'delivery_neighborhood': row[8],
    'delivery_reference': row[9],
    'subtotal': _toDouble(row[10]),
    'delivery_fee': _toDouble(row[11]),
    'total': _toDouble(row[12]),
    'mp_payment_id': row[13] == null ? null : (row[13] as num).toInt(),
    'pix_copy_code': row[14],
    'pix_qr_base64': row[15],
    'pix_expires_at': row[16],
    'paid_at': row[17],
    'created_at': row[18],
    'customer_id': row[19] == null ? null : (row[19] as num).toInt(),
  };
}

Map<String, Object?> orderToPublicJson(Map<String, Object?> order) {
  return {
    'id': order['id'],
    'status': order['status'],
    'subtotal': order['subtotal'],
    'delivery_fee': order['delivery_fee'],
    'total': order['total'],
    'paid_at': order['paid_at']?.toString(),
    'pix_expires_at': order['pix_expires_at']?.toString(),
  };
}

double _toDouble(Object? value) => switch (value) {
      final num n => n.toDouble(),
      final String s => double.parse(s),
      _ => 0.0,
    };

String _normalizeName(Object? value) {
  final raw = value?.toString().trim() ?? '';
  return raw.replaceAll(RegExp(r'\s+'), ' ');
}

String _trimmed(Object? value) => value?.toString().trim() ?? '';

String _digitsOnly(Object? value) =>
    (value?.toString() ?? '').replaceAll(RegExp(r'\D'), '');
