import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/screens/account_auth_screen.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/widgets/td_button.dart';

/// Aviso com botão para entrar ou criar conta. Usado onde a tela precisa de
/// uma conta (checkout, pedidos).
class AccountLoginPrompt extends StatelessWidget {
  const AccountLoginPrompt({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.brown.withValues(alpha: 0.12)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              message,
              style: GoogleFonts.poppins(
                fontSize: 14,
                color: AppColors.dark,
                height: 1.45,
              ),
            ),
            const SizedBox(height: 12),
            TdButton(
              label: 'Entrar ou criar conta',
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const AccountAuthScreen(),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
