import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/favorites/favorites_scope.dart';
import 'package:tri_docuras/models/product.dart';
import 'package:tri_docuras/screens/product_screen.dart';
import 'package:tri_docuras/services/api_service.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/widgets/td_button.dart';
import 'package:tri_docuras/widgets/td_icon_button.dart';
import 'package:tri_docuras/widgets/td_photo_frame.dart';

/// Lista de produtos favoritos (aba 3 da bottom nav).
class FavoritesScreen extends StatefulWidget {
  const FavoritesScreen({
    super.key,
    this.api,
    this.onBrowseCatalog,
  });

  final ApiService? api;
  final VoidCallback? onBrowseCatalog;

  @override
  State<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends State<FavoritesScreen> {
  late final ApiService _api;
  late Future<List<Product>> _productsFuture;

  @override
  void initState() {
    super.initState();
    _api = widget.api ?? ApiService();
    _productsFuture = _loadProducts();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      FavoritesScope.of(context).load();
    });
  }

  Future<List<Product>> _loadProducts() async {
    try {
      return await _api.fetchProducts();
    } catch (_) {
      return _api.fallbackProducts();
    }
  }

  void _openProduct(Product product) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => ProductScreen(product: product)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final favorites = FavoritesScope.of(context);

    return ColoredBox(
      color: AppColors.cream,
      child: FutureBuilder<List<Product>>(
        future: _productsFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting &&
              !favorites.isLoaded) {
            return const Center(
              child: CircularProgressIndicator(color: AppColors.pinkDeep),
            );
          }

          final all = snapshot.data ?? _api.fallbackProducts();
          final items = all.where((p) => favorites.isFavorite(p.id)).toList();

          if (items.isEmpty) {
            return _EmptyFavorites(onBrowse: widget.onBrowseCatalog);
          }

          return CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
                  child: Text(
                    'Seus favoritos',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                  child: Text(
                    '${items.length} ${items.length == 1 ? 'item' : 'itens'} salvos',
                    style: GoogleFonts.poppins(
                      fontSize: 14,
                      color: AppColors.brown,
                    ),
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                sliver: SliverList.separated(
                  itemCount: items.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 10),
                  itemBuilder: (context, index) {
                    final product = items[index];
                    return _FavoriteCard(
                      product: product,
                      onTap: () => _openProduct(product),
                      onRemove: () => favorites.remove(product.id),
                    );
                  },
                ),
              ),
              const SliverToBoxAdapter(child: SizedBox(height: 24)),
            ],
          );
        },
      ),
    );
  }
}

class _EmptyFavorites extends StatelessWidget {
  const _EmptyFavorites({this.onBrowse});

  final VoidCallback? onBrowse;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.favorite_border, size: 48, color: AppColors.pink),
            const SizedBox(height: 16),
            Text(
              'Nenhum favorito ainda',
              style: Theme.of(context).textTheme.headlineSmall,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              'Toque no coração na página do produto para salvar seus brownies preferidos.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if (onBrowse != null) ...[
              const SizedBox(height: 20),
              TdButton(
                label: 'Ver catálogo',
                variant: TdButtonVariant.soft,
                onPressed: onBrowse,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _FavoriteCard extends StatelessWidget {
  const _FavoriteCard({
    required this.product,
    required this.onTap,
    required this.onRemove,
  });

  final Product product;
  final VoidCallback onTap;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.card,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.brown.withValues(alpha: 0.1)),
          ),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                const SizedBox(
                  width: 72,
                  height: 72,
                  child: TdPhotoFrame(),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        product.name,
                        style: Theme.of(context).textTheme.titleMedium,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        product.formattedPrice,
                        style: Theme.of(context).textTheme.bodyLarge,
                      ),
                    ],
                  ),
                ),
                TdIconButton(
                  icon: Icons.favorite,
                  onPressed: onRemove,
                  tint: AppColors.peach,
                  iconColor: AppColors.pinkDeep,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
