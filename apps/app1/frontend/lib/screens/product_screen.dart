import 'package:flutter/material.dart';
import 'package:tri_docuras/cart/cart_item.dart';
import 'package:tri_docuras/cart/cart_scope.dart';
import 'package:tri_docuras/models/product.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/theme/app_theme.dart';
import 'package:tri_docuras/widgets/td_button.dart';
import 'package:tri_docuras/widgets/td_chip.dart';
import 'package:tri_docuras/widgets/td_icon_button.dart';
import 'package:tri_docuras/widgets/td_photo_frame.dart';
import 'package:tri_docuras/widgets/td_quantity_stepper.dart';

class ProductScreen extends StatefulWidget {
  const ProductScreen({super.key, required this.product});

  final Product product;

  @override
  State<ProductScreen> createState() => _ProductScreenState();
}

class _ProductScreenState extends State<ProductScreen> {
  static const _sizeOptions = ['9x9cm', 'Fatia grande'];
  static const _lactoseExtra = 3.0;

  late int _quantity;
  late String _size;
  late bool _lactoseFree;
  late bool _favorited;

  bool get _isCombo => widget.product.category == 'combos';

  @override
  void initState() {
    super.initState();
    _quantity = 2;
    _size = _sizeOptions.first;
    _lactoseFree = false;
    _favorited = widget.product.featured;
  }

  double get _unitPrice => widget.product.price + (_lactoseFree ? _lactoseExtra : 0);

  double get _totalPrice => _unitPrice * _quantity;

  String _formatPrice(double value) =>
      'R\$ ${value.toStringAsFixed(2).replaceAll('.', ',')}';

  void _addToCart() {
    CartScope.of(context).add(
      CartItem(
        product: widget.product,
        quantity: _quantity,
        size: _isCombo ? null : _size,
        lactoseFree: _isCombo ? false : _lactoseFree,
      ),
    );
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
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
                    _ProductHeader(
                      favorited: _favorited,
                      onBack: () => Navigator.of(context).pop(),
                      onFavorite: () => setState(() => _favorited = !_favorited),
                    ),
                    Expanded(
                      child: SingleChildScrollView(
                        padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 24),
                              child: SizedBox(
                                height: 220,
                                child: TdPhotoFrame(),
                              ),
                            ),
                            const SizedBox(height: 20),
                            Text(
                              widget.product.name,
                              style: Theme.of(context).textTheme.headlineSmall,
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: 6),
                            Text(
                              '${_formatPrice(widget.product.price)} / unidade',
                              style: Theme.of(context).textTheme.bodyLarge,
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: 12),
                            Text(
                              widget.product.description,
                              style: Theme.of(context).textTheme.bodyMedium,
                              textAlign: TextAlign.center,
                            ),
                            if (!_isCombo) ...[
                              const SizedBox(height: 20),
                              Wrap(
                                alignment: WrapAlignment.center,
                                spacing: 0,
                                runSpacing: 8,
                                children: _sizeOptions
                                    .map(
                                      (option) => TdChip(
                                        label: option,
                                        selected: _size == option,
                                        onTap: () => setState(() => _size = option),
                                      ),
                                    )
                                    .toList(),
                              ),
                              const SizedBox(height: 8),
                              Center(
                                child: TdChip(
                                  label: 'Sem lactose +R\$3',
                                  selected: _lactoseFree,
                                  onTap: () => setState(() => _lactoseFree = !_lactoseFree),
                                ),
                              ),
                            ],
                            const SizedBox(height: 24),
                            TdQuantityStepper(
                              value: _quantity,
                              onChanged: (value) => setState(() => _quantity = value),
                            ),
                          ],
                        ),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                      child: TdButton(
                        label: 'Adicionar',
                        onPressed: widget.product.available ? _addToCart : null,
                        variant: widget.product.available
                            ? TdButtonVariant.primary
                            : TdButtonVariant.disabled,
                        trailing: Text(_formatPrice(_totalPrice)),
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

class _ProductHeader extends StatelessWidget {
  const _ProductHeader({
    required this.favorited,
    required this.onBack,
    required this.onFavorite,
  });

  final bool favorited;
  final VoidCallback onBack;
  final VoidCallback onFavorite;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          TdIconButton(
            icon: Icons.arrow_back,
            onPressed: onBack,
            tint: AppColors.peach,
          ),
          TdIconButton(
            icon: favorited ? Icons.favorite : Icons.favorite_border,
            onPressed: onFavorite,
            tint: AppColors.peach,
            iconColor: favorited ? AppColors.pinkDeep : AppColors.dark,
          ),
        ],
      ),
    );
  }
}
