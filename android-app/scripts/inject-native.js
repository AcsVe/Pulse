#!/usr/bin/env node
// Runs in CI after `npx cap add android` (which generates android/). It:
//  1. copies our hand-written Java sources + XML/strings into the generated project,
//  2. registers the PulsePlugin in MainActivity,
//  3. patches AndroidManifest.xml with the permissions, service and receiver declarations
//     our native code needs (Capacitor's generated manifest doesn't know about any of this).
// Idempotent: safe to run more than once (patches check for their own markers first).
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const ANDROID = path.join(ROOT, 'android');
const PKG_PATH = 'app/src/main/java/org/pulse/monitor';
const JAVA_DST = path.join(ANDROID, PKG_PATH);
const RES_DST = path.join(ANDROID, 'app/src/main/res');
const MANIFEST = path.join(ANDROID, 'app/src/main/AndroidManifest.xml');

function fail(msg) { console.error('inject-native: ' + msg); process.exit(1); }

if (!fs.existsSync(ANDROID)) fail('android/ not found — run `npx cap add android` first');

// 1. Java sources -----------------------------------------------------------
fs.mkdirSync(JAVA_DST, { recursive: true });
const javaSrcDir = path.join(ROOT, 'native-src/java/org/pulse/monitor');
for (const f of fs.readdirSync(javaSrcDir)) {
  fs.copyFileSync(path.join(javaSrcDir, f), path.join(JAVA_DST, f));
  console.log('copied', f);
}

// 2. Resources ----------------------------------------------------------------
const xmlDst = path.join(RES_DST, 'xml');
fs.mkdirSync(xmlDst, { recursive: true });
fs.copyFileSync(path.join(ROOT, 'native-src/xml/pulse_accessibility_config.xml'), path.join(xmlDst, 'pulse_accessibility_config.xml'));
fs.copyFileSync(path.join(ROOT, 'native-src/xml/pulse_device_admin.xml'), path.join(xmlDst, 'pulse_device_admin.xml'));

// Default (values/, no qualifier) is Arabic and English (values-en/) is the
// explicit override — without the second one, Android has no English
// resource to fall back to and always shows the Arabic description in
// system screens (the Accessibility settings list, the device-admin
// activation screen) regardless of the phone's own language, since those
// are native string resources the in-app JS language toggle can't reach at
// all. Looping over both locale dirs here instead of hand-duplicating the
// single-locale block keeps it from silently drifting out of sync again if
// a third locale is ever added.
for (const locale of ['values', 'values-en']) {
  const srcFile = path.join(ROOT, `native-src/${locale}/pulse_strings.xml`);
  if (!fs.existsSync(srcFile)) continue;
  const pulseStringsSnippet = fs.readFileSync(srcFile, 'utf8')
    .match(/<resources>([\s\S]*)<\/resources>/)[1].trim();
  const stringsPath = path.join(RES_DST, locale, 'strings.xml');
  fs.mkdirSync(path.dirname(stringsPath), { recursive: true });
  let strings = fs.existsSync(stringsPath)
    ? fs.readFileSync(stringsPath, 'utf8')
    : '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n</resources>\n';
  if (!strings.includes('pulse_access_desc')) {
    strings = strings.replace('</resources>', '    ' + pulseStringsSnippet + '\n</resources>');
    fs.writeFileSync(stringsPath, strings);
    console.log('patched', locale + '/strings.xml');
  }
}

// 3. MainActivity: register the plugin ---------------------------------------
const mainActivityPath = path.join(JAVA_DST, 'MainActivity.java');
if (!fs.existsSync(mainActivityPath)) fail('MainActivity.java not found at ' + mainActivityPath);
let mainActivity = fs.readFileSync(mainActivityPath, 'utf8');
if (!mainActivity.includes('registerPlugin(PulsePlugin.class)')) {
  if (!/public class MainActivity extends BridgeActivity\s*\{/.test(mainActivity)) {
    fail('MainActivity.java has an unexpected shape — could not find the class body to patch');
  }
  mainActivity = mainActivity.replace(
    /public class MainActivity extends BridgeActivity\s*\{/,
    'public class MainActivity extends BridgeActivity {\n' +
    '  @Override\n' +
    '  public void onCreate(android.os.Bundle savedInstanceState) {\n' +
    '    registerPlugin(PulsePlugin.class);\n' +
    '    super.onCreate(savedInstanceState);\n' +
    '  }\n'
  );
  fs.writeFileSync(mainActivityPath, mainActivity);
  console.log('patched MainActivity.java');
}

// 4. AndroidManifest.xml -------------------------------------------------------
let manifest = fs.readFileSync(MANIFEST, 'utf8');

const permissions = [
  'android.permission.INTERNET',
  'android.permission.ACCESS_NETWORK_STATE',
  'android.permission.ACCESS_WIFI_STATE',
  'android.permission.FOREGROUND_SERVICE',
  'android.permission.FOREGROUND_SERVICE_DATA_SYNC',
  'android.permission.FOREGROUND_SERVICE_MEDIA_PROJECTION',
  'android.permission.RECEIVE_BOOT_COMPLETED',
  'android.permission.POST_NOTIFICATIONS',
  'android.permission.PACKAGE_USAGE_STATS',
  'android.permission.BIND_VPN_SERVICE',
  // Without this, Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS throws
  // a SecurityException that PulsePlugin used to swallow silently — the
  // "Ignore battery optimization" button would just do nothing when tapped.
  'android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS',
  // Remote control's "close app": the only kill a normal (non system, non
  // Device-Owner) app can do to another app's process — not a true
  // force-stop, just what this permission already allows: killing another
  // app's *cached/background* process, same effect as swiping it off Recents.
  'android.permission.KILL_BACKGROUND_PROCESSES',
];
for (const p of permissions) {
  const tag = `<uses-permission android:name="${p}" />`;
  if (!manifest.includes(`android:name="${p}"`)) {
    manifest = manifest.replace('<application', `    ${tag}\n\n    <application`);
  }
}
// special-case PACKAGE_USAGE_STATS: declared with tool:ignore since the system
// grants it only via the Usage Access settings screen, never at install time.
manifest = manifest.replace(
  '<uses-permission android:name="android.permission.PACKAGE_USAGE_STATS" />',
  '<uses-permission android:name="android.permission.PACKAGE_USAGE_STATS" tools:ignore="ProtectedPermissions" />'
);
if (!manifest.includes('xmlns:tools=')) {
  manifest = manifest.replace('<manifest ', '<manifest xmlns:tools="http://schemas.android.com/tools" ');
}

// Pulse talks to a plain-HTTP server on the user's own LAN (no TLS cert is
// practical for a local IP), but Android blocks cleartext (non-HTTPS)
// traffic by default for apps targeting API 28+. Without this, enrollment
// and sync silently fail to reach an http:// server while the same URL
// works fine in a browser (the OS cleartext block is per-app, not global).
if (!manifest.includes('android:usesCleartextTraffic=')) {
  manifest = manifest.replace('<application', '<application\n        android:usesCleartextTraffic="true"');
}

// Android 11+ hides other apps' packages from PackageManager queries by
// default (package visibility) unless declared here — needed for remote
// control's "open app" list (queryIntentActivities for MAIN/LAUNCHER).
// Scoped to launchable apps only, not the broader QUERY_ALL_PACKAGES
// permission, since that's all this feature needs.
if (!manifest.includes('<queries>')) {
  const queriesBlock = `    <queries>
        <intent>
            <action android:name="android.intent.action.MAIN" />
            <category android:name="android.intent.category.LAUNCHER" />
        </intent>
    </queries>

`;
  manifest = manifest.replace('<application', queriesBlock + '    <application');
}

// 4b. Wrap MainActivity's launcher intent-filter in a toggleable activity-alias,
// so the icon can be hidden/shown at runtime (IconVisibility.hide/show) without
// touching MainActivity itself. Idempotent: skipped if already wrapped.
if (!manifest.includes('android:name=".LauncherAlias"') && !manifest.includes('android:name="org.pulse.monitor.LauncherAlias"')) {
  const activityRe = /<activity\s+([^>]*android:name="\.MainActivity"[^>]*)>([\s\S]*?)<\/activity>/;
  const m = manifest.match(activityRe);
  if (!m) fail('could not find the MainActivity <activity> block to wrap with a launcher alias');
  const attrs = m[1];
  const inner = m[2];
  const launcherFilterRe = /<intent-filter>\s*<action android:name="android\.intent\.action\.MAIN"\s*\/>\s*<category android:name="android\.intent\.category\.LAUNCHER"\s*\/>\s*<\/intent-filter>/;
  const filterMatch = inner.match(launcherFilterRe);
  if (!filterMatch) fail('could not find the MAIN/LAUNCHER intent-filter inside MainActivity to move to the alias');
  const innerWithoutFilter = inner.replace(launcherFilterRe, '').trim();
  const activityWithoutLauncher = `<activity ${attrs.replace(/\s*android:exported="true"/, ' android:exported="true"')}>\n        ${innerWithoutFilter}\n        </activity>`;
  const alias = `
        <activity-alias
            android:name=".LauncherAlias"
            android:targetActivity=".MainActivity"
            android:exported="true"
            android:icon="@mipmap/ic_launcher"
            android:roundIcon="@mipmap/ic_launcher_round"
            android:label="@string/app_name"
            android:enabled="true">
            ${filterMatch[0]}
        </activity-alias>
`;
  manifest = manifest.replace(m[0], activityWithoutLauncher + '\n' + alias);
  console.log('wrapped MainActivity launcher intent-filter in .LauncherAlias');
}

const componentsBlock = `
        <receiver
            android:name="org.pulse.monitor.ShowIconReceiver"
            android:exported="false" />

        <service
            android:name="org.pulse.monitor.CollectorService"
            android:foregroundServiceType="dataSync"
            android:exported="false" />

        <service
            android:name="org.pulse.monitor.ScreenCaptureService"
            android:foregroundServiceType="mediaProjection"
            android:exported="false" />

        <service
            android:name="org.pulse.monitor.DnsVpnService"
            android:permission="android.permission.BIND_VPN_SERVICE"
            android:exported="false">
            <intent-filter>
                <action android:name="android.net.VpnService" />
            </intent-filter>
        </service>

        <service
            android:name="org.pulse.monitor.PulseAccessibilityService"
            android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"
            android:exported="false">
            <intent-filter>
                <action android:name="android.accessibilityservice.AccessibilityService" />
            </intent-filter>
            <meta-data
                android:name="android.accessibilityservice"
                android:resource="@xml/pulse_accessibility_config" />
        </service>

        <receiver
            android:name="org.pulse.monitor.BootReceiver"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
                <action android:name="android.intent.action.QUICKBOOT_POWERON" />
            </intent-filter>
        </receiver>

        <receiver
            android:name="org.pulse.monitor.PulseDeviceAdminReceiver"
            android:permission="android.permission.BIND_DEVICE_ADMIN"
            android:exported="true">
            <meta-data
                android:name="android.app.device_admin"
                android:resource="@xml/pulse_device_admin" />
            <intent-filter>
                <action android:name="android.app.action.DEVICE_ADMIN_ENABLED" />
            </intent-filter>
        </receiver>
`;
if (!manifest.includes('org.pulse.monitor.CollectorService')) {
  manifest = manifest.replace('</application>', componentsBlock + '    </application>');
}

fs.writeFileSync(MANIFEST, manifest);
console.log('patched AndroidManifest.xml');
console.log('inject-native: done');
