/// Endereço de entrega — apenas Nazaré da Mata - PE (CEP 55.800-000).
class DeliveryAddress {
  const DeliveryAddress({
    required this.street,
    required this.number,
    this.complement,
    required this.neighborhood,
    required this.reference,
  });

  static const city = 'Nazaré da Mata';
  static const state = 'PE';
  static const postalCode = '55800-000';
  static const postalCodeLabel = '55.800-000';
  static const cityLabel = 'Nazaré da Mata - PE';

  final String street;
  final String number;
  final String? complement;
  final String neighborhood;
  final String reference;

  String get line1 {
    final base = '$street, $number';
    if (complement != null && complement!.isNotEmpty) {
      return '$base, $complement';
    }
    return base;
  }

  String get formattedSummary => '$line1 — $neighborhood';

  String get fullDescription =>
      '$formattedSummary\nRef.: $reference\n$cityLabel · CEP $postalCodeLabel';
}
