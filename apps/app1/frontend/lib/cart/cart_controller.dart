import 'package:flutter/foundation.dart';
import 'package:tri_docuras/cart/cart_item.dart';
import 'package:tri_docuras/cart/delivery_mode.dart';

class CartController extends ChangeNotifier {
  static const deliveryFeeAmount = 6.0;

  final List<CartItem> _items = [];
  DeliveryMode _deliveryMode = DeliveryMode.pickup;

  List<CartItem> get items => List.unmodifiable(_items);

  DeliveryMode get deliveryMode => _deliveryMode;

  int get itemCount => _items.fold(0, (sum, item) => sum + item.quantity);

  double get subtotal => _items.fold(0, (sum, item) => sum + item.lineTotal);

  double get deliveryFee =>
      _deliveryMode == DeliveryMode.pickup ? 0 : deliveryFeeAmount;

  double get total => subtotal + deliveryFee;

  String get formattedSubtotal => _formatMoney(subtotal);

  String get formattedTotal => _formatMoney(total);

  String get formattedDeliveryFee => _formatMoney(deliveryFee);

  String get deliveryFeeLabel =>
      _deliveryMode == DeliveryMode.pickup ? 'Grátis' : formattedDeliveryFee;

  void add(CartItem item) {
    _items.add(item);
    notifyListeners();
  }

  void setDeliveryMode(DeliveryMode mode) {
    _deliveryMode = mode;
    notifyListeners();
  }

  void updateQuantity(int index, int quantity) {
    if (index < 0 || index >= _items.length) return;
    if (quantity <= 0) {
      _items.removeAt(index);
    } else {
      _items[index] = _items[index].copyWith(quantity: quantity);
    }
    notifyListeners();
  }

  void removeAt(int index) {
    if (index < 0 || index >= _items.length) return;
    _items.removeAt(index);
    notifyListeners();
  }

  void clear() {
    _items.clear();
    notifyListeners();
  }

  static String _formatMoney(double value) =>
      'R\$ ${value.toStringAsFixed(2).replaceAll('.', ',')}';
}
