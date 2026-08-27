import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/cart/cart_item.dart';
import 'package:tri_docuras/cart/cart_scope.dart';
import 'package:tri_docuras/cart/delivery_mode.dart';
import 'package:tri_docuras/screens/checkout_screen.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/theme/app_theme.dart';
import 'package:tri_docuras/widgets/td_button.dart';
import 'package:tri_docuras/widgets/td_icon_button.dart';
import 'package:tri_docuras/widgets/td_photo_frame.dart';
import 'package:tri_docuras/widgets/td_quantity_stepper.dart';

class CartScreen extends StatelessWidget {
  const CartScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final cart = CartScope.of(context);

    return ColoredBox(
      color: AppColors.cream,
      child: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final contentWidth = constraints.maxWidth.clamp(0, AppTheme.maxContentWidth);
            return Align(
              alignment: Alignment.topCenter,
              child: SizedBox(
                width: contentWidth.toDouble(),
                height: constraints.maxHeight,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _CartHeader(onBack: () => Navigator.of(context).pop()),
                    if (cart.items.isEmpty)
                      Expanded(
                        child: Center(
                          child: Padding(
                            padding: const EdgeInsets.all(32),
                            child: Text(
                              'Seu carrinho está vazio',
                              style: Theme.of(context).textTheme.bodyMedium,
                              textAlign: TextAlign.center,
                            ),
                          ),
                        ),
                      )
                    else
                      Expanded(
                        child: SingleChildScrollView(
                          padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              ...List.generate(cart.items.length, (index) {
                                final item = cart.items[index];
                                return Padding(
                                  padding: const EdgeInsets.only(bottom: 16),
                                  child: _CartLineCard(
                                    item: item,
                                    onQuantityChanged: (qty) =>
                                        cart.updateQuantity(index, qty),
                                  ),
                                );
                              }),
                              const SizedBox(height: 8),
                              Text(
                                'ENTREGA',
                                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                      letterSpacing: 0.8,
                                    ),
                              ),
                              const SizedBox(height: 10),
                              Row(
                                children: [
                                  Expanded(
                                    child: _DeliveryOption(
                                      label: 'Retirar na loja',
                                      selected: cart.deliveryMode == DeliveryMode.pickup,
                                      onTap: () =>
                                          cart.setDeliveryMode(DeliveryMode.pickup),
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: _DeliveryOption(
                                      label: 'Receber em casa',
                                      selected: cart.deliveryMode == DeliveryMode.delivery,
                                      onTap: () =>
                                          cart.setDeliveryMode(DeliveryMode.delivery),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 24),
                              _SummaryRow(
                                label: 'Subtotal',
                                value: cart.formattedSubtotal,
                              ),
                              const SizedBox(height: 8),
                              _SummaryRow(
                                label: cart.deliveryMode == DeliveryMode.pickup
                                    ? 'Retirada'
                                    : 'Entrega',
                                value: cart.deliveryFeeLabel,
                              ),
                              const SizedBox(height: 12),
                              _SummaryRow(
                                label: 'Total',
                                value: cart.formattedTotal,
                                emphasized: true,
                              ),
                            ],
                          ),
                        ),
                      ),
                    if (cart.items.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                        child: TdButton(
                          label: 'Finalizar pedido',
                          trailing: Text(cart.formattedTotal),
                          onPressed: () {
                            Navigator.of(context).push(
                              MaterialPageRoute<void>(
                                builder: (_) => const CheckoutScreen(),
                              ),
                            );
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

class _CartHeader extends StatelessWidget {
  const _CartHeader({required this.onBack});

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
              'Seu carrinho',
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

class _CartLineCard extends StatelessWidget {
  const _CartLineCard({
    required this.item,
    required this.onQuantityChanged,
  });

  final CartItem item;
  final ValueChanged<int> onQuantityChanged;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: AppColors.dark.withValues(alpha: 0.05),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            SizedBox(
              width: 64,
              height: 64,
              child: TdPhotoFrame(),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.product.name,
                    style: Theme.of(context).textTheme.titleMedium,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    item.formattedUnitPrice,
                    style: Theme.of(context).textTheme.bodyLarge,
                  ),
                ],
              ),
            ),
            TdQuantityStepper(
              value: item.quantity,
              compact: true,
              onChanged: onQuantityChanged,
            ),
          ],
        ),
      ),
    );
  }
}

class _DeliveryOption extends StatelessWidget {
  const _DeliveryOption({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? AppColors.dark : AppColors.peach,
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: GoogleFonts.poppins(
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: selected ? AppColors.white : AppColors.dark,
            ),
          ),
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
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: AppColors.dark,
          )
        : Theme.of(context).textTheme.bodyMedium;

    return Row(
      children: [
        Text(label, style: style),
        const Spacer(),
        Text(value, style: style),
      ],
    );
  }
}
