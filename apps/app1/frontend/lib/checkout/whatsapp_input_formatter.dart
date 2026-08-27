import 'package:flutter/services.dart';

/// Máscara BR `(DD) 9XXXX-XXXX` a partir de dígitos.
class WhatsAppInputFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    final digits = newValue.text.replaceAll(RegExp(r'\D'), '');
    final limited = digits.length > 11 ? digits.substring(0, 11) : digits;
    final masked = _mask(limited);
    return TextEditingValue(
      text: masked,
      selection: TextSelection.collapsed(offset: masked.length),
    );
  }

  static String _mask(String digits) {
    if (digits.isEmpty) return '';
    final buf = StringBuffer('(');
    if (digits.isNotEmpty) buf.write(digits[0]);
    if (digits.length >= 2) {
      buf.write(digits[1]);
      buf.write(') ');
    }
    if (digits.length > 2) {
      final midEnd = digits.length < 7 ? digits.length : 7;
      buf.write(digits.substring(2, midEnd));
    }
    if (digits.length > 7) {
      buf.write('-');
      buf.write(digits.substring(7));
    }
    return buf.toString();
  }
}
