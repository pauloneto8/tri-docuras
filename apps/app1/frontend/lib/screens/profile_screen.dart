import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/checkout/delivery_address.dart';
import 'package:tri_docuras/config.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/widgets/td_button.dart';
import 'package:url_launcher/url_launcher.dart';

/// Perfil / informações da loja (aba 4 da bottom nav).
class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppColors.cream,
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Olá!',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 4),
            Text(
              'Bem-vindo à ${AppConfig.appName}',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 20),
            const _InfoCard(
              icon: Icons.storefront_outlined,
              title: 'Retirada na loja',
              body:
                  'Hoje, entre 16h e 17h.\nEndereço informado no pedido ou pelo WhatsApp.',
            ),
            const SizedBox(height: 12),
            const _InfoCard(
              icon: Icons.delivery_dining_outlined,
              title: 'Entrega',
              body:
                  '${DeliveryAddress.cityLabel} · CEP ${DeliveryAddress.postalCodeLabel}\n'
                  'Taxa de R\$ 6,00 para receber em casa.',
            ),
            const SizedBox(height: 12),
            _InfoCard(
              icon: Icons.payments_outlined,
              title: 'Pagamento',
              body: 'Pix via Mercado Pago — confirmação automática após o pagamento.',
            ),
            const SizedBox(height: 12),
            _InfoCard(
              icon: Icons.chat_outlined,
              title: 'Fale conosco',
              body: 'Dúvidas sobre pedidos? Chame no WhatsApp.',
              action: TdButton(
                label: 'WhatsApp',
                expand: false,
                variant: TdButtonVariant.soft,
                onPressed: () => _openWhatsApp(context),
              ),
            ),
            const SizedBox(height: 20),
            Text(
              AppConfig.tagline,
              textAlign: TextAlign.center,
              style: GoogleFonts.poppins(
                fontSize: 13,
                color: AppColors.brown.withValues(alpha: 0.85),
                height: 1.4,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Versão ${AppConfig.appVersion}',
              textAlign: TextAlign.center,
              style: GoogleFonts.poppins(
                fontSize: 12,
                color: AppColors.brown.withValues(alpha: 0.6),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openWhatsApp(BuildContext context) async {
    final uri = Uri.parse('https://wa.me/${AppConfig.storeWhatsApp}');
    final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!launched && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Não foi possível abrir o WhatsApp.',
            style: GoogleFonts.poppins(fontSize: 13),
          ),
          behavior: SnackBarBehavior.floating,
          backgroundColor: AppColors.dark,
        ),
      );
    }
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({
    required this.icon,
    required this.title,
    required this.body,
    this.action,
  });

  final IconData icon;
  final String title;
  final String body;
  final Widget? action;

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
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: AppColors.pinkDeep, size: 22),
                const SizedBox(width: 10),
                Text(
                  title,
                  style: GoogleFonts.poppins(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: AppColors.dark,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              body,
              style: GoogleFonts.poppins(
                fontSize: 14,
                fontWeight: FontWeight.w400,
                color: AppColors.brown,
                height: 1.45,
              ),
            ),
            if (action != null) ...[
              const SizedBox(height: 12),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}

/// Menu lateral (ícone ☰ no catálogo).
class StoreMenuSheet extends StatelessWidget {
  const StoreMenuSheet({super.key});

  static Future<void> show(BuildContext context) {
    return showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.card,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => const StoreMenuSheet(),
    );
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              AppConfig.appName,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.displayMedium,
            ),
            const SizedBox(height: 4),
            Text(
              AppConfig.tagline,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 20),
            _MenuTile(
              icon: Icons.cake_outlined,
              label: 'Brownies artesanais',
              subtitle: 'Feitos sob encomenda em Nazaré da Mata - PE',
            ),
            _MenuTile(
              icon: Icons.schedule_outlined,
              label: 'Horário de retirada',
              subtitle: 'Hoje, 16h às 17h',
            ),
            _MenuTile(
              icon: Icons.location_on_outlined,
              label: 'Entrega local',
              subtitle: '${DeliveryAddress.cityLabel} · CEP ${DeliveryAddress.postalCodeLabel}',
            ),
            const SizedBox(height: 8),
            TdButton(
              label: 'Fechar',
              variant: TdButtonVariant.outline,
              onPressed: () => Navigator.of(context).pop(),
            ),
          ],
        ),
      ),
    );
  }
}

class _MenuTile extends StatelessWidget {
  const _MenuTile({
    required this.icon,
    required this.label,
    required this.subtitle,
  });

  final IconData icon;
  final String label;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: AppColors.tan, size: 22),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: GoogleFonts.poppins(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: AppColors.dark,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: GoogleFonts.poppins(
                    fontSize: 13,
                    color: AppColors.brown,
                    height: 1.35,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
