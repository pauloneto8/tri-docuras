import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:tri_docuras/theme/app_colors.dart';

/// Moldura circular assinatura — dois anéis concêntricos e coração rosa,
/// herdada da logo (Design System v1).
class TdPhotoFrame extends StatelessWidget {
  const TdPhotoFrame({
    super.key,
    this.imageUrl,
  });

  final String? imageUrl;

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 1,
      child: CustomPaint(
        painter: const TdPhotoFramePainter(),
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: ClipOval(
            child: imageUrl != null
                ? Image.network(
                    imageUrl!,
                    fit: BoxFit.cover,
                    width: double.infinity,
                    height: double.infinity,
                  )
                : ColoredBox(
                    color: AppColors.peach,
                    child: Center(
                      child: LayoutBuilder(
                        builder: (context, constraints) {
                          final size = math.min(constraints.maxWidth, constraints.maxHeight) * 0.28;
                          return Icon(
                            Icons.favorite,
                            size: size.clamp(14, 36),
                            color: AppColors.pink,
                          );
                        },
                      ),
                    ),
                  ),
          ),
        ),
      ),
    );
  }
}

class TdPhotoFramePainter extends CustomPainter {
  const TdPhotoFramePainter();

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2;

    final fill = Paint()
      ..style = PaintingStyle.fill
      ..color = AppColors.peach;
    canvas.drawCircle(center, radius - 1, fill);

    final ring = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6
      ..color = AppColors.brown;

    canvas.drawCircle(center, radius - 1.6, ring);
    canvas.drawCircle(center, radius - 6.5, ring);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
