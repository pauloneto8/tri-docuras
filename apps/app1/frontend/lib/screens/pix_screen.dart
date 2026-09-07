import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:tri_docuras/cart/cart_scope.dart';
import 'package:tri_docuras/checkout/checkout_draft.dart';
import 'package:tri_docuras/models/created_order.dart';
import 'package:tri_docuras/screens/confirmation_screen.dart';
import 'package:tri_docuras/services/api_service.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/theme/app_theme.dart';
import 'package:tri_docuras/widgets/td_button.dart';
import 'package:tri_docuras/widgets/td_icon_button.dart';

/// Pagamento Pix (tela 5) — QR e copia-e-cola via Mercado Pago.
class PixScreen extends StatefulWidget {
  const PixScreen({
    super.key,
    required this.draft,
    required this.order,
    this.api,
  });

  final CheckoutDraft draft;
  final CreatedOrder order;
  final ApiService? api;

  @override
  State<PixScreen> createState() => _PixScreenState();
}

class _PixScreenState extends State<PixScreen> {
  late final ApiService _api;
  PixPayment? _pix;
  String? _pixError;
  bool _isTestMode = false;
  bool _loadingPix = false;
  Timer? _pollTimer;
  Timer? _tickTimer;
  Duration _remaining = Duration.zero;
  bool _expired = false;

  @override
  void initState() {
    super.initState();
    _api = widget.api ?? ApiService();
    _pix = widget.order.pix;
    _pixError = widget.order.pixError;
    _isTestMode = widget.order.pix?.isTestMode ?? false;
    _syncExpiryFromPix();
    _startPolling();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _tickTimer?.cancel();
    super.dispose();
  }

  void _syncExpiryFromPix() {
    if (_pix != null) {
      _updateRemaining(_pix!.expiresAt.difference(DateTime.now()));
      _startCountdown();
    }
  }

  void _startCountdown() {
    _tickTimer?.cancel();
    _tickTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_pix == null) return;
      _updateRemaining(_pix!.expiresAt.difference(DateTime.now()));
    });
  }

  void _updateRemaining(Duration left) {
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
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(seconds: 3), (_) => _checkPayment());
    _checkPayment();
  }

  Future<void> _checkPayment() async {
    try {
      final status = await _api.fetchOrderStatus(widget.order.id);
      if (!mounted) return;
      if (status.isPaid) {
        _pollTimer?.cancel();
        _goToConfirmation();
      }
    } catch (_) {
      // Mantém polling; falha de rede é temporária.
    }
  }

  Future<void> _retryPix() async {
    setState(() {
      _loadingPix = true;
      _pixError = null;
    });
    try {
      final pix = await _api.createPix(widget.order.id);
      if (!mounted) return;
      setState(() {
        _pix = pix;
        _isTestMode = pix.isTestMode;
        _loadingPix = false;
      });
      _syncExpiryFromPix();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _pixError = error.message;
        _loadingPix = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _pixError = 'Não foi possível gerar o Pix.';
        _loadingPix = false;
      });
    }
  }

  void _goToConfirmation() {
    final summary = widget.draft.toOrderSummary(widget.order.id);
    CartScope.of(context).clear();
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(
        builder: (_) => ConfirmationScreen(summary: summary),
      ),
    );
  }

  String get _timerLabel {
    final m = _remaining.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = _remaining.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  void _onCopyPressed() {
    final code = _pix?.copyCode;
    if (code == null || code.isEmpty) return;
    Clipboard.setData(ClipboardData(text: code));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Código Pix copiado.',
          style: GoogleFonts.poppins(fontSize: 13),
        ),
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.dark,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final pixCodePreview = _pix?.copyCode ?? '';
    final showPix = _pix != null && pixCodePreview.isNotEmpty;

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
                              'Pedido ${widget.order.id}',
                              textAlign: TextAlign.center,
                              style: GoogleFonts.poppins(
                                fontSize: 13,
                                fontWeight: FontWeight.w500,
                                color: AppColors.brown,
                              ),
                            ),
                            const SizedBox(height: 8),
                            if (_isTestMode) ...[
                              _TestModeBanner(),
                              const SizedBox(height: 12),
                            ],
                            if (_pixError != null) ...[
                              _ErrorBanner(message: _pixError!),
                              const SizedBox(height: 12),
                              TdButton(
                                label: _loadingPix ? 'Gerando Pix…' : 'Tentar novamente',
                                variant: _loadingPix
                                    ? TdButtonVariant.disabled
                                    : TdButtonVariant.primary,
                                onPressed: _loadingPix ? null : _retryPix,
                              ),
                              const SizedBox(height: 16),
                            ],
                            if (showPix) ...[
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
                              Center(child: _QrImage(pix: _pix!, expired: _expired)),
                              const SizedBox(height: 20),
                              Text(
                                widget.draft.formattedTotal,
                                textAlign: TextAlign.center,
                                style: Theme.of(context)
                                    .textTheme
                                    .displayLarge
                                    ?.copyWith(
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
                                    color: _expired
                                        ? AppColors.brown
                                        : AppColors.warning,
                                  ),
                                  const SizedBox(width: 6),
                                  Text(
                                    _expired
                                        ? 'Código expirado'
                                        : 'Expira em $_timerLabel',
                                    style: GoogleFonts.poppins(
                                      fontSize: 14,
                                      fontWeight: FontWeight.w600,
                                      color: _expired
                                          ? AppColors.brown
                                          : AppColors.warning,
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 24),
                              Text(
                                'OU COPIE O CÓDIGO PIX',
                                style: Theme.of(context)
                                    .textTheme
                                    .labelSmall
                                    ?.copyWith(letterSpacing: 0.8),
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
                                          pixCodePreview,
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
                            ] else if (_pixError == null && _loadingPix) ...[
                              const SizedBox(height: 48),
                              const Center(child: CircularProgressIndicator()),
                              const SizedBox(height: 16),
                              Text(
                                'Gerando Pix…',
                                textAlign: TextAlign.center,
                                style: GoogleFonts.poppins(color: AppColors.brown),
                              ),
                            ],
                            const SizedBox(height: 24),
                            const _StepLine(number: 1, text: 'Abra o app do seu banco'),
                            const SizedBox(height: 10),
                            const _StepLine(
                              number: 2,
                              text: 'Escaneie o QR ou cole o código',
                            ),
                            const SizedBox(height: 10),
                            const _StepLine(
                              number: 3,
                              text: 'A confirmação é automática após o pagamento',
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
                    if (showPix && !_expired)
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                        child: TdButton(
                          label: 'Já realizei o pagamento',
                          variant: TdButtonVariant.soft,
                          onPressed: _checkPayment,
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
          TdIconButton(icon: Icons.arrow_back, onPressed: onBack, tint: AppColors.peach),
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

class _QrImage extends StatelessWidget {
  const _QrImage({required this.pix, required this.expired});

  final PixPayment pix;
  final bool expired;

  @override
  Widget build(BuildContext context) {
    final code = pix.copyCode.trim();
    Widget child;

    if (code.isNotEmpty && !expired) {
      child = QrImageView(
        data: code,
        size: 200,
        backgroundColor: AppColors.white,
        eyeStyle: const QrEyeStyle(
          eyeShape: QrEyeShape.square,
          color: AppColors.dark,
        ),
        dataModuleStyle: const QrDataModuleStyle(
          dataModuleShape: QrDataModuleShape.square,
          color: AppColors.dark,
        ),
      );
    } else if (pix.hasQrImage && !expired) {
      try {
        final bytes = base64Decode(pix.qrCodeBase64);
        child = Image.memory(bytes, width: 200, height: 200, fit: BoxFit.contain);
      } catch (_) {
        child = _QrPlaceholder(expired: expired);
      }
    } else {
      child = _QrPlaceholder(expired: expired);
    }

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
        child: Center(
          child: Opacity(opacity: expired ? 0.45 : 1, child: child),
        ),
      ),
    );
  }
}

class _TestModeBanner extends StatelessWidget {
  const _TestModeBanner();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.warning.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.warning.withValues(alpha: 0.35)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Text(
          'Modo teste do Mercado Pago: este Pix não pode ser pago em apps bancários reais. '
          'Para pagar de verdade, use credenciais de produção.',
          textAlign: TextAlign.center,
          style: GoogleFonts.poppins(
            fontSize: 12,
            fontWeight: FontWeight.w500,
            color: AppColors.brown,
            height: 1.4,
          ),
        ),
      ),
    );
  }
}

class _QrPlaceholder extends StatelessWidget {
  const _QrPlaceholder({required this.expired});

  final bool expired;

  @override
  Widget build(BuildContext context) {
    return Column(
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
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.warning.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Text(
          message,
          textAlign: TextAlign.center,
          style: GoogleFonts.poppins(
            fontSize: 13,
            fontWeight: FontWeight.w500,
            color: AppColors.brown,
          ),
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
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
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
