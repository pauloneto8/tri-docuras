import 'package:flutter/material.dart';
import 'package:tri_docuras/cart/cart_added_result.dart';
import 'package:tri_docuras/cart/cart_item.dart';
import 'package:tri_docuras/cart/cart_scope.dart';
import 'package:tri_docuras/favorites/favorites_scope.dart';
import 'package:tri_docuras/models/product.dart';
import 'package:tri_docuras/models/product_option.dart';
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
  late int _quantity;
  int? _sizeId;
  final Set<int> _addonIds = {};
  late bool _favorited;

  /// Opções marcadas, na ordem do cadastro do produto.
  List<ProductOption> get _selectedOptions => [
        for (final option in widget.product.options)
          if (option.id == _sizeId || _addonIds.contains(option.id)) option,
      ];

  @override
  void initState() {
    super.initState();
    _quantity = 2;
    final sizes = widget.product.sizeOptions;
    _sizeId = sizes.isEmpty ? null : sizes.first.id;
    final favorites = FavoritesScope.of(context);
    _favorited = favorites.isFavorite(widget.product.id);
    favorites.load().then((_) {
      if (!mounted) return;
      setState(() {
        _favorited = favorites.isFavorite(widget.product.id);
      });
    });
  }

  double get _unitPrice => widget.product.price +
      _selectedOptions.fold<double>(0, (sum, option) => sum + option.priceDelta);

  double get _totalPrice => _unitPrice * _quantity;

  String _formatPrice(double value) =>
      'R\$ ${value.toStringAsFixed(2).replaceAll('.', ',')}';

  void _addToCart() {
    CartScope.of(context).add(
      CartItem(
        product: widget.product,
        quantity: _quantity,
        options: _selectedOptions,
      ),
    );
    Navigator.of(context).pop(
      CartAddedResult(
        productName: widget.product.name,
        quantity: _quantity,
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
                      onFavorite: () async {
                        await FavoritesScope.of(context).toggle(widget.product.id);
                        if (!mounted) return;
                        setState(() {
                          _favorited = FavoritesScope.of(context)
                              .isFavorite(widget.product.id);
                        });
                      },
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
                                child: TdPhotoFrame(imageUrl: widget.product.imageUrl),
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
                            if (widget.product.sizeOptions.isNotEmpty) ...[
                              const SizedBox(height: 20),
                              Wrap(
                                alignment: WrapAlignment.center,
                                spacing: 0,
                                runSpacing: 8,
                                children: widget.product.sizeOptions
                                    .map(
                                      (option) => TdChip(
                                        label: option.label,
                                        selected: _sizeId == option.id,
                                        onTap: () => setState(() => _sizeId = option.id),
                                      ),
                                    )
                                    .toList(),
                              ),
                            ],
                            if (widget.product.addonOptions.isNotEmpty) ...[
                              const SizedBox(height: 8),
                              Wrap(
                                alignment: WrapAlignment.center,
                                spacing: 0,
                                runSpacing: 8,
                                children: widget.product.addonOptions
                                    .map(
                                      (option) => TdChip(
                                        label: option.chipLabel,
                                        selected: _addonIds.contains(option.id),
                                        onTap: () => setState(() {
                                          if (!_addonIds.remove(option.id)) {
                                            _addonIds.add(option.id);
                                          }
                                        }),
                                      ),
                                    )
                                    .toList(),
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
                        label: widget.product.soldOut ? 'Esgotado' : 'Adicionar',
                        onPressed: widget.product.canBuy ? _addToCart : null,
                        variant: widget.product.canBuy
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
