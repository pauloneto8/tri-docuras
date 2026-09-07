class TrackingStep {
  const TrackingStep({
    required this.key,
    required this.label,
    required this.done,
    required this.current,
  });

  factory TrackingStep.fromJson(Map<String, dynamic> json) {
    return TrackingStep(
      key: json['key'] as String,
      label: json['label'] as String,
      done: json['done'] as bool? ?? false,
      current: json['current'] as bool? ?? false,
    );
  }

  final String key;
  final String label;
  final bool done;
  final bool current;
}

class OrderTracking {
  const OrderTracking({
    required this.id,
    required this.status,
    required this.statusLabel,
    required this.deliveryLabel,
    required this.total,
    required this.timeline,
    this.isCompleted = false,
  });

  factory OrderTracking.fromJson(Map<String, dynamic> json) {
    final order = json['order'] as Map<String, dynamic>;
    final timelineRaw = json['timeline'] as List<dynamic>? ?? [];
    return OrderTracking(
      id: order['id'] as String,
      status: order['status'] as String,
      statusLabel: order['status_label'] as String? ?? order['status'] as String,
      deliveryLabel: order['delivery_label'] as String? ?? '',
      total: (order['total'] as num).toDouble(),
      isCompleted: order['is_completed'] as bool? ?? false,
      timeline: timelineRaw
          .map((step) => TrackingStep.fromJson(step as Map<String, dynamic>))
          .toList(),
    );
  }

  final String id;
  final String status;
  final String statusLabel;
  final String deliveryLabel;
  final double total;
  final bool isCompleted;
  final List<TrackingStep> timeline;

  String get formattedTotal =>
      'R\$ ${total.toStringAsFixed(2).replaceAll('.', ',')}';
}
