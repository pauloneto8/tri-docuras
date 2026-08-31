import 'package:tri_docuras/checkout/delivery_address.dart';

/// Validadores do endereço de entrega (Nazaré da Mata - PE).
abstract final class DeliveryAddressValidators {
  static const streetMaxLength = 120;
  static const numberMaxLength = 20;
  static const complementMaxLength = 80;
  static const neighborhoodMaxLength = 80;
  static const referenceMaxLength = 120;

  static final _controlChars = RegExp(r'[\x00-\x1F\x7F]');

  static String sanitize(String raw) =>
      raw.trim().replaceAll(RegExp(r'\s+'), ' ');

  static String? validateStreet(String raw) {
    final value = sanitize(raw);
    if (value.isEmpty) return 'Informe a rua';
    if (_controlChars.hasMatch(value)) return 'Rua contém caracteres inválidos';
    if (value.length < 3) return 'Rua muito curta';
    if (value.length > streetMaxLength) return 'Rua muito longa';
    return null;
  }

  static String? validateNumber(String raw) {
    final value = sanitize(raw);
    if (value.isEmpty) return 'Informe o número';
    if (_controlChars.hasMatch(value)) return 'Número inválido';
    if (value.length > numberMaxLength) return 'Número muito longo';
    return null;
  }

  static String? validateComplement(String raw) {
    final value = sanitize(raw);
    if (value.isEmpty) return null;
    if (_controlChars.hasMatch(value)) return 'Complemento inválido';
    if (value.length > complementMaxLength) return 'Complemento muito longo';
    return null;
  }

  static String? validateNeighborhood(String raw) {
    final value = sanitize(raw);
    if (value.isEmpty) return 'Informe o bairro';
    if (_controlChars.hasMatch(value)) return 'Bairro inválido';
    if (value.length < 2) return 'Bairro muito curto';
    if (value.length > neighborhoodMaxLength) return 'Bairro muito longo';
    return null;
  }

  static String? validateReference(String raw) {
    final value = sanitize(raw);
    if (value.isEmpty) return 'Informe um ponto de referência';
    if (_controlChars.hasMatch(value)) return 'Referência inválida';
    if (value.length < 5) return 'Descreva melhor o ponto de referência';
    if (value.length > referenceMaxLength) return 'Referência muito longa';
    return null;
  }

  static bool isValid({
    required String street,
    required String number,
    required String complement,
    required String neighborhood,
    required String reference,
  }) =>
      validateStreet(street) == null &&
      validateNumber(number) == null &&
      validateComplement(complement) == null &&
      validateNeighborhood(neighborhood) == null &&
      validateReference(reference) == null;

  static DeliveryAddress? buildIfValid({
    required String street,
    required String number,
    required String complement,
    required String neighborhood,
    required String reference,
  }) {
    if (!isValid(
      street: street,
      number: number,
      complement: complement,
      neighborhood: neighborhood,
      reference: reference,
    )) {
      return null;
    }
    final complementSanitized = sanitize(complement);
    return DeliveryAddress(
      street: sanitize(street),
      number: sanitize(number),
      complement: complementSanitized.isEmpty ? null : complementSanitized,
      neighborhood: sanitize(neighborhood),
      reference: sanitize(reference),
    );
  }
}
