import 'dart:io';

class ProductImageException implements Exception {
  ProductImageException(this.message);

  final String message;

  @override
  String toString() => message;
}

const _maxBytes = 5 * 1024 * 1024;
const _allowedExtensions = {'jpg', 'jpeg', 'png', 'webp'};

String productsUploadDirectory() {
  return Platform.environment['APP1_UPLOADS_DIR'] ?? '/app/uploads/products';
}

String? extensionForContentType(String? contentType) {
  final normalized = contentType?.toLowerCase().trim();
  switch (normalized) {
    case 'image/jpeg':
    case 'image/jpg':
      return 'jpg';
    case 'image/png':
      return 'png';
    case 'image/webp':
      return 'webp';
    default:
      return null;
  }
}

String? extensionForFilename(String? filename) {
  if (filename == null || filename.trim().isEmpty) return null;
  final parts = filename.split('.');
  if (parts.length < 2) return null;
  final ext = parts.last.toLowerCase();
  return _allowedExtensions.contains(ext) ? ext : null;
}

void validateImageBytes(List<int> bytes, String extension) {
  if (bytes.isEmpty) {
    throw ProductImageException('Arquivo de imagem vazio.');
  }
  if (bytes.length > _maxBytes) {
    throw ProductImageException('Imagem muito grande (máx. 5 MB).');
  }
  if (!_allowedExtensions.contains(extension)) {
    throw ProductImageException('Formato inválido. Use JPG, PNG ou WebP.');
  }
}

String buildProductImagePath(int productId, String extension) {
  return '$productId.$extension';
}

String buildProductImageUrl(int productId, String extension) {
  return '/api/uploads/products/${buildProductImagePath(productId, extension)}';
}

Future<void> ensureUploadDirectory() async {
  final dir = Directory(productsUploadDirectory());
  if (!dir.existsSync()) {
    dir.createSync(recursive: true);
  }
}

Future<void> deleteProductImageFiles(int productId) async {
  final dir = Directory(productsUploadDirectory());
  if (!dir.existsSync()) return;

  for (final ext in _allowedExtensions) {
    final file = File('${dir.path}/$productId.$ext');
    if (file.existsSync()) {
      await file.delete();
    }
  }
}

Future<String> saveProductImage({
  required int productId,
  required List<int> bytes,
  required String extension,
}) async {
  validateImageBytes(bytes, extension);
  await ensureUploadDirectory();
  await deleteProductImageFiles(productId);

  final filename = buildProductImagePath(productId, extension);
  final file = File('${productsUploadDirectory()}/$filename');
  await file.writeAsBytes(bytes, flush: true);
  return buildProductImageUrl(productId, extension);
}

File? resolveProductImageFile(String filename) {
  if (!RegExp(r'^\d+\.(jpe?g|png|webp)$', caseSensitive: false).hasMatch(filename)) {
    return null;
  }
  final file = File('${productsUploadDirectory()}/$filename');
  if (!file.existsSync()) return null;
  return file;
}

String contentTypeForFilename(String filename) {
  final ext = extensionForFilename(filename) ?? 'jpg';
  switch (ext) {
    case 'png':
      return 'image/png';
    case 'webp':
      return 'image/webp';
    default:
      return 'image/jpeg';
  }
}
