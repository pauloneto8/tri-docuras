import 'package:flutter/material.dart';
import 'package:tri_docuras/theme/app_colors.dart';

class TdIconButton extends StatelessWidget {
  const TdIconButton({
    super.key,
    required this.icon,
    required this.onPressed,
    this.tint,
    this.iconColor,
  });

  final IconData icon;
  final VoidCallback onPressed;
  final Color? tint;
  final Color? iconColor;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: tint ?? Colors.transparent,
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onPressed,
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Icon(icon, color: iconColor ?? AppColors.dark, size: 24),
        ),
      ),
    );
  }
}
