import 'package:tri_docuras/models/store_config.dart';

/// Um bloco dos Termos de Compra ou da Política de Privacidade.
class LegalSection {
  const LegalSection({required this.title, required this.paragraphs});

  final String title;
  final List<String> paragraphs;
}

/// Quem vende, como aparece no texto. Sem o nome do vendedor configurado,
/// cai no nome da loja.
String sellerText(StoreConfig config) {
  final name = config.sellerName;
  final document = config.sellerDocument;
  if (name == null) return 'a Tri Doçuras';
  if (document == null) return name;
  return '$name, $document';
}

String _contactLine(StoreConfig config) {
  final display = config.storeWhatsAppDisplay;
  if (display == null) return 'Fale com a loja pelo WhatsApp da loja.';
  return 'Fale com a loja pelo WhatsApp $display.';
}

List<LegalSection> privacySections(StoreConfig config) => [
      LegalSection(
        title: 'Quem é responsável',
        paragraphs: [
          'Quem vende os brownies pelo site é ${sellerText(config)}.',
          _contactLine(config),
        ],
      ),
      const LegalSection(
        title: 'Quais dados coletamos',
        paragraphs: [
          'Nome, WhatsApp e e-mail da sua conta.',
          'Endereço de entrega e ponto de referência, quando o pedido é entregue em casa.',
          'Dados do pedido: produtos, valores, data e status.',
          'O pagamento Pix é processado pelo Mercado Pago. A loja recebe só a confirmação de que o pagamento foi feito. Não guardamos dados de cartão.',
        ],
      ),
      const LegalSection(
        title: 'Para que usamos',
        paragraphs: [
          'Preparar, entregar e acompanhar o seu pedido, inclusive pelo WhatsApp.',
          'Manter sua conta, seus endereços e seus favoritos.',
          'Cumprir obrigações fiscais e legais.',
          'Prevenir fraudes e uso indevido do site.',
        ],
      ),
      const LegalSection(
        title: 'Com quem compartilhamos',
        paragraphs: [
          'Mercado Pago, para receber o pagamento. Não vendemos nem alugamos seus dados.',
          'Empresas de hospedagem que mantêm o site e o banco de dados. Elas usam os dados só para isso.',
        ],
      ),
      const LegalSection(
        title: 'Por quanto tempo guardamos',
        paragraphs: [
          'Os dados da conta ficam enquanto ela existir. Os dados dos pedidos ficam pelo prazo exigido pela legislação fiscal e contábil e depois são apagados.',
        ],
      ),
      const LegalSection(
        title: 'Seus direitos',
        paragraphs: [
          'Você pode pedir acesso, correção, exclusão e cópia dos seus dados, e retirar seu consentimento, pelo WhatsApp da loja.',
        ],
      ),
      const LegalSection(
        title: 'Segurança e navegador',
        paragraphs: [
          'O site guarda no seu navegador só o necessário para funcionar, como o login e o carrinho. A comunicação é criptografada (HTTPS) e o painel da loja tem acesso restrito.',
        ],
      ),
      const LegalSection(
        title: 'Mudanças nesta política',
        paragraphs: [
          'Podemos atualizar esta política. A versão em vigor é sempre a publicada aqui.',
        ],
      ),
    ];

List<LegalSection> termsSections(StoreConfig config) => [
      const LegalSection(
        title: 'Como funciona o pedido',
        paragraphs: [
          'O pedido é confirmado quando o pagamento chega à loja.',
          'O Pix tem validade de 10 minutos. Se o pagamento não for feito nesse prazo, o pedido expira e os produtos voltam ao estoque.',
          'Os preços são os exibidos no site no momento do pedido. A taxa de entrega aparece no resumo antes do pagamento.',
        ],
      ),
      const LegalSection(
        title: 'Entrega e retirada',
        paragraphs: [
          'Entregas são feitas no endereço informado no pedido. Retiradas são feitas nos horários combinados com a loja.',
          'Você acompanha o pedido pelo link enviado pela loja ou pela aba Pedidos.',
        ],
      ),
      const LegalSection(
        title: 'Produtos e alergias',
        paragraphs: [
          'Os brownies são artesanais. Se você tem alergia ou restrição alimentar, confirme os ingredientes com a loja antes de comprar.',
        ],
      ),
      const LegalSection(
        title: 'Cancelamento e estorno',
        paragraphs: [
          'Se um pedido pago for cancelado, o valor é devolvido pelo Mercado Pago, na mesma forma de pagamento. O prazo para o dinheiro voltar depende da operadora ou do banco.',
        ],
      ),
      const LegalSection(
        title: 'Desistência da compra',
        paragraphs: [
          'Compras feitas pela internet podem ter direito de arrependimento em até 7 dias, pelo Código de Defesa do Consumidor. Como os brownies são perecíveis e feitos sob pedido, a loja resolve cada caso com o cliente.',
          'Se houver erro ou defeito no pedido, você tem direito à troca ou ao reembolso.',
        ],
      ),
      LegalSection(
        title: 'Quem vende',
        paragraphs: [
          'Vendedor: ${sellerText(config)}.',
          _contactLine(config),
        ],
      ),
    ];
