import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/legal/legal_texts.dart';
import 'package:tri_docuras/store_config_holder.dart';
import 'package:tri_docuras/theme/app_colors.dart';

enum LegalPage { terms, privacy }

/// Abre os Termos de Compra ou a Política de Privacidade com o texto atual
/// da loja (nome do vendedor e WhatsApp vêm da configuração pública).
void openLegalPage(BuildContext context, LegalPage page) {
  final config = StoreConfigHolder.instance.config;
  final isTerms = page == LegalPage.terms;
  Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => LegalScreen(
        title: isTerms ? 'Termos de Compra' : 'Política de Privacidade',
        sections: isTerms ? termsSections(config) : privacySections(config),
      ),
    ),
  );
}

class LegalScreen extends StatelessWidget {
  const LegalScreen({super.key, required this.title, required this.sections});

  final String title;
  final List<LegalSection> sections;

  @override
  Widget build(BuildContext context) {
    final config = StoreConfigHolder.instance.config;
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: AppColors.cream,
      appBar: AppBar(
        backgroundColor: AppColors.cream,
        foregroundColor: AppColors.dark,
        elevation: 0,
        title: Text(
          title,
          style: GoogleFonts.poppins(
            fontWeight: FontWeight.w600,
            color: AppColors.dark,
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: [
          for (final section in sections) ...[
            Text(section.title, style: theme.textTheme.titleMedium),
            const SizedBox(height: 6),
            for (final paragraph in section.paragraphs)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(paragraph, style: theme.textTheme.bodyMedium),
              ),
            const SizedBox(height: 12),
          ],
          const Divider(),
          Text(
            'Tri Doçuras · ${sellerText(config)}',
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
