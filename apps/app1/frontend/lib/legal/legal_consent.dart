import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/legal/legal_screen.dart';
import 'package:tri_docuras/theme/app_colors.dart';

/// Caixa de aceite dos Termos de Compra e da Política de Privacidade, com
/// atalhos para ler cada texto. `onChanged` nulo desabilita a caixa.
class LegalConsent extends StatelessWidget {
  const LegalConsent({
    super.key,
    required this.value,
    required this.onChanged,
  });

  final bool value;
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Checkbox(
          value: value,
          onChanged: onChanged == null
              ? null
              : (checked) => onChanged!(checked ?? false),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Li e aceito os Termos de Compra e a Política de Privacidade.',
                  style: GoogleFonts.poppins(
                    fontSize: 14,
                    color: AppColors.brown,
                  ),
                ),
                Wrap(
                  spacing: 4,
                  children: [
                    TextButton(
                      onPressed: () => openLegalPage(context, LegalPage.terms),
                      child: const Text('Ler os termos'),
                    ),
                    TextButton(
                      onPressed: () =>
                          openLegalPage(context, LegalPage.privacy),
                      child: const Text('Ler a privacidade'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
