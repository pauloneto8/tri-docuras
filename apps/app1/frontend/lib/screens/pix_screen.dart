import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/cart/cart_scope.dart';
import 'package:tri_docuras/checkout/checkout_draft.dart';
import 'package:tri_docuras/checkout/order_summary.dart';
import 'package:tri_docuras/screens/confirmation_screen.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/theme/app_theme.dart';
import 'package:tri_docuras/widgets/td_button.dart';
import 'package:tri_docuras/widgets/td_icon_button.dart';

/// Pagamento Pix (tela 5) — UI fiel ao PDF; QR/código reais virão da API Mercado Pago.
class PixScreen extends StatefulWidget {
  const PixScreen({super.key, required this.draft});

  final CheckoutDraft draft;

  @override
  State<PixScreen> createState() => _PixScreenState();
}

class _PixScreenState extends State<PixScreen> {
  static const _expiryDuration = Duration(minutes: 10);
  static const _previewPixCode = '00020126580014BR.GOV.BCB.PIX0…';

  late final String _orderId;
  late DateTime _expiresAt;
  Duration _remaining = _expiryDuration;
  bool _expired = false;

  @override
  void initState() {
    super.initState();
    _orderId = OrderSummary.generateOrderId();
    _expiresAt = DateTime.now().add(_expiryDuration);
    _tickTimer();
  }

  void _tickTimer() {
    final left = _expiresAt.difference(DateTime.now());
    if (left.isNegative || left.inSeconds <= 0) {
      setState(() {
        _remaining = Duration.zero;
        _expired = true;
      });
      return;
    }
    setState(() {
      _remaining = left;
      _expired = false;
    });
    Future.delayed(const Duration(seconds: 1), () {
      if (mounted) _tickTimer();
    });
  }

  String get _timerLabel {
    final m = _remaining.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = _remaining.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  void _onCopyPressed() {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'O código Pix será gerado pela API Mercado Pago (integração em breve).',
          style: GoogleFonts.poppins(fontSize: 13),
        ),
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.dark,
      ),
    );
  }

  void _onPaymentConfirmed() {
    if (_expired) return;
    final summary = widget.draft.toOrderSummary(_orderId);
    CartScope.of(context).clear();
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(
        builder: (_) => ConfirmationScreen(summary: summary),
      ),
    );
  }

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
                    _PixHeader(onBack: () => Navigator.of(context).pop()),
                    Expanded(
                      child: SingleChildScrollView(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Text(
                              'Escaneie o QR Code no app do seu banco',
                              textAlign: TextAlign.center,
                              style: GoogleFonts.poppins(
                                fontSize: 15,
                                fontWeight: FontWeight.w400,
                                color: AppColors.brown,
                              ),
                            ),
                            const SizedBox(height: 16),
                            Center(child: _QrPlaceholder(expired: _expired)),
                            const SizedBox(height: 20),
                            Text(
                              widget.draft.formattedTotal,
                              textAlign: TextAlign.center,
                              style: Theme.of(context).textTheme.displayLarge?.copyWith(
                                    fontSize: 36,
                                    fontStyle: FontStyle.normal,
                                    fontWeight: FontWeight.w600,
                                  ),
                            ),
                            const SizedBox(height: 8),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(
                                  Icons.timer_outlined,
                                  size: 18,
                                  color: _expired ? AppColors.brown : AppColors.warning,
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  _expired
                                      ? 'Código expirado'
                                      : 'Expira em $_timerLabel',
                                  style: GoogleFonts.poppins(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w600,
                                    color: _expired ? AppColors.brown : AppColors.warning,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 24),
                            Text(
                              'OU COPIE O CÓDIGO PIX',
                              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                    letterSpacing: 0.8,
                                  ),
                            ),
                            const SizedBox(height: 8),
                            DecoratedBox(
                              decoration: BoxDecoration(
                                color: AppColors.card,
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(
                                  color: AppColors.brown.withValues(alpha: 0.12),
                                ),
                              ),
                              child: Padding(
                                padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        _previewPixCode,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: GoogleFonts.poppins(
                                          fontSize: 14,
                                          fontWeight: FontWeight.w500,
                                          color: AppColors.dark,
                                        ),
                                      ),
                                    ),
                                    TdButton(
                                      label: 'COPIAR',
                                      expand: false,
                                      variant: _expired
                                          ? TdButtonVariant.disabled
                                          : TdButtonVariant.outline,
                                      onPressed: _expired ? null : _onCopyPressed,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                            const SizedBox(height: 20),
                            Center(
                              child: _StatusBadge(
                                label: _expired
                                    ? 'Pagamento expirado'
                                    : 'Aguardando pagamento',
                                warning: !_expired,
                              ),
                            ),
                            const SizedBox(height: 24),
                            _StepLine(
                              number: 1,
                              text: 'Abra o app do seu banco',
                            ),
                            const SizedBox(height: 10),
                            _StepLine(
                              number: 2,
                              text: 'Escaneie o QR ou cole o código',
                            ),
                            const SizedBox(height: 10),
                            _StepLine(
                              number: 3,
                              text: 'Confirme — a confirmação é automática',
                            ),
                            const SizedBox(height: 24),
                            Text(
                              'Pagamento processado com segurança pelo Mercado Pago',
                              textAlign: TextAlign.center,
                              style: GoogleFonts.poppins(
                                fontSize: 12,
                                fontWeight: FontWeight.w400,
                                color: AppColors.brown.withValues(alpha: 0.85),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    if (!_expired)
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                        child: TdButton(
                          label: 'Já realizei o pagamento',
                          variant: TdButtonVariant.soft,
                          onPressed: _onPaymentConfirmed,
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

class _PixHeader extends StatelessWidget {
  const _PixHeader({required this.onBack});

  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 4),
      child: Row(
        children: [
          TdIconButton(
            icon: Icons.arrow_back,
            onPressed: onBack,
            tint: AppColors.peach,
          ),
          Expanded(
            child: Text(
              'Pagar com Pix',
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

class _QrPlaceholder extends StatelessWidget {
  const _QrPlaceholder({required this.expired});

  final bool expired;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.brown.withValues(alpha: 0.15)),
        boxShadow: [
          BoxShadow(
            color: AppColors.dark.withValues(alpha: 0.06),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: SizedBox(
        width: 220,
        height: 220,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              expired ? Icons.qr_code_2 : Icons.qr_code_scanner,
              size: 120,
              color: expired
                  ? AppColors.disabled
                  : AppColors.brown.withValues(alpha: 0.35),
            ),
            if (!expired) ...[
              const SizedBox(height: 8),
              Text(
                'QR Code',
                style: GoogleFonts.poppins(
                  fontSize: 12,
                  color: AppColors.brown.withValues(alpha: 0.6),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.label, required this.warning});

  final String label;
  final bool warning;

  @override
  Widget build(BuildContext context) {
    final bg = warning ? AppColors.warning.withValues(alpha: 0.18) : AppColors.disabled;
    final fg = warning ? AppColors.warning : AppColors.brown;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Text(
          label,
          style: GoogleFonts.poppins(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: fg,
          ),
        ),
      ),
    );
  }
}

class _StepLine extends StatelessWidget {
  const _StepLine({required this.number, required this.text});

  final int number;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 24,
          height: 24,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: AppColors.peach,
            borderRadius: BorderRadius.circular(999),
          ),
          child: Text(
            '$number',
            style: GoogleFonts.poppins(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: AppColors.dark,
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            text,
            style: GoogleFonts.poppins(
              fontSize: 14,
              fontWeight: FontWeight.w400,
              color: AppColors.brown,
              height: 1.4,
            ),
          ),
        ),
      ],
    );
  }
}
