import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:tri_docuras/account/auth_token.dart';
import 'package:tri_docuras/cart/cart_item.dart';
import 'package:tri_docuras/checkout/checkout_draft.dart';
import 'package:tri_docuras/checkout/order_payload.dart';
import 'package:tri_docuras/config.dart';
import 'package:tri_docuras/models/created_order.dart';
import 'package:tri_docuras/models/customer_profile.dart';
import 'package:tri_docuras/models/order_tracking.dart';
import 'package:tri_docuras/models/product.dart';

class ApiService {
  ApiService({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  Future<List<Product>> fetchProducts() async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}/products');
    final response = await _client.get(uri);

    if (response.statusCode != 200) {
      throw Exception('Erro ao carregar produtos (${response.statusCode})');
    }

    final body = jsonDecode(response.body) as Map<String, dynamic>;
    final products = body['products'] as List<dynamic>;
    return products
        .map((item) => Product.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<CreatedOrder> createOrder({
    required CheckoutDraft draft,
    required List<CartItem> items,
  }) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}/orders');
    final response = await _client.post(
      uri,
      headers: {'Content-Type': 'application/json', ..._authHeaders()},
      body: jsonEncode(buildCreateOrderPayload(draft: draft, items: items)),
    );

    Map<String, dynamic> body;
    try {
      body = jsonDecode(response.body) as Map<String, dynamic>;
    } on FormatException {
      throw ApiException('Resposta inválida do servidor (${response.statusCode}).');
    }

    if (response.statusCode == 201) {
      return CreatedOrder.fromJson(body);
    }

    throw _apiError(response, body, 'Não foi possível registrar o pedido (${response.statusCode}).');
  }

  Future<OrderStatus> fetchOrderStatus(String orderId) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}/orders/$orderId');
    final response = await _client.get(uri, headers: _authHeaders());

    Map<String, dynamic> body;
    try {
      body = jsonDecode(response.body) as Map<String, dynamic>;
    } on FormatException {
      throw ApiException('Resposta inválida do servidor (${response.statusCode}).');
    }

    if (response.statusCode == 200) {
      return OrderStatus.fromJson(body);
    }

    throw _apiError(response, body, 'Não foi possível consultar o pedido (${response.statusCode}).');
  }

  Future<OrderTracking> fetchOrderTracking(
    String orderId, {
    String? trackingToken,
  }) async {
    final url = '${AppConfig.apiBaseUrl}/orders/$orderId/tracking';
    final uri = trackingToken == null
        ? Uri.parse(url)
        : Uri.parse(url).replace(queryParameters: {'t': trackingToken});
    final response = await _client.get(uri, headers: _authHeaders());

    Map<String, dynamic> body;
    try {
      body = jsonDecode(response.body) as Map<String, dynamic>;
    } on FormatException {
      throw ApiException('Resposta inválida do servidor (${response.statusCode}).');
    }

    if (response.statusCode == 200) {
      return OrderTracking.fromJson(body);
    }

    throw _apiError(response, body, 'Não foi possível consultar o pedido (${response.statusCode}).');
  }

  Future<PixPayment> createPix(String orderId) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}/orders/$orderId/pix');
    final response = await _client.post(
      uri,
      headers: {'Content-Type': 'application/json', ..._authHeaders()},
    );

    Map<String, dynamic> body;
    try {
      body = jsonDecode(response.body) as Map<String, dynamic>;
    } on FormatException {
      throw ApiException('Resposta inválida do servidor (${response.statusCode}).');
    }

    if (response.statusCode == 200) {
      final pix = body['pix'];
      if (pix is Map<String, dynamic>) {
        return PixPayment.fromJson(pix);
      }
      throw ApiException('Resposta Pix inválida.');
    }

    throw _apiError(response, body, 'Não foi possível gerar o Pix (${response.statusCode}).');
  }

  Map<String, String> _authHeaders() {
    final token = AuthToken.value;
    return token == null ? const {} : {'Authorization': 'Bearer $token'};
  }

  /// Erro da API. Um 401 com sessão ativa derruba a sessão local, para a
  /// tela pedir login de novo sem perder o carrinho.
  ApiException _apiError(
    http.Response response,
    Map<String, dynamic> body,
    String fallback,
  ) {
    if (response.statusCode == 401 && AuthToken.value != null) {
      AuthToken.onUnauthorized?.call();
      return ApiException(
        'Sua sessão expirou. Entre na sua conta de novo.',
        unauthorized: true,
      );
    }
    return ApiException(body['error'] as String? ?? fallback);
  }

  /// Chamada JSON genérica para as rotas de conta.
  Future<Map<String, dynamic>> _json(
    String method,
    String path, {
    Map<String, dynamic>? body,
    bool auth = false,
    required String fallback,
  }) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}$path');
    final headers = {
      if (body != null) 'Content-Type': 'application/json',
      if (auth) ..._authHeaders(),
    };
    final encoded = body == null ? null : jsonEncode(body);
    final response = switch (method) {
      'GET' => await _client.get(uri, headers: headers),
      'PUT' => await _client.put(uri, headers: headers, body: encoded),
      'DELETE' => await _client.delete(uri, headers: headers, body: encoded),
      _ => await _client.post(uri, headers: headers, body: encoded),
    };

    Map<String, dynamic> decoded;
    try {
      decoded = jsonDecode(response.body) as Map<String, dynamic>;
    } on FormatException {
      throw ApiException('Resposta inválida do servidor (${response.statusCode}).');
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return decoded;
    }
    throw _apiError(response, decoded, fallback);
  }

  Future<CustomerSession> register({
    required String email,
    required String password,
    required String name,
    required String whatsapp,
  }) async {
    final body = await _json(
      'POST',
      '/customers',
      body: {
        'email': email,
        'password': password,
        'name': name,
        'whatsapp': whatsapp,
        // A tela só libera o cadastro com a caixa marcada.
        'accepted_terms': true,
      },
      fallback: 'Não foi possível criar a conta.',
    );
    return CustomerSession.fromJson(body);
  }

  Future<CustomerSession> login({
    required String email,
    required String password,
  }) async {
    final body = await _json(
      'POST',
      '/customers/session',
      body: {'email': email, 'password': password},
      fallback: 'Não foi possível entrar.',
    );
    return CustomerSession.fromJson(body);
  }

  Future<CustomerProfile> fetchProfile() async {
    final body = await _json(
      'GET',
      '/customers/me',
      auth: true,
      fallback: 'Não foi possível carregar sua conta.',
    );
    return CustomerProfile.fromJson(body['customer'] as Map<String, dynamic>);
  }

  Future<CustomerProfile> updateProfile({
    required String name,
    required String whatsapp,
    required List<CustomerAddress> addresses,
  }) async {
    final body = await _json(
      'PUT',
      '/customers/me',
      body: {
        'name': name,
        'whatsapp': whatsapp,
        'addresses': addresses.map((a) => a.toJson()).toList(),
      },
      auth: true,
      fallback: 'Não foi possível salvar seus dados.',
    );
    return CustomerProfile.fromJson(body['customer'] as Map<String, dynamic>);
  }

  /// Exclui a conta do cliente logado. Pede a senha de novo.
  Future<void> deleteAccount({required String password}) async {
    await _json(
      'DELETE',
      '/customers/me',
      body: {'password': password},
      auth: true,
      fallback: 'Não foi possível excluir a conta.',
    );
  }

  /// Troca a senha e devolve o token novo (o antigo deixa de valer).
  Future<String> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    final body = await _json(
      'POST',
      '/customers/me/password',
      body: {
        'current_password': currentPassword,
        'new_password': newPassword,
      },
      auth: true,
      fallback: 'Não foi possível trocar a senha.',
    );
    return body['token'] as String;
  }

  /// Pedidos do cliente, no formato do rastreamento (`order` e `timeline`).
  Future<List<Map<String, dynamic>>> fetchMyOrders() async {
    final body = await _json(
      'GET',
      '/customers/me/orders',
      auth: true,
      fallback: 'Não foi possível carregar seus pedidos.',
    );
    final raw = body['orders'] as List<dynamic>? ?? const [];
    return raw.cast<Map<String, dynamic>>();
  }

  Future<Set<int>> fetchFavorites() async {
    final body = await _json(
      'GET',
      '/customers/me/favorites',
      auth: true,
      fallback: 'Não foi possível carregar seus favoritos.',
    );
    final raw = body['product_ids'] as List<dynamic>? ?? const [];
    return raw.map((id) => (id as num).toInt()).toSet();
  }

  Future<void> saveFavorites(Set<int> productIds) async {
    await _json(
      'PUT',
      '/customers/me/favorites',
      body: {'product_ids': productIds.toList()},
      auth: true,
      fallback: 'Não foi possível salvar seus favoritos.',
    );
  }
}

class ApiException implements Exception {
  ApiException(this.message, {this.unauthorized = false});

  final String message;

  /// `true` quando a sessão do cliente expirou ou foi invalidada.
  final bool unauthorized;

  @override
  String toString() => message;
}
