import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/theme/app_colors.dart';

enum TdButtonVariant { primary, outline, soft, disabled }

class TdButton extends StatelessWidget {
  const TdButton({
    super.key,
    required this.label,
    this.onPressed,
    this.variant = TdButtonVariant.primary,
    this.expand = true,
    this.trailing,
  });

  final String label;
  final VoidCallback? onPressed;
  final TdButtonVariant variant;
  final bool expand;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final isDisabled = variant == TdButtonVariant.disabled || onPressed == null;

    late final Color background;
    late final Color foreground;
    BorderSide? border;

    switch (variant) {
      case TdButtonVariant.primary:
        background = AppColors.pinkDeep;
        foreground = AppColors.white;
        border = null;
      case TdButtonVariant.outline:
        background = Colors.transparent;
        foreground = AppColors.brown;
        border = const BorderSide(color: AppColors.brown, width: 1.2);
      case TdButtonVariant.soft:
        background = AppColors.peach;
        foreground = AppColors.dark;
        border = null;
      case TdButtonVariant.disabled:
        background = AppColors.disabled;
        foreground = AppColors.brown.withValues(alpha: 0.55);
        border = null;
    }

    final button = Material(
      color: background,
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        onTap: isDisabled ? null : onPressed,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            border: border != null ? Border.fromBorderSide(border) : null,
          ),
          alignment: Alignment.center,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: expand ? MainAxisSize.max : MainAxisSize.min,
            children: [
              Text(
                label,
                style: GoogleFonts.poppins(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: foreground,
                  height: 1.1,
                ),
              ),
              if (trailing != null) ...[
                const Spacer(),
                DefaultTextStyle.merge(
                  style: GoogleFonts.poppins(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: foreground,
                  ),
                  child: trailing!,
                ),
              ],
            ],
          ),
        ),
      ),
    );

    return expand ? SizedBox(width: double.infinity, child: button) : button;
  }
}
