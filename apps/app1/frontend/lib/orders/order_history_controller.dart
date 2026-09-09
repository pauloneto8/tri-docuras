import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tri_docuras/orders/order_history_entry.dart';

const _prefsKey = 'order_history_entries';
const _maxEntries = 20;

class OrderHistoryController extends ChangeNotifier {
  OrderHistoryController({List<OrderHistoryEntry>? seed}) : _entries = [...?seed];

  final List<OrderHistoryEntry> _entries;
  bool _loaded = false;

  List<OrderHistoryEntry> get entries => List.unmodifiable(_entries);
  bool get isLoaded => _loaded;
  bool get isEmpty => _entries.isEmpty;

  Future<void> load() async {
    if (_loaded) return;
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getStringList(_prefsKey);
    if (stored != null) {
      _entries
        ..clear()
        ..addAll(
          stored.map((raw) {
            final json = jsonDecode(raw) as Map<String, dynamic>;
            return OrderHistoryEntry.fromJson(json);
          }),
        );
    }
    _loaded = true;
    notifyListeners();
  }

  Future<void> remember({
    required String id,
    required double total,
    String deliveryMode = 'pickup',
    DateTime? createdAt,
  }) async {
    _entries.removeWhere((entry) => entry.id == id);
    _entries.insert(
      0,
      OrderHistoryEntry(
        id: id,
        total: total,
        createdAt: createdAt ?? DateTime.now(),
        deliveryMode: deliveryMode,
      ),
    );
    if (_entries.length > _maxEntries) {
      _entries.removeRange(_maxEntries, _entries.length);
    }
    notifyListeners();
    await _persist();
  }

  Future<void> remove(String id) async {
    final index = _entries.indexWhere((entry) => entry.id == id);
    if (index < 0) return;
    _entries.removeAt(index);
    notifyListeners();
    await _persist();
  }

  Future<void> clear() async {
    if (_entries.isEmpty) return;
    _entries.clear();
    notifyListeners();
    await _persist();
  }

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(
      _prefsKey,
      _entries.map((entry) => jsonEncode(entry.toJson())).toList(),
    );
  }
}
