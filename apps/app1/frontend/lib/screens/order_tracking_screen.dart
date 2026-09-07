import 'dart:async';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/models/order_tracking.dart';
import 'package:tri_docuras/services/api_service.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/theme/app_theme.dart';
import 'package:tri_docuras/widgets/td_button.dart';
import 'package:tri_docuras/widgets/td_icon_button.dart';
import 'package:tri_docuras/widgets/td_text_field.dart';

/// Acompanhamento do pedido — timeline com polling.
class OrderTrackingScreen extends StatefulWidget {
  const OrderTrackingScreen({
    super.key,
    required this.orderId,
    this.api,
    this.showBack = true,
  });

  final String orderId;
  final ApiService? api;
  final bool showBack;

  @override
  State<OrderTrackingScreen> createState() => _OrderTrackingScreenState();
}

class _OrderTrackingScreenState extends State<OrderTrackingScreen> {
  late final ApiService _api;
  OrderTracking? _tracking;
  String? _error;
  bool _loading = true;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _api = widget.api ?? ApiService();
    _loadTracking();
    _pollTimer = Timer.periodic(const Duration(seconds: 15), (_) => _loadTracking());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadTracking() async {
    try {
      final tracking = await _api.fetchOrderTracking(widget.orderId);
      if (!mounted) return;
      setState(() {
        _tracking = tracking;
        _error = null;
        _loading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = 'Não foi possível carregar o pedido.';
        _loading = false;
      });
    }
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
                    _TrackingHeader(
                      showBack: widget.showBack,
                      onBack: () => Navigator.of(context).pop(),
                    ),
                    Expanded(
                      child: SingleChildScrollView(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                        child: _buildBody(context),
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

  Widget _buildBody(BuildContext context) {
    if (_loading && _tracking == null) {
      return const Padding(
        padding: EdgeInsets.only(top: 48),
        child: Center(child: CircularProgressIndicator(color: AppColors.pinkDeep)),
      );
    }

    if (_error != null && _tracking == null) {
      return Column(
        children: [
          const SizedBox(height: 32),
          Text(
            _error!,
            textAlign: TextAlign.center,
            style: GoogleFonts.poppins(color: AppColors.brown),
          ),
          const SizedBox(height: 16),
          TdButton(label: 'Tentar novamente', onPressed: _loadTracking),
        ],
      );
    }

    final tracking = _tracking!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Pedido ${tracking.id}',
          textAlign: TextAlign.center,
          style: GoogleFonts.poppins(
            fontSize: 13,
            fontWeight: FontWeight.w500,
            color: AppColors.brown,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          tracking.statusLabel,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 6),
        Text(
          '${tracking.deliveryLabel} · ${tracking.formattedTotal}',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 24),
        DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.card,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.brown.withValues(alpha: 0.12)),
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                for (var i = 0; i < tracking.timeline.length; i++)
                  _TimelineStep(
                    step: tracking.timeline[i],
                    isLast: i == tracking.timeline.length - 1,
                  ),
              ],
            ),
          ),
        ),
        if (tracking.isCompleted) ...[
          const SizedBox(height: 20),
          Text(
            'Pedido concluído. Obrigado pela preferência!',
            textAlign: TextAlign.center,
            style: GoogleFonts.poppins(
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: AppColors.success,
            ),
          ),
        ],
        const SizedBox(height: 20),
        TdButton(
          label: 'Atualizar status',
          variant: TdButtonVariant.soft,
          onPressed: _loadTracking,
        ),
      ],
    );
  }
}

class OrderLookupScreen extends StatefulWidget {
  const OrderLookupScreen({super.key, this.api});

  final ApiService? api;

  @override
  State<OrderLookupScreen> createState() => _OrderLookupScreenState();
}

class _OrderLookupScreenState extends State<OrderLookupScreen> {
  final _controller = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _openTracking() {
    final id = _controller.text.trim().toUpperCase();
    if (!RegExp(r'^TD-\d{4}$').hasMatch(id)) {
      setState(() => _error = 'Informe o número do pedido (ex.: TD-0009).');
      return;
    }
    setState(() => _error = null);
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => OrderTrackingScreen(
          orderId: id,
          api: widget.api,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppColors.cream,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Acompanhar pedido',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 8),
              Text(
                'Digite o número do pedido que você recebeu após o pagamento.',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 20),
              Text(
                'NÚMERO DO PEDIDO',
                style: Theme.of(context).textTheme.labelSmall,
              ),
              const SizedBox(height: 8),
              TdTextField(
                controller: _controller,
                hintText: 'TD-0001',
                errorText: _error,
                textInputAction: TextInputAction.done,
              ),
              const SizedBox(height: 20),
              TdButton(label: 'Consultar', onPressed: _openTracking),
            ],
          ),
        ),
      ),
    );
  }
}

class _TrackingHeader extends StatelessWidget {
  const _TrackingHeader({required this.showBack, required this.onBack});

  final bool showBack;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 4),
      child: Row(
        children: [
          if (showBack)
            TdIconButton(icon: Icons.arrow_back, onPressed: onBack, tint: AppColors.peach)
          else
            const SizedBox(width: 48),
          Expanded(
            child: Text(
              'Acompanhar pedido',
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

class _TimelineStep extends StatelessWidget {
  const _TimelineStep({required this.step, required this.isLast});

  final TrackingStep step;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    final color = step.done
        ? (step.current ? AppColors.pinkDeep : AppColors.success)
        : AppColors.disabled;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Column(
          children: [
            Container(
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                color: step.done ? color : AppColors.card,
                shape: BoxShape.circle,
                border: Border.all(color: color, width: 2),
              ),
              child: step.done
                  ? Icon(
                      step.current ? Icons.circle : Icons.check,
                      size: step.current ? 10 : 14,
                      color: step.current ? AppColors.white : AppColors.white,
                    )
                  : null,
            ),
            if (!isLast)
              Container(
                width: 2,
                height: 28,
                color: step.done && !step.current
                    ? AppColors.success.withValues(alpha: 0.5)
                    : AppColors.disabled,
              ),
          ],
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Padding(
            padding: EdgeInsets.only(bottom: isLast ? 0 : 18),
            child: Text(
              step.label,
              style: GoogleFonts.poppins(
                fontSize: 14,
                fontWeight: step.current ? FontWeight.w600 : FontWeight.w400,
                color: step.done ? AppColors.dark : AppColors.brown,
              ),
            ),
          ),
        ),
      ],
    );
  }
}
