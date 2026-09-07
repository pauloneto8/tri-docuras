class PixPayment {
  const PixPayment({
    required this.copyCode,
    required this.qrCodeBase64,
    required this.expiresAt,
    this.paymentId,
    this.status = 'pending',
    this.mpMode = 'production',
  });

  factory PixPayment.fromJson(Map<String, dynamic> json) {
    return PixPayment(
      paymentId: (json['payment_id'] as num?)?.toInt(),
      copyCode: json['copy_code'] as String? ?? '',
      qrCodeBase64: json['qr_code_base64'] as String? ?? '',
      expiresAt: DateTime.parse(json['expires_at'] as String).toLocal(),
      status: json['status'] as String? ?? 'pending',
      mpMode: json['mp_mode'] as String? ?? 'production',
    );
  }

  final int? paymentId;
  final String copyCode;
  final String qrCodeBase64;
  final DateTime expiresAt;
  final String status;
  final String mpMode;

  bool get hasQrImage => qrCodeBase64.isNotEmpty;
  bool get isTestMode => mpMode == 'test';
}

class CreatedOrder {
  const CreatedOrder({
    required this.id,
    required this.status,
    required this.subtotal,
    required this.deliveryFee,
    required this.total,
    this.pix,
    this.pixError,
  });

  factory CreatedOrder.fromJson(Map<String, dynamic> json) {
    final order = json['order'] as Map<String, dynamic>;
    final pixRaw = json['pix'];
    return CreatedOrder(
      id: order['id'] as String,
      status: order['status'] as String,
      subtotal: (order['subtotal'] as num).toDouble(),
      deliveryFee: (order['delivery_fee'] as num).toDouble(),
      total: (order['total'] as num).toDouble(),
      pix: pixRaw is Map<String, dynamic>
          ? PixPayment.fromJson(pixRaw)
          : null,
      pixError: json['pix_error'] as String?,
    );
  }

  final String id;
  final String status;
  final double subtotal;
  final double deliveryFee;
  final double total;
  final PixPayment? pix;
  final String? pixError;
}

class OrderStatus {
  const OrderStatus({required this.id, required this.status});

  factory OrderStatus.fromJson(Map<String, dynamic> json) {
    final order = json['order'] as Map<String, dynamic>;
    return OrderStatus(
      id: order['id'] as String,
      status: order['status'] as String,
    );
  }

  final String id;
  final String status;

  bool get isPaid => status == 'paid';
}
