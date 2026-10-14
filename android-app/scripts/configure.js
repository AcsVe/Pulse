// Pulse is a local-only app (no remote WebView server): it ships its own
// tiny setup screen in www/ and does all real work natively. So, unlike a
// thin wrapper app, capacitor.config.json has no server.url — Capacitor just
// serves the bundled www/ folder from the APK itself.
const fs = require('fs');
const path = require('path');

const config = {
  appId: 'org.pulse.monitor',
  appName: 'Pulse',
  webDir: 'www',
  backgroundColor: '#0b1e31',
  android: { allowMixedContent: false },
};
fs.writeFileSync(path.join(__dirname, '..', 'capacitor.config.json'), JSON.stringify(config, null, 2));
console.log('capacitor.config.json written (local app, no remote server)');
