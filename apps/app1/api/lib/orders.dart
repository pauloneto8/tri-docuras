import 'package:postgres/postgres.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/mercado_pago_client.dart';
import 'package:tri_docuras_api/mercado_pago_config.dart';
import 'package:tri_docuras_api/whatsapp_notify.dart';

const lactoseExtraPrice = 3.0;
const deliveryFeeAmount = 6.0;

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
    this.size,
    this.lactoseFree = false,
  });

  final int productId;
  final int quantity;
  final double unitPrice;
  final String productName;
  final String? size;
  final bool lactoseFree;

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
    final lactoseFree = entry['lactose_free'] == true;
    final sizeRaw = entry['size'];
    final size = sizeRaw == null ? null : sizeRaw.toString().trim();
    parsedItems.add({
      'product_id': productId.toInt(),
      'quantity': quantity.toInt(),
      'lactose_free': lactoseFree,
      'size': size != null && size.isNotEmpty ? size : null,
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

  final items = <OrderItemInput>[];
  for (final entry in parsedItems) {
    final productId = entry['product_id'] as int;
    final product = productsById[productId]!;
    final basePrice = product['price']! as double;
    final lactoseFree = entry['lactose_free'] as bool;
    final unitPrice = basePrice + (lactoseFree ? lactoseExtraPrice : 0);
    items.add(
      OrderItemInput(
        productId: productId,
        quantity: entry['quantity'] as int,
        unitPrice: unitPrice,
        productName: product['name']! as String,
        size: entry['size'] as String?,
        lactoseFree: lactoseFree,
      ),
    );
  }

  final subtotal = items.fold<double>(0, (sum, item) => sum + item.lineTotal);
  final deliveryFee = deliveryMode == 'delivery' ? deliveryFeeAmount : 0.0;
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

Future<Map<String, Object?>> createOrder(CreateOrderInput input) async {
  final connection = await getConnection();

  return connection.runTx((tx) async {
    final tempPublicId = 'TMP-${DateTime.now().microsecondsSinceEpoch}';
    final orderResult = await tx.execute(
      r'''
      INSERT INTO orders (
        public_id, status, customer_name, whatsapp, delivery_mode,
        delivery_street, delivery_number, delivery_complement,
        delivery_neighborhood, delivery_reference,
        subtotal, delivery_fee, total
      ) VALUES (
        $1, 'pending_payment', $2, $3, $4,
        $5, $6, $7, $8, $9, $10, $11, $12
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
      ],
    );

    final orderId = (orderResult.first.first as num).toInt();
    final publicId = 'TD-${orderId.toString().padLeft(4, '0')}';

    await tx.execute(
      'UPDATE orders SET public_id = \$1 WHERE id = \$2;',
      parameters: [publicId, orderId],
    );

    for (final item in input.items) {
      await tx.execute(
        r'''
        INSERT INTO order_items (
          order_id, product_id, product_name, quantity,
          unit_price, size, lactose_free, line_total
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8);
        ''',
        parameters: [
          orderId,
          item.productId,
          item.productName,
          item.quantity,
          item.unitPrice,
          item.size,
          item.lactoseFree,
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
           pix_qr_base64, pix_expires_at, paid_at, created_at
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

Future<bool> markOrderPaid(String publicId, {int? paymentId}) async {
  final connection = await getConnection();
  final result = await connection.execute(
    '''
    UPDATE orders
    SET status = 'paid',
        paid_at = NOW(),
        mp_payment_id = COALESCE(\$2, mp_payment_id)
    WHERE public_id = \$1 AND status <> 'paid'
    RETURNING public_id;
    ''',
    parameters: [publicId, paymentId],
  );
  final updated = result.isNotEmpty;
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
