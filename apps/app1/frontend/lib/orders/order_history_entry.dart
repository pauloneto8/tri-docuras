class OrderHistoryEntry {
  const OrderHistoryEntry({
    required this.id,
    required this.total,
    required this.createdAt,
    this.deliveryMode = 'pickup',
  });

  factory OrderHistoryEntry.fromJson(Map<String, dynamic> json) {
    return OrderHistoryEntry(
      id: json['id'] as String,
      total: (json['total'] as num).toDouble(),
      createdAt: DateTime.parse(json['created_at'] as String).toLocal(),
      deliveryMode: json['delivery_mode'] as String? ?? 'pickup',
    );
  }

  final String id;
  final double total;
  final DateTime createdAt;
  final String deliveryMode;

  Map<String, dynamic> toJson() => {
        'id': id,
        'total': total,
        'created_at': createdAt.toUtc().toIso8601String(),
        'delivery_mode': deliveryMode,
      };

  String get formattedTotal =>
      'R\$ ${total.toStringAsFixed(2).replaceAll('.', ',')}';

  String get deliveryLabel =>
      deliveryMode == 'delivery' ? 'Entrega' : 'Retirada';
}
