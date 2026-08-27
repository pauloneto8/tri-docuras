/// Validadores puros do checkout (sem Flutter) — seguros para unit test.
abstract final class CheckoutValidators {
  static const nameMinLength = 3;
  static const nameMaxLength = 80;

  /// Letras Unicode, espaços, hífen e apóstrofo.
  static final _namePattern = RegExp(
    r"^[\p{L}][\p{L}\s'\-]{1,78}[\p{L}]$",
    unicode: true,
  );

  static final _controlChars = RegExp(r'[\x00-\x1F\x7F]');

  /// Normaliza espaços e trim.
  static String sanitizeName(String raw) =>
      raw.trim().replaceAll(RegExp(r'\s+'), ' ');

  /// Extrai só dígitos do telefone.
  static String digitsOnly(String raw) =>
      raw.replaceAll(RegExp(r'\D'), '');

  /// Retorna mensagem de erro ou `null` se válido.
  static String? validateName(String raw) {
    final name = sanitizeName(raw);
    if (name.isEmpty) {
      return 'Informe seu nome completo';
    }
    if (_controlChars.hasMatch(name)) {
      return 'Nome contém caracteres inválidos';
    }
    if (name.length < nameMinLength) {
      return 'Nome muito curto';
    }
    if (name.length > nameMaxLength) {
      return 'Nome muito longo';
    }
    if (!_namePattern.hasMatch(name)) {
      return 'Use apenas letras, espaços, hífen ou apóstrofo';
    }
    return null;
  }

  /// WhatsApp BR: 11 dígitos (DDD + 9 + 8 dígitos).
  /// Retorna mensagem de erro ou `null` se válido.
  static String? validateWhatsApp(String raw) {
    final digits = digitsOnly(raw);
    if (digits.isEmpty) {
      return 'Informe seu WhatsApp';
    }
    if (digits.length != 11) {
      return 'WhatsApp deve ter 11 dígitos (DDD + celular)';
    }
    final ddd = int.tryParse(digits.substring(0, 2)) ?? 0;
    if (ddd < 11 || ddd > 99) {
      return 'DDD inválido';
    }
    if (digits[2] != '9') {
      return 'Informe um celular com 9 dígitos';
    }
    if (RegExp(r'^(\d)\1{10}$').hasMatch(digits)) {
      return 'Número de WhatsApp inválido';
    }
    return null;
  }

  static bool isNameValid(String raw) => validateName(raw) == null;

  static bool isWhatsAppValid(String raw) => validateWhatsApp(raw) == null;
}
