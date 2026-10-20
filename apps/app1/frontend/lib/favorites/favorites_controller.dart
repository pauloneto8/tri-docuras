import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tri_docuras/account/auth_token.dart';
import 'package:tri_docuras/services/api_service.dart';

const _prefsKey = 'favorite_product_ids';

/// Favoritos. Sem conta ficam salvos no aparelho; com conta, na API. Ao
/// entrar, os favoritos do aparelho são somados aos da conta e apagados
/// do aparelho.
class FavoritesController extends ChangeNotifier {
  FavoritesController({Set<int>? seed, ApiService? api})
      : _ids = {...?seed},
        _api = api ?? ApiService();

  final Set<int> _ids;
  final ApiService _api;
  bool _loaded = false;

  Set<int> get ids => Set.unmodifiable(_ids);
  int get count => _ids.length;
  bool get isLoaded => _loaded;

  bool isFavorite(int productId) => _ids.contains(productId);

  /// Carrega a lista. Com [force], recarrega mesmo se já estava carregada
  /// (usado ao entrar ou sair da conta).
  Future<void> load({bool force = false}) async {
    if (_loaded && !force) return;
    if (AuthToken.value != null) {
      await _loadRemote();
    } else {
      await _loadLocal();
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

  Future<void> _loadLocal() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getStringList(_prefsKey);
    _ids
      ..clear()
      ..addAll((stored ?? const <String>[]).map(int.parse));
  }

  Future<void> _loadRemote() async {
    try {
      final remote = await _api.fetchFavorites();
      final local = await _readLocal();
      final merged = {...remote, ...local};
      if (merged.length != remote.length) {
        await _api.saveFavorites(merged);
      }
      if (local.isNotEmpty) await _clearLocal();
      _ids
        ..clear()
        ..addAll(merged);
    } catch (_) {
      // Sem rede: mantém o que já estava em memória.
    }
  }

  Future<void> _persist() async {
    if (AuthToken.value != null) {
      try {
        await _api.saveFavorites(_ids);
      } catch (_) {
        await _loadRemote();
        notifyListeners();
      }
      return;
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(
      _prefsKey,
      _ids.map((id) => id.toString()).toList(),
    );
  }

  Future<Set<int>> _readLocal() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getStringList(_prefsKey) ?? const <String>[];
    return stored.map(int.parse).toSet();
  }

  Future<void> _clearLocal() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_prefsKey);
  }
}
