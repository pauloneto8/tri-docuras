import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/checkout/delivery_address.dart';
import 'package:tri_docuras/checkout/order_summary.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/theme/app_theme.dart';
import 'package:tri_docuras/widgets/td_button.dart';

/// Confirmação do pedido (tela 6) — após pagamento Pix confirmado.
class ConfirmationScreen extends StatelessWidget {
  const ConfirmationScreen({super.key, required this.summary});

  final OrderSummary summary;

  @override
  Widget build(BuildContext context) {
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
                    Expanded(
                      child: SingleChildScrollView(
                        padding: const EdgeInsets.fromLTRB(24, 32, 24, 16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const Center(
                              child: Icon(
                                Icons.favorite,
                                size: 48,
                                color: AppColors.pink,
                              ),
                            ),
                            const SizedBox(height: 16),
                            Text(
                              'Pedido confirmado!',
                              textAlign: TextAlign.center,
                              style: Theme.of(context).textTheme.headlineSmall,
                            ),
                            const SizedBox(height: 12),
                            Text(
                              'Recebemos seu pagamento via Pix.\n'
                              'Seu brownie já entrou na fila de preparo.',
                              textAlign: TextAlign.center,
                              style: Theme.of(context).textTheme.bodyMedium,
                            ),
                            const SizedBox(height: 28),
                            DecoratedBox(
                              decoration: BoxDecoration(
                                color: AppColors.card,
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(
                                  color: AppColors.brown.withValues(alpha: 0.12),
                                ),
                              ),
                              child: Padding(
                                padding: const EdgeInsets.all(16),
                                child: Column(
                                  children: [
                                    _DetailRow(
                                      label: 'Pedido',
                                      value: '#${summary.orderId}',
                                    ),
                                    const SizedBox(height: 12),
                                    _DetailRow(
                                      label: summary.deliveryLabel,
                                      value: summary.deliveryDetail,
                                    ),
                                    if (summary.deliveryAddress != null) ...[
                                      const SizedBox(height: 8),
                                      Text(
                                        'Ref.: ${summary.deliveryAddress!.reference}',
                                        style: GoogleFonts.poppins(
                                          fontSize: 13,
                                          fontWeight: FontWeight.w400,
                                          color: AppColors.brown,
                                        ),
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        '${DeliveryAddress.cityLabel} · CEP ${DeliveryAddress.postalCodeLabel}',
                                        style: GoogleFonts.poppins(
                                          fontSize: 13,
                                          fontWeight: FontWeight.w400,
                                          color: AppColors.brown.withValues(alpha: 0.85),
                                        ),
                                      ),
                                    ],
                                    const SizedBox(height: 12),
                                    _DetailRow(
                                      label: 'Total pago',
                                      value: summary.formattedTotal,
                                      emphasized: true,
                                    ),
                                    const SizedBox(height: 16),
                                    Row(
                                      children: [
                                        Text(
                                          'Status',
                                          style: GoogleFonts.poppins(
                                            fontSize: 14,
                                            fontWeight: FontWeight.w400,
                                            color: AppColors.brown,
                                          ),
                                        ),
                                        const Spacer(),
                                        _StatusPaidBadge(),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                      child: TdButton(
                        label: 'Acompanhar pedido',
                        onPressed: () {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text(
                                'Rastreamento de pedidos em breve.',
                                style: GoogleFonts.poppins(fontSize: 13),
                              ),
                              behavior: SnackBarBehavior.floating,
                              backgroundColor: AppColors.dark,
                            ),
                          );
                        },
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                      child: TdButton(
                        label: 'Voltar à loja',
                        variant: TdButtonVariant.outline,
                        onPressed: () {
                          Navigator.of(context).popUntil((route) => route.isFirst);
                        },
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

class _DetailRow extends StatelessWidget {
  const _DetailRow({
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

class _StatusPaidBadge extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.success.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        child: Text(
          'Pago',
          style: GoogleFonts.poppins(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: AppColors.success,
          ),
        ),
      ),
    );
  }
}
