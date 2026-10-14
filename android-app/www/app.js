(function () {
'use strict';
const T = {
  ar: {
    consentTitle: 'هذا الجهاز يخضع للمراقبة', consentAgree: 'أوافق على تشغيل المراقبة على هذا الجهاز', continue: 'متابعة',
    connectTitle: 'الاتصال بالخادم', serverUrl: 'رابط الخادم', enrollCode: 'رمز الربط', connect: 'اتصال',
    permsTitle: 'الأذونات المطلوبة', permsHint: 'امنح كل إذن لتعمل كل الميزات بشكل صحيح', start: 'بدء المراقبة',
    runningTitle: 'المراقبة تعمل', device: 'الجهاز', server: 'الخادم', lastSync: 'آخر مزامنة', queued: 'بانتظار الإرسال',
    syncNow: 'مزامنة الآن', checkPerms: 'إعادة فحص الأذونات', stop: 'إيقاف المراقبة',
    hideIcon: 'إخفاء الأيقونة', showIconBtn: 'إظهار الأيقونة',
    iconHint: 'يبقى إشعار التشغيل ظاهراً دائماً (يفرضه نظام أندرويد) — اضغط عليه في أي وقت لإعادة إظهار الأيقونة وفتح التطبيق.',
    hideConfirm: 'ستختفي أيقونة التطبيق من قائمة التطبيقات. للعودة إليه لاحقاً: اضغط على إشعار "Pulse" الثابت في شريط الإشعارات. متابعة؟',
    pUsage: 'إحصاءات الاستخدام', pUsageD: 'لرصد التطبيقات المستخدمة ومدتها', pAccess: 'خدمة الوصول', pAccessD: 'لقراءة شريط عنوان المتصفح، وضرورية لعمل النقر والسحب عند التحكم عن بعد',
    pBattery: 'تجاهل تحسين البطارية', pBatteryD: 'لإبقاء الخدمة تعمل في الخلفية', pNotif: 'الإشعارات', pNotifD: 'لعرض إشعار تشغيل الخدمة',
    pAutostart: 'التشغيل التلقائي عند إعادة التشغيل', pAutostartD: 'بعض الهواتف (شاومي، هواوي، أوبو...) توقف هذا تلقائياً — فعّله هنا ليعمل التطبيق دون إعادة فتحه يدوياً',
    pVpn: 'مراقبة DNS', pVpnD: 'لتسجيل أسماء المواقع عبر كل التطبيقات', grant: 'منح', granted: 'ممنوح',
    permError: 'تعذّر فتح هذا الإعداد على هذا الهاتف. جرّب فتحه يدويًا من إعدادات أندرويد.',
    pAdmin: 'حماية إلغاء التثبيت', pAdminD: 'يمنع حذف التطبيق مباشرة دون تعطيل هذه الحماية أولاً من الإعدادات',
    invalidCode: 'الرمز غير صحيح أو منتهي، أو تعذر الاتصال بالخادم', never: 'لم تحدث بعد', neverSynced: 'لم تتم بعد',
    stopConfirm: 'سيتم إيقاف جمع البيانات على هذا الجهاز. هل تريد المتابعة؟', justNow: 'الآن',
    lockTitle: 'أدخل رمز الدخول', unlock: 'دخول', wrongPin: 'رمز غير صحيح',
    pinSetupTitle: 'إنشاء رمز دخول', pinSetupHint: 'رمز من ٤ إلى ٦ أرقام، يُطلب عند فتح التطبيق وعند إيقاف المراقبة',
    newPin: 'الرمز', confirmPin: 'تأكيد الرمز', savePin: 'حفظ',
    pinMismatch: 'الرمزان غير متطابقين', pinLength: 'الرمز يجب أن يكون من ٤ إلى ٦ أرقام',
    enterPinToStop: 'أدخل رمز الدخول لإيقاف المراقبة',
    enableRemote: 'تفعيل التحكم عن بعد', disableRemote: 'إيقاف التحكم عن بعد', remoteOn: 'مفعّل',
    remoteHint: 'يتطلب موافقتك هنا على الجهاز مرة واحدة (مطلب أمني من أندرويد لا يمكن تجاوزه). تُفقد الموافقة بعد إعادة تشغيل الهاتف أو إيقافه القسري وتحتاج تفعيلاً جديداً.',
    remoteDenied: 'لم تتم الموافقة على مشاركة الشاشة'
  },
  en: {
    consentTitle: 'This device is monitored', consentAgree: 'I agree to run monitoring on this device', continue: 'Continue',
    connectTitle: 'Connect to server', serverUrl: 'Server URL', enrollCode: 'Enrollment code', connect: 'Connect',
    permsTitle: 'Required permissions', permsHint: 'Grant each permission so every feature works correctly', start: 'Start monitoring',
    runningTitle: 'Monitoring is running', device: 'Device', server: 'Server', lastSync: 'Last sync', queued: 'Queued',
    syncNow: 'Sync now', checkPerms: 'Recheck permissions', stop: 'Stop monitoring',
    hideIcon: 'Hide app icon', showIconBtn: 'Show app icon',
    iconHint: 'The running notification always stays visible (required by Android) — tap it any time to bring the icon back and reopen the app.',
    hideConfirm: 'The app icon will disappear from your app list. To get back in later: tap the persistent "Pulse" notification. Continue?',
    pUsage: 'Usage access', pUsageD: 'To track which apps are used and for how long', pAccess: 'Accessibility service', pAccessD: 'To read the browser address bar, and required for tap/swipe to work in remote control',
    pBattery: 'Ignore battery optimization', pBatteryD: 'To keep the background service running', pNotif: 'Notifications', pNotifD: 'To show the running-service notice',
    pAutostart: 'Autostart on reboot', pAutostartD: 'Some phones (Xiaomi, Huawei, Oppo...) block this by default — enable it here so the app keeps running without opening it by hand',
    pVpn: 'DNS monitoring', pVpnD: 'To log visited domains across all apps', grant: 'Grant', granted: 'Granted',
    permError: "Couldn't open this setting on this phone. Try opening it manually from Android settings.",
    pAdmin: 'Uninstall protection', pAdminD: 'Blocks removing the app until this protection is turned off from Settings first',
    invalidCode: 'The code is wrong or expired, or the server could not be reached', never: 'Not yet', neverSynced: 'Not yet',
    stopConfirm: 'This stops data collection on this device. Continue?', justNow: 'Just now',
    lockTitle: 'Enter passcode', unlock: 'Unlock', wrongPin: 'Wrong passcode',
    pinSetupTitle: 'Create a passcode', pinSetupHint: '4–6 digits, asked when opening the app and when stopping monitoring',
    newPin: 'Passcode', confirmPin: 'Confirm passcode', savePin: 'Save',
    pinMismatch: 'The passcodes do not match', pinLength: 'The passcode must be 4–6 digits',
    enterPinToStop: 'Enter your passcode to stop monitoring',
    enableRemote: 'Enable remote control', disableRemote: 'Disable remote control', remoteOn: 'Enabled',
    remoteHint: 'Requires your one-time consent right here on the device (an Android security requirement that can\'t be bypassed). Consent is lost after a reboot or force-stop and needs re-enabling.',
    remoteDenied: 'Screen-sharing consent was not granted'
  }
};
let lang = 'ar';
const t = k => (T[lang] && T[lang][k]) || k;
const $ = s => document.querySelector(s);
const SECTIONS = ['lock', 'pinSetup', 'consent', 'enroll', 'perms', 'status'];
const show = id => { SECTIONS.forEach(s => $('#' + s).classList.toggle('hidden', s !== id)); };

function paint() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  $('#langBtn').textContent = lang === 'ar' ? 'EN' : 'عربي';
  document.querySelectorAll('[data-t]').forEach(e => { e.textContent = t(e.dataset.t); });
  $('#serverUrl').placeholder = 'https://pulse.example.com';
}

const Pulse = () => (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Pulse) || null;

const PERMS = [
  { key: 'usageAccess', t: 'pUsage', d: 'pUsageD', action: 'openUsageAccessSettings' },
  { key: 'accessibility', t: 'pAccess', d: 'pAccessD', action: 'openAccessibilitySettings' },
  { key: 'battery', t: 'pBattery', d: 'pBatteryD', action: 'requestBattery' },
  { key: 'notifications', t: 'pNotif', d: 'pNotifD', action: 'requestNotifications' },
  { key: 'vpn', t: 'pVpn', d: 'pVpnD', action: 'requestVpn' },
  { key: 'deviceAdmin', t: 'pAdmin', d: 'pAdminD', action: 'requestDeviceAdmin', statusCall: 'isDeviceAdminActive', optional: true },
  { key: 'autostart', t: 'pAutostart', d: 'pAutostartD', action: 'requestAutostart', optional: true },
];

async function refreshPerms() {
  const p = Pulse(); if (!p) return {};
  const st = await p.getPermStatus();
  const admin = await p.isDeviceAdminActive();
  st.deviceAdmin = admin.value;
  const list = $('#permList'); list.innerHTML = '';
  PERMS.forEach(info => {
    const on = !!st[info.key];
    const row = document.createElement('div');
    row.className = 'perm' + (on ? ' on' : '');
    row.innerHTML = `<div><div class="pt"><span class="dot"></span>${t(info.t)}</div><div class="pd">${t(info.d)}</div></div>
      <button class="pbtn">${on ? t('granted') : t('grant')}</button>`;
    row.querySelector('button').onclick = async () => {
      try { await p[info.action](); } catch (e) { alert(t('permError')); return; }
      setTimeout(refreshPerms, 600);
    };
    list.append(row);
  });
  const allOn = PERMS.filter(info => !info.optional).every(info => st[info.key]);
  $('#startBtn').disabled = !allOn;
  return st;
}

async function refreshStatus() {
  const p = Pulse(); if (!p) return;
  const cfg = await p.getConfig();
  const st = await p.getStatus();
  $('#stDevice').textContent = cfg.deviceName || '—';
  $('#stServer').textContent = cfg.serverUrl || '—';
  $('#stSync').textContent = st.lastSync ? new Date(st.lastSync).toLocaleString(lang === 'ar' ? 'ar' : 'en') : t('never');
  $('#stQueue').textContent = String(st.queueCount || 0);
  $('#iconBtn').textContent = st.iconHidden ? t('showIconBtn') : t('hideIcon');
  $('#iconBtn').dataset.hidden = st.iconHidden ? '1' : '0';
  const remoteBtn = $('#remoteBtn');
  if (remoteBtn) {
    remoteBtn.textContent = st.remoteCapable ? (t('remoteOn') + ' — ' + t('disableRemote')) : t('enableRemote');
    remoteBtn.dataset.on = st.remoteCapable ? '1' : '0';
  }
}

// ── PIN lock: used both as a full-screen gate on open, and inline before "stop" ──
function askPin(onOk) {
  show('lock');
  $('#lockErr').classList.add('hidden');
  $('#lockPin').value = '';
  $('#lockPin').focus();
  $('#lockBtn').onclick = async () => {
    const p = Pulse(); if (!p) return;
    const r = await p.verifyPin({ pin: $('#lockPin').value.trim() });
    if (r.ok) { onOk(); } else { $('#lockErr').classList.remove('hidden'); $('#lockPin').value = ''; }
  };
}

async function setupPin() {
  show('pinSetup');
  $('#newPin').value = ''; $('#confirmPinInput').value = ''; $('#pinSetupErr').classList.add('hidden');
  $('#pinSetupBtn').onclick = async () => {
    const p = Pulse(); if (!p) return;
    const a = $('#newPin').value.trim(), b = $('#confirmPinInput').value.trim();
    const err = $('#pinSetupErr');
    if (!/^\d{4,6}$/.test(a)) { err.textContent = t('pinLength'); err.classList.remove('hidden'); return; }
    if (a !== b) { err.textContent = t('pinMismatch'); err.classList.remove('hidden'); return; }
    await p.setPin({ pin: a });
    routeAfterConsent();
  };
}

async function routeAfterConsent() {
  const p = Pulse(); const cfg = p ? await p.getConfig() : {};
  if (cfg && cfg.serverUrl) {
    show(cfg.enabled ? 'status' : 'perms');
    if (!cfg.enabled) refreshPerms(); else refreshStatus();
  } else {
    show('enroll');
  }
}

async function init() {
  paint();
  $('#langBtn').onclick = () => { lang = lang === 'ar' ? 'en' : 'ar'; paint(); refreshPerms(); };
  $('#consentChk').onchange = e => { $('#consentNext').disabled = !e.target.checked; };
  $('#consentNext').onclick = async () => {
    const p = Pulse(); if (p) await p.setConsented();
    const has = p ? (await p.hasPin()).value : false;
    if (!has) setupPin(); else routeAfterConsent();
  };

  $('#enrollBtn').onclick = async () => {
    const p = Pulse(); if (!p) return;
    const serverUrl = $('#serverUrl').value.trim().replace(/\/+$/, '');
    const code = $('#enrollCode').value.trim();
    $('#enrollErr').classList.add('hidden');
    if (!serverUrl || !code) return;
    $('#enrollBtn').disabled = true;
    try {
      await p.enroll({ serverUrl, code });
      show('perms'); refreshPerms();
    } catch (e) {
      $('#enrollErr').textContent = t('invalidCode');
      $('#enrollErr').classList.remove('hidden');
    } finally { $('#enrollBtn').disabled = false; }
  };

  $('#startBtn').onclick = async () => {
    const p = Pulse(); if (!p) return;
    await p.start();
    show('status'); refreshStatus();
  };
  $('#permsBtn').onclick = () => { show('perms'); refreshPerms(); };
  $('#iconBtn').onclick = async () => {
    const p = Pulse(); if (!p) return;
    const hidden = $('#iconBtn').dataset.hidden === '1';
    if (hidden) { await p.showIcon(); }
    else { if (!confirm(t('hideConfirm'))) return; await p.hideIcon(); }
    refreshStatus();
  };
  $('#syncNowBtn').onclick = async () => { const p = Pulse(); if (p) { await p.syncNow(); setTimeout(refreshStatus, 1200); } };
  $('#remoteBtn').onclick = async () => {
    const p = Pulse(); if (!p) return;
    const on = $('#remoteBtn').dataset.on === '1';
    if (on) { await p.stopScreenCapture(); refreshStatus(); return; }
    try { await p.requestScreenCapture(); } catch (e) { alert(t('remoteDenied')); }
    refreshStatus();
  };
  $('#stopBtn').onclick = () => {
    if (!confirm(t('stopConfirm'))) return;
    askPin(async () => {
      const p = Pulse(); if (p) await p.stop();
      show('perms'); refreshPerms();
    });
  };

  // initial route, once the native bridge is ready
  const boot = async () => {
    const p = Pulse();
    if (!p) { show('consent'); return; }
    const cfg = await p.getConfig();
    const hasPin = (await p.hasPin()).value;
    const proceed = async () => {
      if (!cfg.consented) show('consent');
      else if (!hasPin) setupPin();
      else await routeAfterConsent();
    };
    if (cfg.consented && hasPin) askPin(proceed); else proceed();
  };
  if (window.Capacitor) document.addEventListener('deviceready', boot, false);
  setTimeout(boot, 300); // fallback if deviceready never fires (plain browser preview)
}
init();
})();
