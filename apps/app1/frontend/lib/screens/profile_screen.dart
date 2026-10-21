import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/account/account_login_prompt.dart';
import 'package:tri_docuras/account/account_scope.dart';
import 'package:tri_docuras/checkout/delivery_address.dart';
import 'package:tri_docuras/legal/legal_screen.dart';
import 'package:tri_docuras/screens/account_edit_screen.dart';
import 'package:tri_docuras/services/api_service.dart';
import 'package:tri_docuras/config.dart';
import 'package:tri_docuras/store_config_holder.dart';
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
              'Bem-vindo à ${StoreConfigHolder.instance.config.appName}',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 20),
            const _AccountCard(),
            const SizedBox(height: 12),
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
              action: StoreConfigHolder.instance.storeWhatsApp == null
                  ? null
                  : TdButton(
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
    final phone = StoreConfigHolder.instance.storeWhatsApp;
    if (phone == null || phone.isEmpty) return;
    final uri = Uri.parse('https://wa.me/$phone');
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

/// Conta do cliente: convite para entrar, ou dados e saída quando logado.
class _AccountCard extends StatelessWidget {
  const _AccountCard();

  @override
  Widget build(BuildContext context) {
    final account = AccountScope.of(context);
    if (!account.isLoggedIn) {
      return const AccountLoginPrompt(
        message:
            'Entre ou crie sua conta para comprar, acompanhar seus pedidos e salvar seus endereços.',
      );
    }

    final profile = account.profile;
    return _InfoCard(
      icon: Icons.person_outline,
      title: profile?.name ?? 'Minha conta',
      body: profile == null
          ? 'Não foi possível carregar sua conta agora. Tente de novo mais tarde.'
          : profile.email,
      action: profile == null
          ? null
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TdButton(
                  label: 'Meus dados e endereços',
                  variant: TdButtonVariant.soft,
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => AccountEditScreen(profile: profile),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                TdButton(
                  label: 'Termos de Compra',
                  variant: TdButtonVariant.soft,
                  onPressed: () => openLegalPage(context, LegalPage.terms),
                ),
                const SizedBox(height: 8),
                TdButton(
                  label: 'Política de Privacidade',
                  variant: TdButtonVariant.soft,
                  onPressed: () => openLegalPage(context, LegalPage.privacy),
                ),
                const SizedBox(height: 8),
                TdButton(
                  label: 'Sair da conta',
                  variant: TdButtonVariant.outline,
                  onPressed: () => account.logout(),
                ),
                const SizedBox(height: 8),
                TdButton(
                  label: 'Baixar meus dados',
                  variant: TdButtonVariant.soft,
                  onPressed: () => _showDataExport(context),
                ),
                const SizedBox(height: 8),
                TdButton(
                  label: 'Excluir conta',
                  variant: TdButtonVariant.outline,
                  onPressed: () => _confirmDeleteAccount(context),
                ),
              ],
            ),
    );
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

/// Mostra a cópia dos dados do cliente em texto, para ler ou copiar.
Future<void> _showDataExport(BuildContext context) async {
  final account = AccountScope.of(context);
  final messenger = ScaffoldMessenger.of(context);
  try {
    final data = await account.exportData();
    if (!context.mounted) return;
    final text = const JsonEncoder.withIndent('  ').convert(data);
    await showDialog<void>(
      context: context,
      builder: (_) => _DataExportDialog(text: text),
    );
  } on ApiException catch (error) {
    messenger.showSnackBar(SnackBar(content: Text(error.message)));
  }
}

class _DataExportDialog extends StatelessWidget {
  const _DataExportDialog({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Meus dados'),
      content: SizedBox(
        height: 360,
        width: double.maxFinite,
        child: SingleChildScrollView(
          child: SelectableText(
            text,
            style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () {
            Clipboard.setData(ClipboardData(text: text));
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Dados copiados.')),
            );
          },
          child: const Text('Copiar'),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Fechar'),
        ),
      ],
    );
  }
}

/// Pede a senha e, se confirmada, exclui a conta e encerra a sessão.
Future<void> _confirmDeleteAccount(BuildContext context) async {
  final password = await showDialog<String>(
    context: context,
    builder: (_) => const _DeleteAccountDialog(),
  );
  if (password == null || password.isEmpty || !context.mounted) return;

  final account = AccountScope.of(context);
  final messenger = ScaffoldMessenger.of(context);
  try {
    await account.deleteAccount(password: password);
    messenger.showSnackBar(
      const SnackBar(content: Text('Sua conta foi excluída.')),
    );
  } on ApiException catch (error) {
    messenger.showSnackBar(SnackBar(content: Text(error.message)));
  }
}

class _DeleteAccountDialog extends StatefulWidget {
  const _DeleteAccountDialog();

  @override
  State<_DeleteAccountDialog> createState() => _DeleteAccountDialogState();
}

class _DeleteAccountDialogState extends State<_DeleteAccountDialog> {
  final _passwordController = TextEditingController();

  @override
  void dispose() {
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Excluir conta?'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Seus dados pessoais serão apagados e isso não dá para desfazer. '
            'Os pedidos continuam no registro da loja, sem seu nome nem seu '
            'contato. Para confirmar, digite sua senha.',
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _passwordController,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'Senha'),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancelar'),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(_passwordController.text),
          child: const Text('Excluir conta'),
        ),
      ],
    );
  }
}
