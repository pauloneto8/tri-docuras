import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _prefsKey = 'favorite_product_ids';

class FavoritesController extends ChangeNotifier {
  FavoritesController({Set<int>? seed}) : _ids = {...?seed};

  final Set<int> _ids;
  bool _loaded = false;

  Set<int> get ids => Set.unmodifiable(_ids);
  int get count => _ids.length;
  bool get isLoaded => _loaded;

  bool isFavorite(int productId) => _ids.contains(productId);

  Future<void> load() async {
    if (_loaded) return;
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getStringList(_prefsKey);
    if (stored != null) {
      _ids
        ..clear()
        ..addAll(stored.map(int.parse));
    }
    _loaded = true;
    notifyListeners();
  }

  Future<void> toggle(int productId) async {
    if (_ids.contains(productId)) {
      _ids.remove(productId);
    } else {
      _ids.add(productId);
    }
    notifyListeners();
    await _persist();
  }

  Future<void> remove(int productId) async {
    if (_ids.remove(productId)) {
      notifyListeners();
      await _persist();
    }
  }

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(
      _prefsKey,
      _ids.map((id) => id.toString()).toList(),
    );
  }
}
