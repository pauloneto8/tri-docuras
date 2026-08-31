import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/theme/app_colors.dart';

/// Resultado ao adicionar produto no carrinho (passado via [Navigator.pop]).
class CartAddedResult {
  const CartAddedResult({
    required this.productName,
    required this.quantity,
  });

  final String productName;
  final int quantity;

  String get detailLine => quantity > 1
      ? '$quantity× $productName'
      : productName;
}

/// Balão flutuante exibido no catálogo após adicionar ao carrinho.
class CartAddedBanner extends StatelessWidget {
  const CartAddedBanner({
    super.key,
    required this.result,
    required this.onViewCart,
  });

  final CartAddedResult result;
  final VoidCallback onViewCart;

  @override
  Widget build(BuildContext context) {
    return Material(
      elevation: 6,
      shadowColor: AppColors.dark.withValues(alpha: 0.2),
      color: AppColors.dark,
      borderRadius: BorderRadius.circular(16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.pinkDeep,
                borderRadius: BorderRadius.circular(999),
              ),
              child: const Padding(
                padding: EdgeInsets.all(8),
                child: Icon(
                  Icons.shopping_cart_outlined,
                  color: AppColors.white,
                  size: 22,
                ),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Adicionado ao carrinho',
                    style: GoogleFonts.poppins(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: AppColors.white,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    result.detailLine,
                    style: GoogleFonts.poppins(
                      fontSize: 13,
                      fontWeight: FontWeight.w400,
                      color: AppColors.white.withValues(alpha: 0.9),
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 6),
                  InkWell(
                    onTap: onViewCart,
                    borderRadius: BorderRadius.circular(4),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Text(
                        'Ver carrinho',
                        style: GoogleFonts.poppins(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: AppColors.sky,
                          decoration: TextDecoration.underline,
                          decorationColor: AppColors.sky,
                        ),
                      ),
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
