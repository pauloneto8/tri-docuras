import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tri_docuras/account/auth_token.dart';
import 'package:tri_docuras/models/customer_profile.dart';
import 'package:tri_docuras/services/api_service.dart';

const _tokenKey = 'customer_token';

/// Sessão do cliente. Só o token fica salvo no aparelho; o perfil é buscado
/// da API a cada abertura do app.
class AccountController extends ChangeNotifier {
  AccountController({ApiService? api, this.onSessionChanged})
      : _api = api ?? ApiService() {
    AuthToken.onUnauthorized = _onUnauthorized;
  }

  final ApiService _api;

  /// Chamado quando a sessão começa ou termina, para favoritos e histórico
  /// trocarem entre o aparelho e a conta.
  final VoidCallback? onSessionChanged;

  CustomerProfile? _profile;
  bool _loaded = false;

  bool get isLoggedIn => AuthToken.value != null;
  bool get isLoaded => _loaded;
  CustomerProfile? get profile => _profile;

  /// Restaura a sessão salva. Se a API recusar o token, a sessão é encerrada.
  Future<void> load() async {
    if (_loaded) return;
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString(_tokenKey);
    AuthToken.value = token;
    if (token != null) {
      try {
        _profile = await _api.fetchProfile();
      } catch (_) {
        // 401 já encerrou a sessão pelo onUnauthorized. Erro de rede mantém
        // o token para tentar de novo na próxima abertura.
      }
    }
    _loaded = true;
    notifyListeners();
    onSessionChanged?.call();
  }

  Future<void> login({required String email, required String password}) async {
    final session = await _api.login(email: email, password: password);
    await _startSession(session);
  }

  Future<void> register({
    required String email,
    required String password,
    required String name,
    required String whatsapp,
  }) async {
    final session = await _api.register(
      email: email,
      password: password,
      name: name,
      whatsapp: whatsapp,
    );
    await _startSession(session);
  }

  Future<void> logout() => _endSession();

  Future<void> saveProfile({
    required String name,
    required String whatsapp,
    required List<CustomerAddress> addresses,
  }) async {
    _profile = await _api.updateProfile(
      name: name,
      whatsapp: whatsapp,
      addresses: addresses,
    );
    notifyListeners();
  }

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    final token = await _api.changePassword(
      currentPassword: currentPassword,
      newPassword: newPassword,
    );
    AuthToken.value = token;
    await _persist(token);
  }

  Future<void> _startSession(CustomerSession session) async {
    AuthToken.value = session.token;
    _profile = session.customer;
    await _persist(session.token);
    notifyListeners();
    onSessionChanged?.call();
  }

  Future<void> _endSession() async {
    AuthToken.value = null;
    _profile = null;
    await _persist(null);
    notifyListeners();
    onSessionChanged?.call();
  }

  void _onUnauthorized() {
    if (!isLoggedIn) return;
    _endSession();
  }

  Future<void> _persist(String? token) async {
    final prefs = await SharedPreferences.getInstance();
    if (token == null) {
      await prefs.remove(_tokenKey);
    } else {
      await prefs.setString(_tokenKey, token);
    }
  }
}
