{{flutter_js}}
{{flutter_build_config}}

// CanvasKit é servido localmente a partir de /canvaskit pelo próprio container
// (nginx.conf da app1-web). Sem esta config o engine cairia no CDN
// https://www.gstatic.com/flutter-canvaskit, que é bloqueado pelo CSP em
// nginx/ssl/app1.conf (script-src/connect-src 'self') e derrubava o app.
_flutter.loader.load({
  config: {
    canvasKitBaseUrl: "canvaskit/",
  },
  serviceWorkerSettings: {
    serviceWorkerVersion: {{flutter_service_worker_version}}
  }
});
