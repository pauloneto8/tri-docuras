import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/widgets/td_button.dart';

/// Falha ao carregar produtos da API, com botão para tentar de novo.
class TdLoadError extends StatelessWidget {
  const TdLoadError({super.key, required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppColors.cream,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'Não foi possível carregar os produtos.',
                textAlign: TextAlign.center,
                style: GoogleFonts.poppins(
                  fontSize: 16,
                  color: AppColors.brown,
                ),
              ),
              const SizedBox(height: 16),
              TdButton(
                label: 'Tentar de novo',
                expand: false,
                onPressed: onRetry,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
