import 'package:tri_docuras_api/customer_auth.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/order_tracking.dart';
import 'package:tri_docuras_api/orders.dart';

class CustomerException implements Exception {
  CustomerException(this.message, {this.statusCode = 400});

  final String message;
  final int statusCode;

  @override
  String toString() => message;
}

const maxCustomerAddresses = 5;

class CustomerInput {
  CustomerInput({
    required this.email,
    required this.password,
    required this.name,
    required this.whatsapp,
  });

  final String email;
  final String password;
  final String name;
  final String whatsapp;
}

class CustomerAddressInput {
  CustomerAddressInput({
    required this.label,
    required this.street,
    required this.number,
    required this.neighborhood,
    this.complement,
    this.reference,
  });

  final String label;
  final String street;
  final String number;
  final String neighborhood;
  final String? complement;
  final String? reference;
}

/// Valida cadastro. Lança [CustomerException] com a mensagem para o cliente.
CustomerInput parseCustomerInput(Map<String, dynamic> body) {
  final email = CustomerAuth.normalizeEmail(body['email']);
  if (email == null) {
    throw CustomerException('Informe um e-mail válido.');
  }

  final password = body['password']?.toString() ?? '';
  final passwordError = CustomerAuth.passwordProblem(password);
  if (passwordError != null) throw CustomerException(passwordError);

  if (body['accepted_terms'] != true) {
    throw CustomerException(
      'Confirme que leu os Termos de Compra e a Política de Privacidade.',
    );
  }

  final profile = parseProfileFields(body);
  return CustomerInput(
    email: email,
    password: password,
    name: profile.name,
    whatsapp: profile.whatsapp,
  );
}

/// Nome e WhatsApp, validados. Usado no cadastro e na edição do perfil.
({String name, String whatsapp}) parseProfileFields(Map<String, dynamic> body) {
  final name = _cleanName(body['name']);
  if (name.length < 2) throw CustomerException('Informe o nome completo.');

  final whatsapp = _digitsOnly(body['whatsapp']);
  if (whatsapp.length != 11) {
    throw CustomerException('Informe um WhatsApp válido com 11 dígitos.');
  }
  return (name: name, whatsapp: whatsapp);
}

/// Valida a lista de endereços (substitui a lista inteira ao salvar).
List<CustomerAddressInput> parseCustomerAddresses(Object? raw) {
  if (raw == null) return const [];
  if (raw is! List) throw CustomerException('Endereços em formato inválido.');
  if (raw.length > maxCustomerAddresses) {
    throw CustomerException(
      'Você pode salvar até $maxCustomerAddresses endereços.',
    );
  }

  return raw.map((item) {
    if (item is! Map) {
      throw CustomerException('Endereços em formato inválido.');
    }
    final street = _cleanText(item['street']);
    final number = _cleanText(item['number']);
    final neighborhood = _cleanText(item['neighborhood']);
    if (street.length < 2 || number.isEmpty || neighborhood.length < 2) {
      throw CustomerException(
        'Endereço incompleto: informe rua, número e bairro.',
      );
    }
    final label = _cleanText(item['label']);
    return CustomerAddressInput(
      label: label.isEmpty ? 'Endereço' : label,
      street: street,
      number: number,
      neighborhood: neighborhood,
      complement: _nullableText(item['complement']),
      reference: _nullableText(item['reference']),
    );
  }).toList();
}

/// Cria a conta. Usa `ON CONFLICT` para não vazar se o e-mail já existe:
/// a resposta de "já existe" é a mesma de qualquer erro de cadastro.
Future<Map<String, Object?>> createCustomer(CustomerInput input) async {
  final connection = await getConnection();
  final result = await connection.execute(
    r'''
    INSERT INTO customers (email, password_hash, name, whatsapp, accepted_terms_at)
    VALUES ($1, $2, $3, $4, NOW())
    ON CONFLICT (email) DO NOTHING
    RETURNING id, email, name, whatsapp;
    ''',
    parameters: [
      input.email,
      CustomerAuth.hashPassword(input.password),
      input.name,
      input.whatsapp,
    ],
  );

  if (result.isEmpty) {
    throw CustomerException(
      'Não foi possível criar a conta. Tente entrar ou use outro e-mail.',
      statusCode: 409,
    );
  }

  final row = result.first;
  return {
    'id': (row[0] as num).toInt(),
    'email': row[1],
    'name': row[2],
    'whatsapp': row[3],
    'addresses': <Map<String, Object?>>[],
  };
}

/// Confere e-mail e senha. Devolve o id e a versão da sessão, ou `null` com
/// a mesma resposta para "e-mail não existe" e "senha errada".
Future<({int id, int sessionVersion})?> authenticateCustomer(
  String email,
  String password,
) async {
  final connection = await getConnection();
  final result = await connection.execute(
    r'''
    SELECT id, password_hash, session_version
    FROM customers
    WHERE email = $1 AND disabled_at IS NULL
    LIMIT 1;
    ''',
    parameters: [email],
  );

  if (result.isEmpty) {
    // Mesmo custo de bcrypt, para o tempo não revelar que a conta não existe.
    CustomerAuth.verifyPassword(password, CustomerAuth.dummyHash);
    return null;
  }

  final row = result.first;
  final ok = CustomerAuth.verifyPassword(password, row[1] as String);
  if (!ok) return null;
  return (
    id: (row[0] as num).toInt(),
    sessionVersion: (row[2] as num).toInt(),
  );
}

/// Valida o token do cabeçalho e confere no banco que a conta está ativa e
/// que a sessão não foi invalidada por troca de senha.
Future<CustomerSession?> resolveCustomerSession(String? authorization) async {
  final token = CustomerAuth.bearerToken(authorization);
  final session = CustomerAuth.parseToken(token, DateTime.now());
  if (session == null) return null;

  final connection = await getConnection();
  final result = await connection.execute(
    r'''
    SELECT session_version FROM customers
    WHERE id = $1 AND disabled_at IS NULL
    LIMIT 1;
    ''',
    parameters: [session.customerId],
  );
  if (result.isEmpty) return null;

  final currentVersion = (result.first[0] as num).toInt();
  if (currentVersion != session.sessionVersion) return null;
  return session;
}

/// `true` se o cliente logado (ou ninguém, se [authorization] é nulo) pode
/// ver o pedido. Pedido inexistente vira `false`, igual a pedido de outro
/// cliente, para não revelar quais IDs existem.
Future<bool> customerMayViewOrder(
  String publicId,
  String? authorization,
) async {
  final order = await getOrderByPublicId(publicId);
  if (order.isEmpty) return false;

  final session = await resolveCustomerSession(authorization);
  return canAccessOrder(
    orderCustomerId: order['customer_id'] as int?,
    sessionCustomerId: session?.customerId,
  );
}

/// Perfil com endereços, ou `null` se a conta não existe.
Future<Map<String, Object?>?> getCustomerProfile(int customerId) async {
  final connection = await getConnection();
  final result = await connection.execute(
    r'''
    SELECT id, email, name, whatsapp
    FROM customers
    WHERE id = $1 AND disabled_at IS NULL
    LIMIT 1;
    ''',
    parameters: [customerId],
  );
  if (result.isEmpty) return null;

  final row = result.first;
  final addresses = await connection.execute(
    r'''
    SELECT label, street, number, complement, neighborhood, reference
    FROM customer_addresses
    WHERE customer_id = $1
    ORDER BY id ASC;
    ''',
    parameters: [customerId],
  );

  return {
    'id': (row[0] as num).toInt(),
    'email': row[1],
    'name': row[2],
    'whatsapp': row[3],
    'addresses': addresses
        .map(
          (a) => {
            'label': a[0],
            'street': a[1],
            'number': a[2],
            'complement': a[3],
            'neighborhood': a[4],
            'reference': a[5],
          },
        )
        .toList(),
  };
}

/// Atualiza nome, WhatsApp e endereços. E-mail não muda por aqui.
Future<void> updateCustomerProfile(
  int customerId, {
  required String name,
  required String whatsapp,
  required List<CustomerAddressInput> addresses,
}) async {
  final connection = await getConnection();
  await connection.runTx((tx) async {
    await tx.execute(
      r'''
      UPDATE customers SET name = $2, whatsapp = $3 WHERE id = $1;
      ''',
      parameters: [customerId, name, whatsapp],
    );
    await tx.execute(
      'DELETE FROM customer_addresses WHERE customer_id = \$1;',
      parameters: [customerId],
    );
    for (final address in addresses) {
      await tx.execute(
        r'''
        INSERT INTO customer_addresses (
          customer_id, label, street, number, complement, neighborhood, reference
        ) VALUES ($1, $2, $3, $4, $5, $6, $7);
        ''',
        parameters: [
          customerId,
          address.label,
          address.street,
          address.number,
          address.complement,
          address.neighborhood,
          address.reference,
        ],
      );
    }
  });
}

/// Troca a senha. Incrementa `session_version`, o que derruba as sessões
/// antigas. Devolve a nova versão para o chamador emitir um token novo.
Future<int> changeCustomerPassword(
  int customerId, {
  required String currentPassword,
  required String newPassword,
}) async {
  final connection = await getConnection();
  final result = await connection.execute(
    r'''
    SELECT password_hash FROM customers WHERE id = $1 LIMIT 1;
    ''',
    parameters: [customerId],
  );
  if (result.isEmpty) {
    throw CustomerException('Conta não encontrada.');
  }

  final currentHash = result.first[0] as String;
  if (!CustomerAuth.verifyPassword(currentPassword, currentHash)) {
    throw CustomerException('A senha atual está incorreta.');
  }

  final updated = await connection.execute(
    r'''
    UPDATE customers
    SET password_hash = $2, session_version = session_version + 1
    WHERE id = $1
    RETURNING session_version;
    ''',
    parameters: [customerId, CustomerAuth.hashPassword(newPassword)],
  );
  return (updated.first[0] as num).toInt();
}

/// Status em que o pedido ainda não foi concluído nem cancelado. Enquanto
/// houver algum, a conta não pode ser excluída.
const openOrderStatuses = ['pending_payment', 'paid', 'preparing', 'ready'];

/// Exclui a conta do cliente (LGPD). Os pedidos continuam, porque o
/// financeiro precisa dos valores, mas ficam sem vínculo e sem dados pessoais.
Future<void> deleteCustomerAccount(
  int customerId, {
  required String password,
}) async {
  final connection = await getConnection();
  final result = await connection.execute(
    r'''
    SELECT password_hash FROM customers WHERE id = $1 LIMIT 1;
    ''',
    parameters: [customerId],
  );
  if (result.isEmpty) {
    throw CustomerException('Conta não encontrada.');
  }
  if (!CustomerAuth.verifyPassword(password, result.first[0] as String)) {
    throw CustomerException('A senha está incorreta.');
  }

  final open = await connection.execute(
    r'''
    SELECT COUNT(*) FROM orders
    WHERE customer_id = $1 AND status = ANY($2::text[]);
    ''',
    parameters: [customerId, openOrderStatuses],
  );
  if ((open.first[0] as num).toInt() > 0) {
    throw CustomerException(
      'Você tem pedidos em andamento. Aguarde a conclusão ou fale com a loja antes de excluir a conta.',
      statusCode: 409,
    );
  }

  await connection.runTx((tx) async {
    await tx.execute(
      r'''
      UPDATE orders
      SET customer_id = NULL,
          customer_name = 'Cliente excluído',
          whatsapp = '00000000000',
          delivery_street = NULL,
          delivery_number = NULL,
          delivery_complement = NULL,
          delivery_neighborhood = NULL,
          delivery_reference = NULL
      WHERE customer_id = $1;
      ''',
      parameters: [customerId],
    );
    await tx.execute(
      r'DELETE FROM customer_addresses WHERE customer_id = $1;',
      parameters: [customerId],
    );
    await tx.execute(
      r'DELETE FROM customer_favorites WHERE customer_id = $1;',
      parameters: [customerId],
    );
    await tx.execute(
      r'DELETE FROM customers WHERE id = $1;',
      parameters: [customerId],
    );
  });
}

/// Pedidos do cliente, mais recentes primeiro, no mesmo formato do
/// rastreamento público (status, total e linha do tempo).
Future<List<Map<String, Object?>>> listCustomerOrders(int customerId) async {
  final connection = await getConnection();
  final result = await connection.execute(
    r'''
    SELECT public_id FROM orders
    WHERE customer_id = $1
    ORDER BY created_at DESC
    LIMIT 50;
    ''',
    parameters: [customerId],
  );

  final orders = <Map<String, Object?>>[];
  for (final row in result) {
    orders.add(await getOrderTracking(row[0] as String));
  }
  return orders;
}

const maxCustomerFavorites = 200;

/// IDs de produto favoritos: inteiros positivos, sem repetição.
List<int> parseFavoriteIds(Object? raw) {
  if (raw == null) return const [];
  if (raw is! List) throw CustomerException('Favoritos em formato inválido.');
  if (raw.length > maxCustomerFavorites) {
    throw CustomerException('Você pode ter até $maxCustomerFavorites favoritos.');
  }

  final ids = <int>{};
  for (final item in raw) {
    final id = item is int ? item : int.tryParse(item.toString());
    if (id == null || id <= 0) {
      throw CustomerException('Favoritos em formato inválido.');
    }
    ids.add(id);
  }
  return ids.toList();
}

Future<List<int>> getCustomerFavorites(int customerId) async {
  final connection = await getConnection();
  final result = await connection.execute(
    r'''
    SELECT product_id FROM customer_favorites
    WHERE customer_id = $1
    ORDER BY created_at ASC;
    ''',
    parameters: [customerId],
  );
  return result.map((row) => (row[0] as num).toInt()).toList();
}

/// Substitui a lista inteira de favoritos. IDs de produto inexistentes são
/// ignorados pela chave estrangeira em vez de derrubar a operação.
Future<void> replaceCustomerFavorites(int customerId, List<int> productIds) async {
  final connection = await getConnection();
  await connection.runTx((tx) async {
    await tx.execute(
      r'''
      DELETE FROM customer_favorites WHERE customer_id = $1;
      ''',
      parameters: [customerId],
    );
    for (final productId in productIds) {
      await tx.execute(
        r'''
        INSERT INTO customer_favorites (customer_id, product_id)
        SELECT $1, id FROM products WHERE id = $2
        ON CONFLICT DO NOTHING;
        ''',
        parameters: [customerId, productId],
      );
    }
  });
}

String _cleanName(Object? value) {
  final raw = value?.toString().trim() ?? '';
  return raw.replaceAll(RegExp(r'\s+'), ' ');
}

String _cleanText(Object? value) => value?.toString().trim() ?? '';

String? _nullableText(Object? value) {
  final text = _cleanText(value);
  return text.isEmpty ? null : text;
}

String _digitsOnly(Object? value) =>
    (value?.toString() ?? '').replaceAll(RegExp(r'\D'), '');

/// Cópia dos dados pessoais do cliente (LGPD, direito de acesso): perfil com
/// endereços, pedidos no formato do acompanhamento e favoritos. `null` se a
/// conta não existe.
Future<Map<String, Object?>?> buildCustomerExport(int customerId) async {
  final profile = await getCustomerProfile(customerId);
  if (profile == null) return null;

  final orders = await listCustomerOrders(customerId);
  final favorites = await getCustomerFavorites(customerId);
  return {
    'exported_at': DateTime.now().toUtc().toIso8601String(),
    'customer': {
      'email': profile['email'],
      'name': profile['name'],
      'whatsapp': profile['whatsapp'],
      'addresses': profile['addresses'],
    },
    'orders': orders,
    'favorite_product_ids': favorites,
  };
}
