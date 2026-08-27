import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:tri_docuras/config.dart';
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
