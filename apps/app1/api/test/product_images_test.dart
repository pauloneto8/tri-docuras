import 'package:test/test.dart';
import 'package:tri_docuras_api/product_images.dart';

void main() {
  group('product image helpers', () {
    test('buildProductImageUrl', () {
      expect(buildProductImageUrl(4, 'jpg'), '/api/uploads/products/4.jpg');
    });

    test('extensionForContentType', () {
      expect(extensionForContentType('image/jpeg'), 'jpg');
      expect(extensionForContentType('image/png'), 'png');
      expect(extensionForContentType('image/gif'), isNull);
    });

    test('validateImageBytes rejects empty', () {
      expect(
        () => validateImageBytes([], 'jpg'),
        throwsA(isA<ProductImageException>()),
      );
    });

    test('resolveProductImageFile blocks path traversal', () {
      expect(resolveProductImageFile('../secret.jpg'), isNull);
      expect(resolveProductImageFile('abc.jpg'), isNull);
    });
  });
}
