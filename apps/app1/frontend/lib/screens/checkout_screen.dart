import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/cart/cart_scope.dart';
import 'package:tri_docuras/cart/delivery_mode.dart';
import 'package:tri_docuras/checkout/checkout_draft.dart';
import 'package:tri_docuras/checkout/checkout_validators.dart';
import 'package:tri_docuras/checkout/whatsapp_input_formatter.dart';
import 'package:tri_docuras/screens/pix_screen.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/theme/app_theme.dart';
import 'package:tri_docuras/widgets/td_button.dart';
import 'package:tri_docuras/widgets/td_icon_button.dart';
import 'package:tri_docuras/widgets/td_text_field.dart';

/// Checkout (tela 4) — formulário + resumo; Gerar Pix abre placeholder da tela 5.
class CheckoutScreen extends StatefulWidget {
  const CheckoutScreen({super.key});

  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  final _nameController = TextEditingController();
  final _whatsappController = TextEditingController();

  bool _submitted = false;

  @override
  void dispose() {
    _nameController.dispose();
    _whatsappController.dispose();
    super.dispose();
  }

  bool get _formValid =>
      CheckoutValidators.isNameValid(_nameController.text) &&
      CheckoutValidators.isWhatsAppValid(_whatsappController.text);

  String? get _nameError {
    if (!_submitted && _nameController.text.isEmpty) return null;
    return CheckoutValidators.validateName(_nameController.text);
  }

  String? get _whatsappError {
    if (!_submitted && _whatsappController.text.isEmpty) return null;
    return CheckoutValidators.validateWhatsApp(_whatsappController.text);
  }

  void _onFieldChanged(String _) => setState(() {});

  void _generatePix() {
    setState(() => _submitted = true);
    final cart = CartScope.of(context);
    if (cart.items.isEmpty) {
      Navigator.of(context).pop();
      return;
    }
    if (!_formValid) return;

    final draft = CheckoutDraft(
      customerName: CheckoutValidators.sanitizeName(_nameController.text),
      whatsappDigits: CheckoutValidators.digitsOnly(_whatsappController.text),
      total: cart.total,
    );

    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => PixScreen(draft: draft),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cart = CartScope.of(context);

    if (cart.items.isEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && Navigator.of(context).canPop()) {
          Navigator.of(context).pop();
        }
      });
    }

    final isPickup = cart.deliveryMode == DeliveryMode.pickup;

    return ColoredBox(
      color: AppColors.cream,
      child: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final contentWidth =
                constraints.maxWidth.clamp(0, AppTheme.maxContentWidth);
            return Align(
              alignment: Alignment.topCenter,
              child: SizedBox(
                width: contentWidth.toDouble(),
                height: constraints.maxHeight,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const _CheckoutHeader(),
                    Expanded(
                      child: AutofillGroup(
                        child: SingleChildScrollView(
                          padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Text(
                                'NOME COMPLETO',
                                style: Theme.of(context)
                                    .textTheme
                                    .labelSmall
                                    ?.copyWith(letterSpacing: 0.8),
                              ),
                              const SizedBox(height: 8),
                              TdTextField(
                                controller: _nameController,
                                hintText: 'Seu nome completo',
                                errorText: _nameError,
                                textInputAction: TextInputAction.next,
                                autofillHints: const [AutofillHints.name],
                                maxLength: CheckoutValidators.nameMaxLength,
                                inputFormatters: [
                                  FilteringTextInputFormatter.deny(
                                    RegExp(r'[\x00-\x1F\x7F]'),
                                  ),
                                ],
                                onChanged: _onFieldChanged,
                              ),
                              const SizedBox(height: 20),
                              Text(
                                'WHATSAPP',
                                style: Theme.of(context)
                                    .textTheme
                                    .labelSmall
                                    ?.copyWith(letterSpacing: 0.8),
                              ),
                              const SizedBox(height: 8),
                              TdTextField(
                                controller: _whatsappController,
                                hintText: '(11) 91234-5678',
                                errorText: _whatsappError,
                                keyboardType: TextInputType.phone,
                                textInputAction: TextInputAction.done,
                                autofillHints: const [
                                  AutofillHints.telephoneNumberNational,
                                ],
                                inputFormatters: [
                                  FilteringTextInputFormatter.digitsOnly,
                                  WhatsAppInputFormatter(),
                                ],
                                onChanged: _onFieldChanged,
                              ),
                              const SizedBox(height: 20),
                              Text(
                                isPickup ? 'RETIRADA' : 'ENTREGA',
                                style: Theme.of(context)
                                    .textTheme
                                    .labelSmall
                                    ?.copyWith(letterSpacing: 0.8),
                              ),
                              const SizedBox(height: 8),
                              _InfoCard(
                                child: Text(
                                  isPickup
                                      ? 'Hoje, entre 16h e 17h · Loja Tri Doçuras'
                                      : 'Receber em casa · ${cart.deliveryFeeLabel}',
                                  style: GoogleFonts.poppins(
                                    fontSize: 15,
                                    fontWeight: FontWeight.w400,
                                    color: AppColors.dark,
                                    height: 1.4,
                                  ),
                                ),
                              ),
                              const SizedBox(height: 20),
                              Text(
                                'PAGAMENTO',
                                style: Theme.of(context)
                                    .textTheme
                                    .labelSmall
                                    ?.copyWith(letterSpacing: 0.8),
                              ),
                              const SizedBox(height: 8),
                              const _PaymentPixCard(),
                              const SizedBox(height: 24),
                              _SummaryRow(
                                label: 'Subtotal',
                                value: cart.formattedSubtotal,
                              ),
                              const SizedBox(height: 12),
                              _SummaryRow(
                                label: 'Total a pagar',
                                value: cart.formattedTotal,
                                emphasized: true,
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                      child: TdButton(
                        label: 'Gerar Pix',
                        trailing: Text(cart.formattedTotal),
                        variant: _formValid && cart.items.isNotEmpty
                            ? TdButtonVariant.primary
                            : TdButtonVariant.disabled,
                        onPressed: _formValid && cart.items.isNotEmpty
                            ? _generatePix
                            : null,
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _CheckoutHeader extends StatelessWidget {
  const _CheckoutHeader();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 4),
      child: Row(
        children: [
          TdIconButton(
            icon: Icons.arrow_back,
            onPressed: () => Navigator.of(context).pop(),
            tint: AppColors.peach,
          ),
          Expanded(
            child: Text(
              'Finalizar',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineSmall,
            ),
          ),
          const SizedBox(width: 48),
        ],
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.brown.withValues(alpha: 0.12)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: child,
      ),
    );
  }
}

class _PaymentPixCard extends StatelessWidget {
  const _PaymentPixCard();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.brown.withValues(alpha: 0.12)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 28,
              height: 28,
              decoration: const BoxDecoration(
                color: AppColors.success,
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.check, size: 16, color: AppColors.white),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Pix',
                    style: GoogleFonts.poppins(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: AppColors.dark,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Pix via Mercado Pago',
                    style: GoogleFonts.poppins(
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: AppColors.brown,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Aprovação automática e instantânea',
                    style: GoogleFonts.poppins(
                      fontSize: 13,
                      fontWeight: FontWeight.w400,
                      color: AppColors.brown.withValues(alpha: 0.85),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow({
    required this.label,
    required this.value,
    this.emphasized = false,
  });

  final String label;
  final String value;
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    final style = emphasized
        ? GoogleFonts.poppins(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            color: AppColors.dark,
          )
        : GoogleFonts.poppins(
            fontSize: 14,
            fontWeight: FontWeight.w400,
            color: AppColors.brown,
          );
    return Row(
      children: [
        Text(label, style: style),
        const Spacer(),
        Text(value, style: style),
      ],
    );
  }
}
