import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:tri_docuras/cart/cart_item.dart';
import 'package:tri_docuras/checkout/checkout_draft.dart';
import 'package:tri_docuras/checkout/order_payload.dart';
import 'package:tri_docuras/config.dart';
import 'package:tri_docuras/models/created_order.dart';
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
      headers: {'Content-Type': 'application/json'},
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

    final message = body['error'] as String? ??
        'Não foi possível registrar o pedido (${response.statusCode}).';
    throw ApiException(message);
  }

  Future<OrderStatus> fetchOrderStatus(String orderId) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}/orders/$orderId');
    final response = await _client.get(uri);

    Map<String, dynamic> body;
    try {
      body = jsonDecode(response.body) as Map<String, dynamic>;
    } on FormatException {
      throw ApiException('Resposta inválida do servidor (${response.statusCode}).');
    }

    if (response.statusCode == 200) {
      return OrderStatus.fromJson(body);
    }

    final message = body['error'] as String? ??
        'Não foi possível consultar o pedido (${response.statusCode}).';
    throw ApiException(message);
  }

  Future<OrderTracking> fetchOrderTracking(String orderId) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}/orders/$orderId/tracking');
    final response = await _client.get(uri);

    Map<String, dynamic> body;
    try {
      body = jsonDecode(response.body) as Map<String, dynamic>;
    } on FormatException {
      throw ApiException('Resposta inválida do servidor (${response.statusCode}).');
    }

    if (response.statusCode == 200) {
      return OrderTracking.fromJson(body);
    }

    final message = body['error'] as String? ??
        'Não foi possível consultar o pedido (${response.statusCode}).';
    throw ApiException(message);
  }

  Future<PixPayment> createPix(String orderId) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}/orders/$orderId/pix');
    final response = await _client.post(
      uri,
      headers: {'Content-Type': 'application/json'},
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

    final message = body['error'] as String? ??
        'Não foi possível gerar o Pix (${response.statusCode}).';
    throw ApiException(message);
  }

  List<Product> fallbackProducts() {
    return const [
      Product(
        id: 1,
        name: 'Brownie Tradicional',
        description: 'Brownie amanteigado clássico, macio por dentro.',
        price: 12.0,
        featured: true,
        category: 'brownies',
      ),
      Product(
        id: 2,
        name: 'Ninho c/ Nutella',
        description: 'Recheado e coberto com Nutella derretida e leite Ninho.',
        price: 15.0,
        featured: true,
        category: 'brownies',
      ),
      Product(
        id: 3,
        name: 'Brownie c/ Nozes',
        description: 'Chocolate intenso com nozes caramelizadas.',
        price: 14.0,
        featured: false,
        category: 'brownies',
      ),
      Product(
        id: 4,
        name: 'Caixa Presente (4un)',
        description: 'Seleção especial de 4 brownies para presentear.',
        price: 48.0,
        featured: false,
        category: 'combos',
      ),
    ];
  }
}

class ApiException implements Exception {
  ApiException(this.message);

  final String message;

  @override
  String toString() => message;
}
