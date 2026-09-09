import 'package:flutter/material.dart';
import 'package:tri_docuras/orders/order_history_controller.dart';

class OrderHistoryScope extends InheritedNotifier<OrderHistoryController> {
  const OrderHistoryScope({
    super.key,
    required OrderHistoryController super.notifier,
    required super.child,
  });

  static OrderHistoryController of(BuildContext context) {
    final scope =
        context.dependOnInheritedWidgetOfExactType<OrderHistoryScope>();
    assert(scope != null, 'OrderHistoryScope not found in widget tree');
    return scope!.notifier!;
  }
}
