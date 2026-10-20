/// Endereço salvo na conta do cliente.
class CustomerAddress {
  const CustomerAddress({
    required this.label,
    required this.street,
    required this.number,
    required this.neighborhood,
    this.complement,
    this.reference,
  });

  factory CustomerAddress.fromJson(Map<String, dynamic> json) {
    return CustomerAddress(
      label: json['label'] as String? ?? 'Endereço',
      street: json['street'] as String? ?? '',
      number: json['number'] as String? ?? '',
      neighborhood: json['neighborhood'] as String? ?? '',
      complement: json['complement'] as String?,
      reference: json['reference'] as String?,
    );
  }

  final String label;
  final String street;
  final String number;
  final String neighborhood;
  final String? complement;
  final String? reference;

  Map<String, dynamic> toJson() => {
        'label': label,
        'street': street,
        'number': number,
        'neighborhood': neighborhood,
        if (complement != null && complement!.isNotEmpty)
          'complement': complement,
        if (reference != null && reference!.isNotEmpty) 'reference': reference,
      };

  String get summary => '$street, $number · $neighborhood';
}

/// Perfil do cliente logado (vem de `GET /api/customers/me`).
class CustomerProfile {
  const CustomerProfile({
    required this.id,
    required this.email,
    required this.name,
    required this.whatsapp,
    this.addresses = const [],
  });

  factory CustomerProfile.fromJson(Map<String, dynamic> json) {
    final raw = json['addresses'] as List<dynamic>? ?? const [];
    return CustomerProfile(
      id: (json['id'] as num).toInt(),
      email: json['email'] as String? ?? '',
      name: json['name'] as String? ?? '',
      whatsapp: json['whatsapp'] as String? ?? '',
      addresses: raw
          .map((item) => CustomerAddress.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }

  final int id;
  final String email;
  final String name;
  final String whatsapp;
  final List<CustomerAddress> addresses;
}

/// Resposta de cadastro e login: perfil e token da sessão.
class CustomerSession {
  const CustomerSession({required this.token, required this.customer});

  factory CustomerSession.fromJson(Map<String, dynamic> json) {
    return CustomerSession(
      token: json['token'] as String,
      customer: CustomerProfile.fromJson(
        json['customer'] as Map<String, dynamic>,
      ),
    );
  }

  final String token;
  final CustomerProfile customer;
}
