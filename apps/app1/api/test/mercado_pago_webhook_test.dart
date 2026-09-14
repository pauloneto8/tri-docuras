import 'package:test/test.dart';
import 'package:tri_docuras_api/mercado_pago_webhook.dart';

void main() {
  group('MercadoPagoWebhookSignature', () {
    test('parseSignatureHeader extrai ts e v1', () {
      final parsed = MercadoPagoWebhookSignature.parseSignatureHeader(
        'ts=1704908010,v1=618c85345248dd820d5fb56065fb3d10',
      );
      expect(parsed['ts'], '1704908010');
      expect(parsed['v1'], '618c85345248dd820d5fb56065fb3d10');
    });

    test('buildManifest monta a string no formato esperado pelo MP', () {
      final manifest = MercadoPagoWebhookSignature.buildManifest(
        dataId: '123456',
        requestId: 'req-abc',
        ts: '1704908010',
      );
      expect(manifest, 'id:123456;request-id:req-abc;ts:1704908010;');
    });

    test('sign é determinístico e muda com a secret', () {
      const manifest = 'id:123;request-id:r;ts:1;';
      final s1 = MercadoPagoWebhookSignature.sign(manifest, 'secret-a');
      final s2 = MercadoPagoWebhookSignature.sign(manifest, 'secret-a');
      final s3 = MercadoPagoWebhookSignature.sign(manifest, 'secret-b');
      expect(s1, s2);
      expect(s1, isNot(s3));
      expect(s1, matches(RegExp(r'^[0-9a-f]{64}$')));
    });

    test('isConfigured é false sem APP1_MP_WEBHOOK_SECRET no ambiente', () {
      expect(MercadoPagoWebhookSignature.isConfigured, isFalse);
    });
  });
}
