import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/theme/app_colors.dart';

class TdQuantityStepper extends StatelessWidget {
  const TdQuantityStepper({
    super.key,
    required this.value,
    required this.onChanged,
    this.min = 1,
    this.max = 99,
    this.compact = false,
  });

  final int value;
  final ValueChanged<int> onChanged;
  final int min;
  final int max;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final buttonSize = compact ? 32.0 : 40.0;
    final iconSize = compact ? 16.0 : 20.0;
    final fontSize = compact ? 15.0 : 18.0;
    final horizontalGap = compact ? 12.0 : 24.0;

    return Row(
      mainAxisAlignment: compact ? MainAxisAlignment.end : MainAxisAlignment.center,
      mainAxisSize: compact ? MainAxisSize.min : MainAxisSize.max,
      children: [
        _StepButton(
          icon: Icons.remove,
          enabled: value > min,
          onTap: () => onChanged(value - 1),
          size: buttonSize,
          iconSize: iconSize,
        ),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: horizontalGap),
          child: Text(
            '$value',
            style: GoogleFonts.poppins(
              fontSize: fontSize,
              fontWeight: FontWeight.w600,
              color: AppColors.dark,
            ),
          ),
        ),
        _StepButton(
          icon: Icons.add,
          enabled: value < max,
          onTap: () => onChanged(value + 1),
          size: buttonSize,
          iconSize: iconSize,
        ),
      ],
    );
  }
}

class _StepButton extends StatelessWidget {
  const _StepButton({
    required this.icon,
    required this.enabled,
    required this.onTap,
    required this.size,
    required this.iconSize,
  });

  final IconData icon;
  final bool enabled;
  final VoidCallback onTap;
  final double size;
  final double iconSize;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: enabled ? onTap : null,
        child: Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: enabled ? AppColors.brown : AppColors.brown.withValues(alpha: 0.35),
              width: 1.2,
            ),
          ),
          alignment: Alignment.center,
          child: Icon(
            icon,
            size: iconSize,
            color: enabled ? AppColors.brown : AppColors.brown.withValues(alpha: 0.35),
          ),
        ),
      ),
    );
  }
}
