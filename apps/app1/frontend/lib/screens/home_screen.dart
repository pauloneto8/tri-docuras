import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/cart/cart_added_result.dart';
import 'package:tri_docuras/cart/cart_scope.dart';
import 'package:tri_docuras/config.dart';
import 'package:tri_docuras/models/product.dart';
import 'package:tri_docuras/screens/cart_screen.dart';
import 'package:tri_docuras/screens/product_screen.dart';
import 'package:tri_docuras/services/api_service.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/theme/app_theme.dart';
import 'package:tri_docuras/widgets/td_button.dart';
import 'package:tri_docuras/widgets/td_chip.dart';
import 'package:tri_docuras/widgets/td_icon_button.dart';
import 'package:tri_docuras/widgets/td_photo_frame.dart';
import 'package:tri_docuras/widgets/td_search_field.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ApiService _api = ApiService();
  final TextEditingController _searchController = TextEditingController();

  int _navIndex = 0;
  String _categoryFilter = 'todos';
  String _searchQuery = '';
  late Future<List<Product>> _productsFuture;
  CartAddedResult? _cartAddedNotice;

  static const _categories = [
    ('todos', 'Todos'),
    ('brownies', 'Brownies'),
    ('combos', 'Combos'),
  ];

  @override
  void initState() {
    super.initState();
    _productsFuture = _loadProducts();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<List<Product>> _loadProducts() async {
    try {
      return await _api.fetchProducts();
    } catch (_) {
      return _api.fallbackProducts();
    }
  }

  List<Product> _filterProducts(List<Product> products) {
    return products.where((product) {
      final matchesCategory = product.matchesCategory(_categoryFilter);
      final query = _searchQuery.trim().toLowerCase();
      final matchesSearch = query.isEmpty ||
          product.name.toLowerCase().contains(query) ||
          product.description.toLowerCase().contains(query);
      return matchesCategory && matchesSearch;
    }).toList();
  }

  void _onNavTap(int index) {
    setState(() => _navIndex = index);
  }

  Future<void> _openProduct(Product product) async {
    if (!product.available) return;
    final result = await Navigator.of(context).push<CartAddedResult>(
      MaterialPageRoute(
        builder: (_) => ProductScreen(product: product),
      ),
    );
    if (!mounted || result == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _presentCartAddedNotice(result);
    });
  }

  void _presentCartAddedNotice(CartAddedResult result) {
    setState(() => _cartAddedNotice = result);
    Future.delayed(const Duration(seconds: 5), () {
      if (mounted && _cartAddedNotice == result) {
        setState(() => _cartAddedNotice = null);
      }
    });
  }

  void _openCartFromNotice() {
    setState(() => _cartAddedNotice = null);
    _openCart();
  }

  void _openCart() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const CartScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cartCount = CartScope.of(context).itemCount;
    return Stack(
      children: [
        ColoredBox(
          color: AppColors.cream,
          child: SafeArea(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _CatalogHeader(
                  cartCount: cartCount,
                  onCartTap: _openCart,
                ),
                Expanded(
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      final contentWidth =
                          constraints.maxWidth.clamp(0, AppTheme.maxContentWidth);
                      return Align(
                        alignment: Alignment.topCenter,
                        child: SizedBox(
                          width: contentWidth.toDouble(),
                          height: constraints.maxHeight,
                          child: _navIndex == 0
                              ? _buildCatalog()
                              : _buildPlaceholderTab(),
                        ),
                      );
                    },
                  ),
                ),
                _BottomNav(
                  currentIndex: _navIndex,
                  onTap: _onNavTap,
                ),
              ],
            ),
          ),
        ),
        if (_cartAddedNotice != null)
          Positioned(
            left: 16,
            right: 16,
            bottom: MediaQuery.of(context).padding.bottom + 72,
            child: CartAddedBanner(
              result: _cartAddedNotice!,
              onViewCart: _openCartFromNotice,
            ),
          ),
      ],
    );
  }

  Widget _buildPlaceholderTab() {
    const labels = ['', 'Pedidos', 'Favoritos', 'Perfil'];
    return ColoredBox(
      color: AppColors.cream,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.favorite, size: 36, color: AppColors.pink),
              const SizedBox(height: 16),
              Text(
                '${labels[_navIndex]} — em breve',
                style: Theme.of(context).textTheme.headlineSmall,
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCatalog() {
    return FutureBuilder<List<Product>>(
      future: _productsFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const ColoredBox(
            color: AppColors.cream,
            child: Center(
              child: CircularProgressIndicator(color: AppColors.pinkDeep),
            ),
          );
        }

        final source = snapshot.data ?? _api.fallbackProducts();
        final products = _filterProducts(source);
        return _buildCatalogContent(products);
      },
    );
  }

  Widget _buildCatalogContent(List<Product> products) {
    return ColoredBox(
      color: AppColors.cream,
      child: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
              child: TdSearchField(
                controller: _searchController,
                onChanged: (value) => setState(() => _searchQuery = value),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: SizedBox(
              height: 40,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                children: _categories
                    .map(
                      (entry) => TdChip(
                        label: entry.$2,
                        selected: _categoryFilter == entry.$1,
                        onTap: () => setState(() => _categoryFilter = entry.$1),
                      ),
                    )
                    .toList(),
              ),
            ),
          ),
          const SliverToBoxAdapter(child: SizedBox(height: 16)),
          if (products.isEmpty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: Center(
                child: Text(
                  'Nenhum brownie encontrado',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              sliver: SliverGrid(
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  mainAxisSpacing: 12,
                  crossAxisSpacing: 12,
                  mainAxisExtent: 268,
                ),
                delegate: SliverChildBuilderDelegate(
                  (context, index) => _ProductGridCard(
                    product: products[index],
                    onTap: () => _openProduct(products[index]),
                    onAdd: () => _openProduct(products[index]),
                  ),
                  childCount: products.length,
                ),
              ),
            ),
          const SliverToBoxAdapter(child: SizedBox(height: 24)),
        ],
      ),
    );
  }
}

class _CatalogHeader extends StatelessWidget {
  const _CatalogHeader({
    required this.cartCount,
    required this.onCartTap,
  });

  final int cartCount;
  final VoidCallback onCartTap;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppColors.cream,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 4, 8, 4),
        child: Row(
          children: [
            TdIconButton(
              icon: Icons.menu,
              onPressed: () {},
              tint: AppColors.peach,
            ),
            Expanded(
              child: Text(
                AppConfig.appName,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.displayMedium,
              ),
            ),
            Stack(
              clipBehavior: Clip.none,
              children: [
                TdIconButton(
                  icon: Icons.shopping_cart_outlined,
                  onPressed: onCartTap,
                  tint: AppColors.peach,
                ),
                if (cartCount > 0)
                  Positioned(
                    right: 2,
                    top: 2,
                    child: Container(
                      width: 18,
                      height: 18,
                      alignment: Alignment.center,
                      decoration: const BoxDecoration(
                        color: AppColors.pinkDeep,
                        shape: BoxShape.circle,
                      ),
                      child: Text(
                        '$cartCount',
                        style: GoogleFonts.poppins(
                          color: AppColors.white,
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                          height: 1,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ProductGridCard extends StatelessWidget {
  const _ProductGridCard({
    required this.product,
    required this.onTap,
    required this.onAdd,
  });

  final Product product;
  final VoidCallback onTap;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.card,
            borderRadius: BorderRadius.circular(20),
            boxShadow: [
              BoxShadow(
                color: AppColors.dark.withValues(alpha: 0.06),
                blurRadius: 10,
                offset: const Offset(0, 3),
              ),
            ],
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 14, 12, 12),
            child: Column(
              children: [
                const Expanded(
                  child: TdPhotoFrame(),
                ),
                const SizedBox(height: 8),
                Text(
                  product.name,
                  style: Theme.of(context).textTheme.titleMedium,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 2),
                Text(
                  product.formattedPrice,
                  style: Theme.of(context).textTheme.bodyLarge,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                TdButton(
                  label: product.available ? 'Adicionar' : 'Indisponível',
                  variant: product.available ? TdButtonVariant.primary : TdButtonVariant.disabled,
                  onPressed: product.available ? onAdd : null,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _BottomNav extends StatelessWidget {
  const _BottomNav({
    required this.currentIndex,
    required this.onTap,
  });

  final int currentIndex;
  final ValueChanged<int> onTap;

  static const _items = [
    (Icons.home_outlined, Icons.home, 'Início'),
    (Icons.receipt_long_outlined, Icons.receipt_long, 'Pedidos'),
    (Icons.favorite_outline, Icons.favorite, 'Favoritos'),
    (Icons.sentiment_satisfied_alt_outlined, Icons.sentiment_satisfied_alt, 'Perfil'),
  ];

  static const _idleColors = [
    AppColors.tan,
    AppColors.sky,
    AppColors.tan,
    AppColors.tan,
  ];

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.white,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
        boxShadow: [
          BoxShadow(
            color: AppColors.dark.withValues(alpha: 0.06),
            blurRadius: 12,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: List.generate(_items.length, (index) {
            final item = _items[index];
            final selected = currentIndex == index;
            final color = selected ? AppColors.pinkDeep : _idleColors[index];
            return InkWell(
              onTap: () => onTap(index),
              borderRadius: BorderRadius.circular(12),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      selected ? item.$2 : item.$1,
                      color: color,
                      size: 22,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      item.$3,
                      style: GoogleFonts.poppins(
                        color: color,
                        fontSize: 10,
                        fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}
