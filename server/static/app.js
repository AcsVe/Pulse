/* Pulse dashboard — vanilla JS, no build step. */
(function () {
'use strict';
const K = window.PULSE;
const $ = (s, r) => (r || document).querySelector(s);
const el = (tag, attrs, html) => { const e = document.createElement(tag); if (attrs) Object.assign(e, attrs); if (html != null) e.innerHTML = html; return e; };
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Renders `label` as a clickable link to `url` when one is actually present
// (and not a bare domain with no scheme and no path, which usually isn't a
// real navigable address) — falls back to plain escaped text otherwise.
function linkify(label, url) {
  const text = esc(label || '');
  if (!text) return '—';
  if (!url) return text;
  const href = /^https?:\/\//i.test(url) ? url : `http://${url}`;
  return `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">${text}</a>`;
}

// ── i18n (Arabic default; masculine/neutral address forms only) ─────────────
const T = {
  ar: {
    today:'اليوم', yesterday:'أمس', d7:'٧ أيام', d30:'٣٠ يوماً', month:'هذا الشهر', custom:'مخصص',
    refresh:'تحديث', logout:'خروج', lang:'EN', allDevices:'كل الأجهزة', devices:'الأجهزة', done:'تم',
    exportPdf:'تصدير PDF',
    overview:'نظرة عامة', apps:'التطبيقات', browse:'التصفح', net:'الشبكة',
    screenTime:'وقت الاستخدام', avgPerDay:'المتوسط اليومي', sessions:'جلسات الاستخدام', appsUsed:'تطبيقات مستخدمة',
    sites:'صفحات مفتوحة', domains:'مواقع مختلفة', outages:'عدد الانقطاعات', outageTime:'مدة الانقطاع', availability:'نسبة الاتصال',
    prev:'السابق', vsPrev:'مقارنة بالفترة السابقة', dailyUse:'الاستخدام اليومي', hourlyUse:'الاستخدام حسب ساعات اليوم',
    outageDaily:'مدة الانقطاع اليومية (دقائق)', topApps:'أكثر التطبيقات استخداماً', topSites:'أكثر المواقع زيارة',
    current:'الحالية', previous:'السابقة',
    connected:'متصل', no_internet:'متصل بلا إنترنت', failed:'فشل اتصال', disconnected:'لا يوجد اتصال',
    app:'التطبيق', package:'الحزمة', time:'المدة', share:'النسبة', last:'آخر استخدام', change:'التغيير', avg:'متوسط الجلسة',
    prevTime:'المدة السابقة', date:'التاريخ', device:'الجهاز', domain:'الموقع', url:'الرابط', title:'العنوان', source:'المصدر',
    browser:'المتصفح', start:'البداية', end:'النهاية', duration:'المدة', kind:'الحالة', transport:'الشبكة', detail:'تفاصيل', ongoing:'مستمر',
    category:'التصنيف', catEmail:'بريد إلكتروني', catSocial:'تواصل اجتماعي', catVideo:'فيديو وبث', catGaming:'ألعاب',
    catShopping:'تسوق', catNews:'أخبار', catEducation:'تعليم', catProductivity:'إنتاجية ومكاتب', catSearch:'بحث',
    catFinance:'مالية ومصرفية', catGovernment:'حكومي', catOther:'أخرى',
    search:'بحث…', all:'الكل', selected:'المحدد', exportCsv:'تصدير CSV', del:'حذف المحدد', confirmDel:'هل تريد حذف العناصر المحددة؟ لا يمكن التراجع.',
    deleted:'تم الحذف', noData:'لا توجد بيانات في هذه الفترة', accessibility:'شريط العنوان', dns:'DNS',
    addDevice:'إضافة جهاز', deviceName:'اسم الجهاز (مثال: هاتف أحمد)', create:'إنشاء', enrollCode:'رمز الربط',
    enrollHint:'أدخل هذا الرمز في تطبيق Pulse خلال ٢٤ ساعة', newCode:'رمز جديد', status:'الحالة', lastSeen:'آخر اتصال',
    model:'الطراز', os:'أندرويد', online:'متصل الآن', offline:'غير متصل', pending:'بانتظار الربط', enrolledAt:'تاريخ الربط', name:'الاسم',
    downloadApk:'تحميل تطبيق Pulse (APK)', updated:'آخر تحديث', legendNote:'الأعمدة الرمادية = الفترة السابقة',
    h:'س', m:'د', s:'ث', sessionsN:'جلسات',
    download:'تنزيل', upload:'رفع', dataUsage:'استهلاك الإنترنت', dataHourly:'الاستهلاك حسب الساعة',
    topDataApps:'الأكثر استهلاكاً للإنترنت', websitesPie:'توزيع المواقع', connPie:'نوع الاتصال', memPie:'الذاكرة',
    liveNow:'الآن مباشرة', liveNowHint:'آخر {s} ثانية — يتحدث تلقائياً', liveNowApps:'استهلاك التطبيقات الآن',
    liveNowSites:'آخر المواقع المفتوحة', liveNowEmpty:'لا نشاط خلال هذه الفترة', liveNowDevTotal:'إجمالي الجهاز',
    rx:'تنزيل', tx:'رفع', total:'الإجمالي', ip:'عنوان IP', rename:'إعادة تسمية', save:'حفظ', cancel:'إلغاء',
  editLabel:'تعديل الاسم', settings:'الإعدادات', emailReports:'تقارير البريد الإلكتروني',
    emailEnabled:'تفعيل الإرسال', smtpHost:'خادم SMTP', smtpPort:'المنفذ', smtpUser:'اسم المستخدم / البريد',
    smtpPass:'كلمة مرور SMTP', smtpPassHint:'اتركه فارغاً للإبقاء على القيمة الحالية', useTls:'استخدام TLS',
    recipient:'البريد المستلم', frequency:'التكرار', daily:'يومي', weekly:'أسبوعي', hourUtc:'ساعة الإرسال (UTC)',
    sections:'الأقسام المرسلة', secOverview:'نظرة عامة', secApps:'التطبيقات', secData:'استهلاك الإنترنت', secNet:'الشبكة', secDevices:'الأجهزة',
    saveSettings:'حفظ الإعدادات', testSend:'إرسال تجريبي الآن', savedOk:'تم الحفظ', testSentOk:'تم الإرسال بنجاح',
    testFail:'فشل الإرسال', lastSent:'آخر إرسال',
    memUsed:'مستخدَمة', memFree:'متاحة', wifi:'واي فاي', cellular:'بيانات الجوال', unknownTransport:'غير معروف',
    hourly:'كل ساعة', unrestricted:'إرسال كل البيانات المتاحة (بلا تقييد بالأقسام)',
    perDevice:'إرسال تقرير إضافي منفصل لكل جهاز', wifiSpeed:'سرعة واي فاي', pollIntervalS:'فترة التحديث (ثوانٍ)',
    cpuUsage:'المعالج', ramUsage:'الذاكرة', netSpeed:'سرعة الشبكة',
    pollIntervalHint:'كل كم ثانية يرسل الهاتف بياناته — رقم أصغر = أقرب للفوري لكنه يستهلك بطارية أكثر',
    connectionType:'نوع الاتصال', connNone:'بلا اتصال', connUnknown:'غير معروف',
    confirmNewCode:'سيتم إنشاء رمز ربط جديد، وسيحتاج هذا الهاتف لإعادة الربط به. استمرار؟',
    accessibilityWarn:'⚠ خدمة إمكانية الوصول غير مفعّلة على هذا الهاتف — النقر والسحب لن يعملا. فعّلها من إعدادات الهاتف داخل تطبيق Pulse.',
    remoteCapableWarn:'⚠ صلاحية مشاركة الشاشة أُلغيت تلقائياً بعد آخر إعادة تشغيل لهذا الهاتف (قيد من أندرويد نفسه، ليست مشكلة في التطبيق) — افتح تطبيق Pulse على هذا الهاتف واضغط "تفعيل" مرة واحدة ليعود البث والتحكم للعمل.',
    remoteCapableBadge:'يحتاج إعادة تفعيل',
    mailTransport:'إعدادات الإرسال', provider:'طريقة الإرسال', providerSmtp:'SMTP', providerGraph:'Microsoft Graph',
    graphTenantId:'معرّف المستأجر (Tenant ID)', graphClientId:'معرّف التطبيق (Client ID)',
    graphClientSecret:'سر التطبيق (Client Secret)', graphClientSecretHint:'اتركه فارغاً للإبقاء على القيمة الحالية',
    graphSender:'البريد المُرسِل (UPN)', testRecipient:'بريد الاختبار',
    reportSchedules:'جلسات إرسال التقارير', addSchedule:'إضافة جلسة', editSchedule:'تعديل الجلسة',
    scheduleName:'اسم الجلسة (اختياري)', localTime:'الوقت (بتوقيت السيرفر المحلي)', once:'لمرة واحدة',
    onceDate:'التاريخ', weekday:'يوم الأسبوع', enabledQ:'مفعّلة', devicesFilter:'الأجهزة المشمولة (فارغ = الكل)',
    edit:'تعديل', add:'إضافة', update:'تحديث', nameCol:'الاسم', timeCol:'الوقت', statusCol:'الحالة',
    on_:'مفعّلة', off_:'متوقفة', mon:'إثنين', tue:'ثلاثاء', wed:'أربعاء', thu:'خميس', fri:'جمعة', sat:'سبت', sun:'أحد',
    remote:'تحكم عن بعد', remoteStart:'بدء التحكم عن بعد', remoteStop:'إيقاف', remoteWaiting:'بانتظار أول صورة من الهاتف…',
    remoteLost:'انقطع الاتصال بالهاتف — تأكد أنه متصل بالإنترنت وأن التحكم عن بعد ما زال مفعّلاً عليه',
    remoteStale:'الصورة لا تتحدث حالياً — جارٍ المحاولة',
    remoteBack:'رجوع', remoteHome:'الرئيسية', remoteRecents:'الأخيرة', remoteSendText:'إرسال نص',
    remoteTextPh:'اكتب نصاً لإرساله إلى الحقل المُركَّز عليه في الهاتف', remoteHint:'انقر على الصورة للنقر على الهاتف. اسحب للتمرير.',
    remoteZoomIn:'تكبير', remoteZoomOut:'تصغير', remoteClose:'إغلاق', remoteApps:'التطبيقات', remoteFullscreen:'ملء الشاشة',
    remoteAppsSearch:'ابحث عن تطبيق…', remoteAppsLoading:'جارٍ جلب قائمة التطبيقات من الهاتف…',
    remoteAppsEmpty:'لا توجد تطبيقات — جرّب فتح لوحة التحكم مرة أخرى بعد قليل.', remoteAppsNone:'لا نتائج',
    remoteLaunch:'فتح', remoteCloseApp:'إغلاق التطبيق',
    remoteCloseHint:'"إغلاق" يُرجع الهاتف للشاشة الرئيسية ثم يوقف العملية الخلفية لذلك التطبيق — يماثل سحبه من قائمة الأخيرة، وليس إغلاقاً قسرياً مضموناً مثل زر النظام (لا تسمح أندرويد لأي تطبيق عادي بذلك).',
    remoteOffline:'لا يمكن التحكم عن بعد بجهاز غير متصل',
    remoteKeyboard:'لوحة المفاتيح', remoteRightClick:'كليك يمين (للنقرة القادمة)',
    remoteRightClickHint:'كليك يمين: اضغط بإصبعين معاً، أو فعّل 🖱️ ثم اضغط بالمكان المطلوب',
    users:'المستخدمون', addUser:'إضافة مستخدم', username:'اسم المستخدم', password:'كلمة المرور',
    role:'الصلاحية', roleSuperadmin:'مدير كامل', roleAdmin:'مدير', roleViewer:'مشاهد فقط',
    deviceAccess:'الأجهزة المتاحة', active:'نشِط', inactive:'موقوف', resetPassword:'كلمة مرور جديدة',
    changeRole:'تعديل الصلاحية/الأجهزة', newPassword:'كلمة المرور الجديدة',
    usernamePasswordRequired:'اسم المستخدم وكلمة المرور مطلوبان', username_taken:'اسم المستخدم مُستخدَم',
    password_too_short:'كلمة المرور قصيرة جداً (٦ أحرف فأكثر)', bad_role:'صلاحية غير صحيحة',
    last_superadmin:'لا يمكن ترك النظام بلا مدير كامل واحد على الأقل',
    cannot_delete_self:'لا يمكنك حذف حسابك الخاص', cannot_deactivate_self:'لا يمكنك إيقاف حسابك الخاص',
    deviceIdsHint:'أدخل أرقام الأجهزة مفصولة بفواصل، أو اتركه فارغاً للسماح بكل الأجهزة',
    roleUpdated:'تم التحديث',
  },
  en: {
    today:'Today', yesterday:'Yesterday', d7:'7 days', d30:'30 days', month:'This month', custom:'Custom',
    refresh:'Refresh', logout:'Logout', lang:'عربي', allDevices:'All devices', devices:'Devices', done:'Done',
    exportPdf:'Export PDF',
    overview:'Overview', apps:'Apps', browse:'Browsing', net:'Network',
    screenTime:'Screen time', avgPerDay:'Daily average', sessions:'Usage sessions', appsUsed:'Apps used',
    sites:'Pages opened', domains:'Distinct sites', outages:'Outages', outageTime:'Outage time', availability:'Connectivity',
    prev:'Previous', vsPrev:'vs previous period', dailyUse:'Daily usage', hourlyUse:'Usage by hour of day',
    outageDaily:'Daily outage time (minutes)', topApps:'Most used apps', topSites:'Most visited sites',
    current:'Current', previous:'Previous',
    connected:'Connected', no_internet:'Connected, no internet', failed:'Connection failed', disconnected:'No connection',
    app:'App', package:'Package', time:'Time', share:'Share', last:'Last used', change:'Change', avg:'Avg session',
    prevTime:'Previous time', date:'Date', device:'Device', domain:'Site', url:'URL', title:'Title', source:'Source',
    browser:'Browser', start:'Start', end:'End', duration:'Duration', kind:'State', transport:'Network', detail:'Detail', ongoing:'Ongoing',
    category:'Category', catEmail:'Email', catSocial:'Social media', catVideo:'Video & streaming', catGaming:'Gaming',
    catShopping:'Shopping', catNews:'News', catEducation:'Education', catProductivity:'Productivity', catSearch:'Search',
    catFinance:'Finance & banking', catGovernment:'Government', catOther:'Other',
    search:'Search…', all:'All', selected:'Selected', exportCsv:'Export CSV', del:'Delete selected', confirmDel:'Delete the selected items? This cannot be undone.',
    deleted:'Deleted', noData:'No data in this period', accessibility:'Address bar', dns:'DNS',
    addDevice:'Add device', deviceName:'Device name (e.g. Ahmed phone)', create:'Create', enrollCode:'Enrollment code',
    enrollHint:'Enter this code in the Pulse app within 24 hours', newCode:'New code', status:'Status', lastSeen:'Last seen',
    model:'Model', os:'Android', online:'Online', offline:'Offline', pending:'Awaiting enrollment', enrolledAt:'Enrolled', name:'Name',
    downloadApk:'Download the Pulse app (APK)', updated:'Updated', legendNote:'Grey bars = previous period',
    h:'h', m:'m', s:'s', sessionsN:'Sessions',
    download:'Download', upload:'Upload', dataUsage:'Data Usage', dataHourly:'Usage by hour',
    topDataApps:'Heaviest data users', websitesPie:'Sites breakdown', connPie:'Connection type', memPie:'Memory',
    liveNow:'Live now', liveNowHint:'Last {s}s — updates automatically', liveNowApps:'App data usage right now',
    liveNowSites:'Recently opened sites', liveNowEmpty:'No activity in this window', liveNowDevTotal:'Device total',
    rx:'Download', tx:'Upload', total:'Total', ip:'IP address', rename:'Rename', save:'Save', cancel:'Cancel',
  editLabel:'Edit name', settings:'Settings', emailReports:'Email reports',
    emailEnabled:'Enable sending', smtpHost:'SMTP host', smtpPort:'Port', smtpUser:'Username / email',
    smtpPass:'SMTP password', smtpPassHint:'Leave blank to keep the current value', useTls:'Use TLS',
    mailTransport:'Mail transport', provider:'Send via', providerSmtp:'SMTP', providerGraph:'Microsoft Graph',
    graphTenantId:'Tenant ID', graphClientId:'Client ID', graphClientSecret:'Client secret',
    graphClientSecretHint:'Leave blank to keep the current value', graphSender:'Sender mailbox (UPN)',
    testRecipient:'Test recipient', reportSchedules:'Report sending sessions', addSchedule:'Add session',
    editSchedule:'Edit session', scheduleName:'Session name (optional)', localTime:'Time (server local time)',
    once:'Once', onceDate:'Date', weekday:'Weekday', enabledQ:'Enabled', devicesFilter:'Devices included (empty = all)',
    edit:'Edit', add:'Add', update:'Update', nameCol:'Name', timeCol:'Time', statusCol:'Status',
    on_:'Enabled', off_:'Disabled', mon:'Mon', tue:'Tue', wed:'Wed', thu:'Thu', fri:'Fri', sat:'Sat', sun:'Sun',
    recipient:'Recipient email', frequency:'Frequency', daily:'Daily', weekly:'Weekly', hourUtc:'Send hour (UTC)',
    sections:'Sections to send', secOverview:'Overview', secApps:'Apps', secData:'Data Usage', secNet:'Network', secDevices:'Devices',
    saveSettings:'Save settings', testSend:'Send test now', savedOk:'Saved', testSentOk:'Sent successfully',
    testFail:'Send failed', lastSent:'Last sent',
    memUsed:'Used', memFree:'Free', wifi:'Wi-Fi', cellular:'Cellular', unknownTransport:'Unknown',
    hourly:'Hourly', unrestricted:'Send all available data (ignore section picker)',
    perDevice:'Also send a separate report per device', wifiSpeed:'Wi-Fi speed', pollIntervalS:'Update interval (seconds)',
    cpuUsage:'CPU', ramUsage:'RAM', netSpeed:'Network speed',
    pollIntervalHint:'How often the phone sends its data — lower = closer to real-time but uses more battery',
    connectionType:'Connection type', connNone:'No connection', connUnknown:'Unknown',
    confirmNewCode:'This creates a new enrollment code, and the phone will need to re-enroll with it. Continue?',
    accessibilityWarn:'⚠ Accessibility service is not enabled on this phone — taps and swipes will not work. Enable it from the phone\'s settings inside the Pulse app.',
    remoteCapableWarn:'⚠ Screen-sharing permission was automatically revoked after this phone\'s last reboot (an Android platform rule, not an app bug) — open the Pulse app on this phone and tap "Start" once to bring the live screen and remote control back.',
    remoteCapableBadge:'Needs re-enabling',
    remote:'Remote control', remoteStart:'Start remote control', remoteStop:'Stop', remoteWaiting:'Waiting for the first frame from the phone…',
    remoteLost:"Lost contact with the phone — check that it's online and remote control is still enabled on it",
    remoteStale:"Picture isn't updating right now — retrying",
    remoteBack:'Back', remoteHome:'Home', remoteRecents:'Recents', remoteSendText:'Send text',
    remoteTextPh:'Type text to send to the focused field on the phone', remoteHint:'Click the image to tap on the phone. Drag to swipe.',
    remoteZoomIn:'Zoom in', remoteZoomOut:'Zoom out', remoteClose:'Close', remoteApps:'Apps', remoteFullscreen:'Fullscreen',
    remoteAppsSearch:'Search for an app…', remoteAppsLoading:'Fetching the app list from the phone…',
    remoteAppsEmpty:'No apps yet — try reopening remote control in a moment.', remoteAppsNone:'No matches',
    remoteLaunch:'Open', remoteCloseApp:'Close app',
    remoteCloseHint:'"Close" sends the phone home then kills that app\'s background process — the same as swiping it off Recents, not a guaranteed force-stop like the system Settings button (no normal app is allowed to do that on Android).',
    remoteOffline:"Can't remote-control an offline device",
    remoteKeyboard:'Keyboard', remoteRightClick:'Right-click (next tap)',
    remoteRightClickHint:'Right-click: tap with two fingers together, or turn on 🖱️ then tap where you want',
    users:'Users', addUser:'Add user', username:'Username', password:'Password',
    role:'Role', roleSuperadmin:'Full admin', roleAdmin:'Admin', roleViewer:'Viewer only',
    deviceAccess:'Device access', active:'Active', inactive:'Inactive', resetPassword:'Reset password',
    changeRole:'Edit role/devices', newPassword:'New password',
    usernamePasswordRequired:'Username and password are required', username_taken:'Username already taken',
    password_too_short:'Password too short (6+ characters)', bad_role:'Invalid role',
    last_superadmin:'The system must keep at least one full admin',
    cannot_delete_self:"You can't delete your own account", cannot_deactivate_self:"You can't deactivate your own account",
    deviceIdsHint:'Enter device IDs separated by commas, or leave empty for all devices',
    roleUpdated:'Updated',
  }
};
let lang = (function(){ try { return localStorage.getItem('pulseLang') || 'ar'; } catch(e){ return 'ar'; } })();
const t = k => (T[lang] && T[lang][k]) || k;
function setLang(l) {
  lang = l; try { localStorage.setItem('pulseLang', l); } catch(e){}
  document.documentElement.lang = l; document.documentElement.dir = l === 'ar' ? 'rtl' : 'ltr';
}

// ── formatting ────────────────────────────────────────────────────────────
const pad = n => String(n).padStart(2, '0');
function fmtDur(ms) {
  if (ms == null) return '—';
  let s = Math.round(ms / 1000);
  if (s < 60) return s + t('s');
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}${t('h')} ${pad(m)}${t('m')}` : `${m}${t('m')}`;
}
function fmtTs(ms) {
  if (!ms) return '—';
  const d = new Date(ms);
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
const fmtNum = n => (n == null ? '—' : Math.round(n).toLocaleString(lang === 'ar' ? 'en-US' : 'en-US'));
const fmtPct = n => (n == null ? '—' : n.toFixed(1) + '%');
function fmtBytes(n) {
  if (n == null) return '—';
  if (n < 1024) return n + ' B';
  const units = ['KB', 'MB', 'GB', 'TB']; let u = -1; let v = n;
  do { v /= 1024; u++; } while (v >= 1024 && u < units.length - 1);
  return v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2) + ' ' + units[u];
}
function fmtVal(v, unit) { return unit === 'ms' ? fmtDur(v) : unit === 'pct' ? fmtPct(v) : unit === 'bytes' ? fmtBytes(v) : fmtNum(v); }
function fmtKbps(v) {
  if (v == null) return '—';
  return v >= 1024 ? (v / 1024).toFixed(1) + ' Mbps' : Math.round(v) + ' Kbps';
}
const KIND_COLOR = { connected:'var(--k-connected)', no_internet:'var(--k-no_internet)', failed:'var(--k-failed)', disconnected:'var(--k-disconnected)' };
const kindBadge = k => `<span class="badge" style="background:${KIND_COLOR[k] || '#888'}">${esc(t(k))}</span>`;

// ── state ─────────────────────────────────────────────────────────────────
const S = { period: 'today', from: null, to: null, devices: null /* null = all */, tab: 'overview', allDevices: [], tables: {}, lastLoad: 0 };
let ME = { role: 'viewer', deviceIds: [] };
const canWrite = () => ME.role === 'admin' || ME.role === 'superadmin';
const isSuper = () => ME.role === 'superadmin';
const TZ = -new Date().getTimezoneOffset();

function dayStart(d) { return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(); }
function computeRange() {
  const now = new Date(), today = dayStart(now), DAY = 86400000;
  const p = S.period;
  if (p === 'today') return [today, today + DAY];
  if (p === 'yesterday') return [today - DAY, today];
  if (p === 'd30') return [today - 29 * DAY, today + DAY];
  if (p === 'month') return [new Date(now.getFullYear(), now.getMonth(), 1).getTime(), today + DAY];
  if (p === 'custom' && S.from && S.to) return [S.from, S.to];
  return [today - 6 * DAY, today + DAY];
}
function qs(extra) {
  const [a, b] = computeRange();
  const p = new URLSearchParams({ from: a, to: b, tz: TZ });
  if (S.devices) p.set('devices', S.devices.join(','));
  if (K.key) p.set('key', K.key);
  if (extra) Object.entries(extra).forEach(([k, v]) => p.set(k, v));
  return p.toString();
}
async function api(path, opt) {
  const r = await fetch(path, opt);
  if (r.status === 401) { location.href = '/login'; throw new Error('401'); }
  return r.json();
}
const jpost = (path, body, method) => api(path, { method: method || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
function toast(msg) { const e = $('#toast'); e.textContent = msg; e.classList.add('on'); setTimeout(() => e.classList.remove('on'), 2200); }

// ── charts (hand-rolled SVG) ──────────────────────────────────────────────
function niceMax(v) { if (v <= 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(v))); return Math.ceil(v / p) * p; }
// Axis text used to be a flat font-size:22 regardless of how many bars/ticks
// were on screen — fine for a week of daily bars, but with 30+ days or all 24
// hours the labels overlapped into an unreadable smear, while a 3-4 point
// chart looked unnecessarily small. Scale the axis font down as the point
// count grows (and let it grow back up when there are only a few), so each
// chart's text is sized to what's actually on it.
// Was 24/20/16/13 — a chart with very few bars (a single "Today" bar in
// Daily usage, n=1) blew its X-axis label up to 24px, which read as
// wildly oversized next to the now-fixed 15px Y-axis labels (yfs below)
// and next to a busier chart like Usage by hour of day (n=24, 13px).
// Kept shrinking for genuinely crowded axes, just without ballooning the
// other end for one or two bars that were never at risk of overlapping.
function axisFont(n) { return n <= 8 ? 16 : n <= 16 ? 15 : n <= 31 ? 14 : 13; }
function barChart(cur, prev, { h = 210, unit = 'ms' } = {}) {
  const n = cur.length; if (!n) return `<div class="empty">${t('noData')}</div>`;
  // W is deliberately smaller than the typical card width (not 1:1 with
  // pixels): the SVG scales to fill its container via viewBox, and that
  // same scale factor applies to font-size, so a narrower W means more
  // pixels per chart unit — i.e. bigger, readable axis text — even when
  // this chart lands in the 2-column grid at ~380-450px wide.
  const W = 560, padL = 54, padB = 26, padT = 8, innerW = W - padL - 6, innerH = h - padB - padT;
  const vals = cur.map(d => d.v).concat((prev || []).map(d => d.v));
  const max = niceMax(Math.max(1, ...vals));
  const slot = innerW / n, bw = Math.max(2, Math.min(34, slot * 0.62));
  const rtl = document.documentElement.dir === 'rtl';
  const X = i => rtl ? W - 6 - (i + 0.5) * slot : padL + (i + 0.5) * slot;
  // Y-axis value labels used to share axisFont(n) with the X-axis category
  // labels — so a 1-bar chart (e.g. Daily usage showing a single day) got
  // much bigger numbers than a 24-bar one (Usage by hour of day), even
  // though both show the same kind of number on the same card grid. The
  // value axis now always renders at one fixed size; only the X-axis
  // category labels still shrink as bar count grows (they're the ones that
  // actually risk overlapping/crowding).
  const yfs = 15;
  const fs = axisFont(n);
  let g = '';
  for (let i = 0; i <= 4; i++) {
    const y = padT + innerH - innerH * i / 4, val = max * i / 4;
    g += `<line x1="${padL}" x2="${W-6}" y1="${y}" y2="${y}" stroke="#d6e1e9" stroke-dasharray="3 4" opacity=".7"/>`;
    g += `<text x="${rtl ? W - 0 : 0}" text-anchor="${rtl ? 'end' : 'start'}" y="${y+4}" font-size="${yfs}">${esc(fmtVal(val, unit))}</text>`;
  }
  cur.forEach((d, i) => {
    const bh = innerH * d.v / max, x = X(i);
    if (prev && prev[i]) {
      const ph = innerH * prev[i].v / max;
      g += `<rect class="chart-hit" x="${x - bw/2 - 3}" y="${padT + innerH - ph}" width="${bw}" height="${Math.max(0, ph)}" rx="2" fill="#aebfcc" opacity=".8" data-tip="${esc(prev[i].label)} — ${esc(fmtVal(prev[i].v, unit))}"><title>${esc(prev[i].label)} — ${esc(fmtVal(prev[i].v, unit))}</title></rect>`;
    }
    g += `<rect class="chart-hit" x="${x - bw/2 + (prev ? 3 : 0)}" y="${padT + innerH - bh}" width="${bw}" height="${Math.max(0, bh)}" rx="2" fill="var(--teal)" data-tip="${esc(d.label)} — ${esc(fmtVal(d.v, unit))}"><title>${esc(d.label)} — ${esc(fmtVal(d.v, unit))}</title></rect>`;
    if (n <= 16 || i % Math.ceil(n / 14) === 0) g += `<text x="${x}" y="${h - 6}" text-anchor="middle" font-size="${fs}">${esc(d.short)}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${h}" width="100%" role="img">${g}</svg>`;
}
function stackedChart(days) {
  const n = days.length; if (!n) return `<div class="empty">${t('noData')}</div>`;
  const rows = days.map(d => ({ label: d.day, short: d.day.slice(5), parts: ['no_internet','failed','disconnected'].map(k => ({ k, v: d.net[k] / 60000 })) }));
  const W = 560, h = 210, padL = 54, padB = 26, padT = 8, innerW = W - padL - 6, innerH = h - padB - padT;
  const max = niceMax(Math.max(1, ...rows.map(r => r.parts.reduce((a, p) => a + p.v, 0))));
  const slot = innerW / n, bw = Math.max(2, Math.min(34, slot * 0.62));
  const rtl = document.documentElement.dir === 'rtl';
  const X = i => rtl ? W - 6 - (i + 0.5) * slot : padL + (i + 0.5) * slot;
  const yfs = 15; // fixed size, same reasoning as barChart's yfs — see there
  const fs = axisFont(n);
  let g = '';
  for (let i = 0; i <= 4; i++) {
    const y = padT + innerH - innerH * i / 4;
    g += `<line x1="${padL}" x2="${W-6}" y1="${y}" y2="${y}" stroke="#d6e1e9" stroke-dasharray="3 4" opacity=".7"/>`;
    // Match barChart's axis labels (e.g. "Usage by hour of day") instead of a
    // bare unlabelled number — minutes here, same unit the legend/tooltips
    // below already use, so the axis stops being the odd one out.
    g += `<text x="${rtl ? W : 0}" text-anchor="${rtl ? 'end' : 'start'}" y="${y+4}" font-size="${yfs}">${Math.round(max * i / 4)}${esc(t('m'))}</text>`;
  }
  rows.forEach((r, i) => {
    let y = padT + innerH;
    r.parts.forEach(p => {
      const bh = innerH * p.v / max; y -= bh;
      if (bh > 0) g += `<rect class="chart-hit" x="${X(i) - bw/2}" y="${y}" width="${bw}" height="${bh}" fill="${KIND_COLOR[p.k]}" data-tip="${esc(r.label)} — ${esc(t(p.k))}: ${Math.round(p.v)}${esc(t('m'))}"><title>${esc(r.label)} — ${esc(t(p.k))}: ${Math.round(p.v)}${t('m')}</title></rect>`;
    });
    if (n <= 16 || i % Math.ceil(n / 14) === 0) g += `<text x="${X(i)}" y="${h - 6}" text-anchor="middle" font-size="${fs}">${esc(r.short)}</text>`;
  });
  const legend = ['no_internet','failed','disconnected'].map(k => `<span><i style="background:${KIND_COLOR[k]}"></i>${esc(t(k))}</span>`).join('');
  return `<svg viewBox="0 0 ${W} ${h}" width="100%" role="img">${g}</svg><div class="legend">${legend}</div>`;
}
function barRows(items, max, fmt) {
  return items.map(it => `
    <div class="barrow"><div class="nm" title="${esc(it.name)}">${esc(it.name)}</div>
      <div class="bar"><b style="width:${max ? (it.v / max * 100).toFixed(1) : 0}%"></b>${it.p ? `<b class="p" style="width:${max ? (it.p / max * 100).toFixed(1) : 0}%"></b>` : ''}</div>
      <div class="vv">${esc(fmt(it))}</div></div>`).join('') || `<div class="empty">${t('noData')}</div>`;
}

const PIE_COLORS = ['#1ba39c', '#3b82c4', '#e0a62b', '#d6577a', '#7e6fd1', '#5fb87a', '#c4783b', '#999'];
function pieChart(parts, fmt) {
  const total = parts.reduce((a, p) => a + p.v, 0);
  if (!total) return `<div class="empty">${t('noData')}</div>`;
  const cx = 90, cy = 90, r = 78;
  let angle = -90, paths = '';
  parts.forEach((p, i) => {
    if (p.v <= 0) return;
    const frac = p.v / total;
    const a0 = angle, a1 = angle + frac * 360;
    angle = a1;
    const toXY = a => [cx + r * Math.cos(a * Math.PI / 180), cy + r * Math.sin(a * Math.PI / 180)];
    const [x0, y0] = toXY(a0), [x1, y1] = toXY(a1);
    const large = (a1 - a0) > 180 ? 1 : 0;
    const d = frac >= 0.999 ? `M${cx},${cy-r} A${r},${r} 0 1,1 ${cx-0.01},${cy-r} Z`
      : `M${cx},${cy} L${x0},${y0} A${r},${r} 0 ${large},1 ${x1},${y1} Z`;
    const tip = `${esc(p.name)} — ${esc(fmt ? fmt(p.v) : p.v)} (${(frac*100).toFixed(1)}%)`;
    paths += `<path class="chart-hit" d="${d}" fill="${p.color || PIE_COLORS[i % PIE_COLORS.length]}" data-tip="${tip}"><title>${tip}</title></path>`;
  });
  const legend = parts.filter(p => p.v > 0).map((p, i) => `<span><i style="background:${p.color || PIE_COLORS[i % PIE_COLORS.length]}"></i>${esc(p.name)} — ${esc(fmt ? fmt(p.v) : p.v)}</span>`).join('');
  return `<div class="pie-wrap"><svg viewBox="0 0 180 180" width="180" height="180">${paths}</svg><div class="legend col">${legend}</div></div>`;
}

// Bars/stacks/pie slices already carried a native SVG <title> (a real
// tooltip, but slow to appear and styled by the OS, not the page — easy to
// miss, which is what "hoover the mouse = alt text for value" was flagging).
// This adds an instant, styled tooltip that tracks the cursor instead,
// without touching every chart function individually: one delegated
// listener on #main reads the same value off each hit-target's data-tip.
let chartTipEl = null;
function initChartTooltip() {
  if (chartTipEl) return; // only wire this up once
  chartTipEl = el('div', { id: 'chartTip', className: 'chart-tip hidden' });
  document.body.appendChild(chartTipEl);
  const main = $('#main');
  main.addEventListener('mousemove', e => {
    const hit = e.target.closest('.chart-hit');
    if (!hit) { chartTipEl.classList.add('hidden'); return; }
    chartTipEl.textContent = hit.dataset.tip || '';
    chartTipEl.classList.remove('hidden');
    const pad = 14, vw = window.innerWidth, vh = window.innerHeight;
    const w = chartTipEl.offsetWidth, hgt = chartTipEl.offsetHeight;
    chartTipEl.style.left = Math.max(4, Math.min(e.clientX + pad, vw - w - 4)) + 'px';
    chartTipEl.style.top = Math.max(4, Math.min(e.clientY + pad, vh - hgt - 4)) + 'px';
  });
  main.addEventListener('mouseleave', () => chartTipEl.classList.add('hidden'));
}

// ── overview ──────────────────────────────────────────────────────────────
function deltaChip(k) {
  if (k.delta == null) return `<span class="delta none">—</span>`;
  const up = k.delta > 0.05, dn = k.delta < -0.05;
  let cls = 'neutral';
  if (k.tone === 'good') cls = up ? 'good' : dn ? 'bad' : 'neutral';
  else if (k.tone === 'bad') cls = up ? 'bad' : dn ? 'good' : 'neutral';
  const arrow = up ? '▲' : dn ? '▼' : '■';
  return `<span class="delta ${cls}">${arrow} ${Math.abs(k.delta).toFixed(0)}%</span>`;
}
async function renderOverview() {
  const d = await api('/api/overview?' + qs());
  // The 8s auto-refresh re-fetches this unconditionally, and between polls
  // the answer is very often byte-for-byte the same (nothing changed in the
  // underlying data yet) — rebuilding and replacing every chart's innerHTML
  // anyway was the main source of the periodic full-dashboard flicker, so
  // skip the DOM rebuild entirely when the response is identical to what's
  // already on screen. renderLiveNow() still refreshes on its own cadence
  // below regardless, since that card is meant to visibly tick.
  const sig = JSON.stringify(d);
  if (sig === S._overviewSig && $('#liveNowCard')) { renderLiveNow(); return; }
  S._overviewSig = sig;
  const kp = d.kpis.map(k => `<div class="kpi ${k.tone === 'bad' ? 'bad' : k.tone === 'good' ? 'good' : ''}">
      <div class="l">${esc(t(k.key))}</div><div class="v">${esc(fmtVal(k.value, k.unit))}</div>
      <div class="d">${deltaChip(k)}<span class="prev">${esc(t('prev'))}: ${esc(fmtVal(k.prev, k.unit))}</span></div></div>`).join('');
  const dayShort = s => s.slice(5);
  const cur = d.daily.map(x => ({ v: x.ms, label: x.day, short: dayShort(x.day) }));
  const prev = d.prevDaily.length === d.daily.length ? d.prevDaily.map(x => ({ v: x.ms, label: x.day })) : null;
  const hrs = d.hourly.map((v, i) => ({ v, label: pad(i) + ':00', short: pad(i) }));
  const maxApp = Math.max(1, ...d.topApps.map(a => Math.max(a.ms, a.prevMs)));
  const maxDom = Math.max(1, ...d.topDomains.map(a => Math.max(a.count, a.prev)));
  const netTot = Object.values(d.net.ms).reduce((a, b) => a + b, 0);
  const netBar = netTot ? ['connected','no_internet','failed','disconnected'].map(k =>
      `<div title="${esc(t(k))}: ${esc(fmtDur(d.net.ms[k]))}" style="flex:${d.net.ms[k]};background:${KIND_COLOR[k]};min-width:${d.net.ms[k] ? 3 : 0}px"></div>`).join('') : '';
  const netLegend = ['connected','no_internet','failed','disconnected'].map(k =>
      `<span><i style="background:${KIND_COLOR[k]}"></i>${esc(t(k))}: ${esc(fmtDur(d.net.ms[k]))} (${d.net.count[k]})</span>`).join('');

  // data-usage hourly line (rx/tx) and top data apps
  const dataHrs = (d.hourlyData || []).map((h, i) => ({ v: (h.rx||0) + (h.tx||0), label: pad(i) + ':00', short: pad(i) }));
  const maxDataApp = Math.max(1, ...(d.topDataApps || []).map(a => a.rx + a.tx));
  // transport (wifi/cellular) pie
  const transLabel = k => ({ wifi: t('wifi'), cellular: t('cellular') })[k] || (k === 'unknown' ? t('unknownTransport') : k);
  const transParts = Object.entries(d.net.transportMs || {}).map(([k, v]) => ({ name: transLabel(k), v }));
  // websites pie (reuse topDomains)
  const siteParts = d.topDomains.map(x => ({ name: x.domain, v: x.count }));

  $('#main').innerHTML = `
    <div class="card live-card" id="liveNowCard"></div>
    <div class="grid kpis" style="margin-bottom:16px">${kp}</div>
    <div class="grid cols2">
      <div class="card"><h3>${t('dailyUse')}</h3>${barChart(cur, prev)}<div class="legend"><span><i style="background:var(--teal)"></i>${t('current')}</span><span><i style="background:#aebfcc"></i>${t('previous')}</span></div></div>
      <div class="card"><h3>${t('hourlyUse')}</h3>${barChart(hrs, null)}</div>
      <div class="card"><h3>${t('connPie')}</h3>${pieChart(transParts, v => fmtDur(v))}</div>
      <div class="card"><h3>${t('net')}</h3>
        <div style="display:flex;height:22px;border-radius:8px;overflow:hidden;background:#e8eff4">${netBar}</div><div class="legend">${netLegend}</div>
        <h3 style="margin-top:16px">${t('outageDaily')}</h3>${stackedChart(d.daily)}</div>
      <div class="card"><h3>${t('topApps')}</h3>${barRows(d.topApps.map(a => ({ name: a.label, v: a.ms, p: a.prevMs, delta: a.delta })), maxApp, it => fmtDur(it.v))}
        <div class="legend"><span>${t('legendNote')}</span></div>
        <h3 style="margin-top:16px">${t('topSites')}</h3>${barRows(d.topDomains.map(a => ({ name: a.domain, v: a.count, p: a.prev })), maxDom, it => String(it.v))}</div>
      <div class="card"><h3>${t('dataHourly')}</h3>${barChart(dataHrs, null, { unit: 'bytes' })}
        <h3 style="margin-top:16px">${t('topDataApps')}</h3>${barRows((d.topDataApps||[]).map(a => ({ name: a.label, v: a.rx + a.tx })), maxDataApp, it => fmtBytes(it.v))}</div>
      <div class="card"><h3>${t('websitesPie')}</h3>${pieChart(siteParts, v => String(v))}</div>
    </div>`;
  renderLiveNow();
}

const LIVE_WINDOW_S = 90;
// A short, fast-refreshing feed of "what's using data / what site was just
// opened" in the last LIVE_WINDOW_S seconds — separate from the rest of
// Overview, which follows the dashboard's from/to period and 8s refresh.
// Only reflects reality once the phone's own sampling is fast too (the
// live-sync setting — see CollectorService.java); with the old fixed
// 15-minute TrafficStats polling this card would have sat empty almost
// all the time, which is why it didn't exist until that was fixed.
async function renderLiveNow() {
  const host = $('#liveNowCard');
  if (!host) return; // overview tab navigated away before this resolved
  let d;
  try { d = await api(`/api/live?window=${LIVE_WINDOW_S * 1000}&` + qs()); } catch (e) { return; }
  if ($('#liveNowCard') !== host) return; // stale response from a since-replaced card
  // This card polls every 4s (startLiveNow below) independent of the rest of
  // the dashboard, specifically so the Overview tab doesn't have to tear
  // itself down every few seconds just to keep "live" numbers moving. But
  // rebuilding *this* card's innerHTML on every one of those ticks — even
  // when the window's contents haven't actually changed, which is most
  // ticks on a quiet device — caused the same kind of flash the rest of the
  // dashboard's dedupe (see renderApps/renderData/etc.) was already fixing
  // elsewhere. Skip the DOM write when nothing changed.
  const sig = JSON.stringify(d);
  // host.innerHTML check: the Overview tab was just (re)entered and this
  // card is a freshly-emptied placeholder div — render even if the data
  // happens to match the last thing shown before the tab was left.
  if (sig === S._liveSig && host.innerHTML) return;
  S._liveSig = sig;
  const apps = d.apps || [], sites = d.sites || [];
  const dt = d.deviceTotal || { rx: 0, tx: 0 };
  // Per-app attribution needs a NetworkStatsManager per-UID query that can
  // legitimately come back empty on some OEM/Android-version combinations
  // even while the device-wide total (plain TrafficStats, no per-UID API
  // needed) keeps recording fine — this card used to show "No activity"
  // in that case regardless of real traffic. deviceTotal was already in
  // every /api/live response (and liveNowDevTotal already translated) but
  // never actually rendered here; fall back to it instead of just the
  // empty state when there's nothing to break down by app.
  const appRows = apps.length ? apps.map(a => `
    <div class="liverow"><span class="nm" title="${esc(a.label)}">${esc(a.label)}</span>
      <span class="liveval">↓${esc(fmtBytes(a.rx))} ↑${esc(fmtBytes(a.tx))}</span></div>`).join('')
    : (dt.rx || dt.tx) ? `
    <div class="liverow"><span class="nm">${esc(t('liveNowDevTotal'))}</span>
      <span class="liveval">↓${esc(fmtBytes(dt.rx))} ↑${esc(fmtBytes(dt.tx))}</span></div>`
    : `<div class="empty small">${t('liveNowEmpty')}</div>`;
  const siteRows = sites.length ? sites.map(s => `
    <div class="liverow"><span class="nm" title="${esc(s.title || s.domain)}">${esc(s.domain || s.title || '—')}</span>
      <span class="liveval muted">${esc(fmtTs(s.ts))}</span></div>`).join('')
    : `<div class="empty small">${t('liveNowEmpty')}</div>`;
  host.innerHTML = `
    <h3><span class="live-dot"></span>${t('liveNow')}
      <span class="live-sub">${t('liveNowHint').replace('{s}', LIVE_WINDOW_S)}</span></h3>
    <div class="grid cols2 live-grid">
      <div><h4>${t('liveNowApps')}</h4><div class="live-list">${appRows}</div></div>
      <div><h4>${t('liveNowSites')}</h4><div class="live-list">${siteRows}</div></div>
    </div>`;
}
// Keeps the Overview tab's "live now" feed current on its own cadence —
// independent of the general 8s dashboard refresh, which would otherwise
// tear down and rebuild the whole Overview (losing scroll position,
// flashing every chart) just to update one small card.
function startLiveNow() {
  setInterval(() => {
    if (S.tab !== 'overview' || document.hidden) return;
    renderLiveNow();
  }, 4000);
}

// ── generic table (sticky header, frozen columns, sort, select) ───────────
function makeTable(host, cfg) {
  const st = S.tables[cfg.id] || (S.tables[cfg.id] = { sortKey: cfg.sortKey, sortDir: cfg.sortDir || 'desc', q: '', sel: new Set() });
  const rows = cfg.rows;
  host.innerHTML = '';
  const bar = el('div', { className: 'toolbar' });
  const search = el('input', { type: 'search', placeholder: t('search'), value: st.q });
  const count = el('span', { className: 'count' });
  const exp = el('button', { className: 'tbtn' }, t('exportCsv'));
  bar.append(search, count, exp);
  host.append(bar);
  const selbar = el('div', { className: 'selbar' });
  host.append(selbar);
  const wrap = el('div', { className: 'tw' });
  host.append(wrap);

  const view = () => {
    let r = rows;
    if (st.q) { const q = st.q.toLowerCase(); r = r.filter(x => cfg.cols.some(c => String(c.text ? c.text(x) : x[c.k] == null ? '' : x[c.k]).toLowerCase().includes(q))); }
    const col = cfg.cols.find(c => c.k === st.sortKey);
    if (col) {
      const get = x => col.sortv ? col.sortv(x) : x[col.k];
      r = r.slice().sort((a, b) => { let av = get(a), bv = get(b); if (av == null) av = ''; if (bv == null) bv = '';
        return (av < bv ? -1 : av > bv ? 1 : 0) * (st.sortDir === 'asc' ? 1 : -1); });
    }
    return r;
  };

  function draw() {
    const r = view();
    count.textContent = `${t('all')} (${rows.length})` + (st.q ? ` · ${r.length}` : '');
    const nsel = [...st.sel].filter(id => rows.some(x => x[cfg.id_] === id)).length;
    selbar.className = 'selbar' + (nsel ? ' on' : '');
    selbar.innerHTML = `<span>${t('selected')}: ${nsel} / ${rows.length}</span>`;
    const ex2 = el('button', { className: 'tbtn' }, t('exportCsv')); ex2.onclick = () => exportCsv(true);
    selbar.append(ex2);
    if (cfg.deletable && canWrite()) { const d = el('button', { className: 'tbtn danger' }, t('del')); d.onclick = doDelete; selbar.append(d); }
    if (!r.length) { wrap.innerHTML = `<div class="empty">${t('noData')}</div>`; return; }
    // frozen columns: checkbox (0) + first `freeze` data columns; offsets accumulate widths
    const CB = 46, freeze = cfg.freeze == null ? 1 : cfg.freeze;
    const offs = []; let acc = CB;
    cfg.cols.forEach((c, i) => { offs[i] = acc; if (i < freeze) acc += (c.w || 150); });
    const fzStyle = (i, isCb) => `inset-inline-start:${isCb ? 0 : offs[i]}px;${isCb ? `min-width:${CB}px;width:${CB}px;` : `min-width:${cfg.cols[i].w || 150}px;`}`;
    const allSel = r.length && r.every(x => st.sel.has(x[cfg.id_]));
    let h = `<table><thead><tr><th class="fz ${freeze ? '' : 'edge'}" style="${fzStyle(0, true)}"><input type="checkbox" id="selAll" ${allSel ? 'checked' : ''} title="${t('all')} (${r.length})"></th>`;
    cfg.cols.forEach((c, i) => {
      const fz = i < freeze, edge = fz && i === freeze - 1;
      const si = st.sortKey === c.k ? (st.sortDir === 'asc' ? '▲' : '▼') : '⇅';
      h += `<th data-k="${c.k}" class="${fz ? 'fz' : ''} ${edge ? 'edge' : ''} ${c.num ? 'num' : ''} ${st.sortKey === c.k ? 'sorted' : ''}" style="${fz ? fzStyle(i) : ''}${!fz && c.w ? `min-width:${c.w}px;` : ''}">${esc(c.label)}<span class="si">${si}</span></th>`;
    });
    h += '</tr></thead><tbody>';
    r.forEach(x => {
      const id = x[cfg.id_], on = st.sel.has(id);
      h += `<tr class="${on ? 'sel' : ''}" data-id="${esc(id)}"><td class="fz ${freeze ? '' : 'edge'}" style="${fzStyle(0, true)}"><input type="checkbox" class="rowcb" ${on ? 'checked' : ''}></td>`;
      cfg.cols.forEach((c, i) => {
        const fz = i < freeze, edge = fz && i === freeze - 1;
        const cell = c.html ? c.html(x) : esc(c.fmt ? c.fmt(x[c.k], x) : x[c.k]);
        h += `<td class="${fz ? 'fz' : ''} ${edge ? 'edge' : ''} ${c.num ? 'num' : ''} ${c.wrap ? 'wrap' : ''}" style="${fz ? fzStyle(i) : ''}">${cell}</td>`;
      });
      h += '</tr>';
    });
    wrap.innerHTML = h + '</tbody></table>';
    const idOf = tr => { const rid = tr.dataset.id; return rows.find(x => String(x[cfg.id_]) === rid)[cfg.id_]; };
    wrap.querySelector('#selAll').onchange = e => { r.forEach(x => e.target.checked ? st.sel.add(x[cfg.id_]) : st.sel.delete(x[cfg.id_])); draw(); };
    wrap.querySelectorAll('.rowcb').forEach(cb => cb.onchange = e => { const id = idOf(e.target.closest('tr')); e.target.checked ? st.sel.add(id) : st.sel.delete(id); draw(); });
    wrap.querySelectorAll('th[data-k]').forEach(th => th.onclick = () => {
      if (st.sortKey === th.dataset.k) st.sortDir = st.sortDir === 'asc' ? 'desc' : 'asc'; else { st.sortKey = th.dataset.k; st.sortDir = 'asc'; }
      draw();
    });
  }
  function exportCsv(onlySel) {
    let r = view(); if (onlySel) r = r.filter(x => st.sel.has(x[cfg.id_]));
    const head = cfg.cols.map(c => c.label);
    const body = r.map(x => cfg.cols.map(c => c.text ? c.text(x) : c.fmt ? c.fmt(x[c.k], x) : x[c.k]));
    const q = v => '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"';
    const csv = '﻿' + [head, ...body].map(l => l.map(q).join(',')).join('\r\n');
    const a = el('a', { href: URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })), download: `pulse-${cfg.id}-${new Date().toISOString().slice(0,10)}.csv` });
    document.body.append(a); a.click(); a.remove();
  }
  async function doDelete() {
    const ids = [...st.sel].filter(id => rows.some(x => x[cfg.id_] === id));
    if (!ids.length || !confirm(t('confirmDel'))) return;
    const [a, b] = computeRange();
    const res = await jpost('/api/delete', { table: cfg.deletable, ids, from: a, to: b, devices: S.devices || [] });
    st.sel.clear(); toast(`${t('deleted')}: ${res.deleted}`); await cfg.reload();
  }
  search.oninput = () => { st.q = search.value; draw(); };
  exp.onclick = () => exportCsv(false);
  draw();
}

// ── rename helpers (app labels + device names) ─────────────────────────────
async function renameAppLabel(pkg, current, reload) {
  const v = prompt(t('editLabel') + ' — ' + pkg, current || '');
  if (v == null) return;
  await jpost('/api/app-labels', { package: pkg, label: v.trim() }, 'PUT');
  reload();
}
async function renameDevice(id, current, reload) {
  const v = prompt(t('rename'), current || '');
  if (v == null || !v.trim()) return;
  await jpost(`/api/devices/${id}`, { name: v.trim() }, 'PATCH');
  reload();
}
const labelCell = (pkg, label) => canWrite()
  ? `<span class="lbl">${esc(label)}</span><button class="editbtn" data-pkg="${esc(pkg)}" title="${esc(t('editLabel'))}">✎</button>`
  : `<span class="lbl">${esc(label)}</span>`;
// Event delegation on the stable table container — survives makeTable's re-draws (sort/search/select).
function wireLabelEdits(host, reload) {
  host.addEventListener('click', e => {
    const b = e.target.closest('.editbtn[data-pkg]');
    if (!b) return;
    e.stopPropagation();
    const pkg = b.dataset.pkg;
    const cur = b.previousElementSibling ? b.previousElementSibling.textContent : '';
    renameAppLabel(pkg, cur, reload);
  });
}
function wireDeviceRename(host, reload) {
  host.addEventListener('click', e => {
    const b = e.target.closest('.renamebtn[data-id]');
    if (!b) return;
    e.stopPropagation();
    const cur = b.previousElementSibling ? b.previousElementSibling.textContent : '';
    renameDevice(b.dataset.id, cur, reload);
  });
}
async function setPollInterval(id, current, reload) {
  const v = prompt(t('pollIntervalHint'), current || '5');
  if (v == null) return;
  const n = parseInt(v, 10);
  if (!n || n < 5) return;
  await jpost(`/api/devices/${id}`, { pollIntervalS: n }, 'PATCH');
  reload();
}
function wirePollEdit(host, reload) {
  host.addEventListener('click', e => {
    const b = e.target.closest('.pollbtn[data-id]');
    if (!b) return;
    e.stopPropagation();
    const cur = b.previousElementSibling ? b.previousElementSibling.textContent : '';
    setPollInterval(b.dataset.id, cur, reload);
  });
}

// ── tab renderers ─────────────────────────────────────────────────────────
async function renderApps() {
  const rows = await api('/api/table/apps?' + qs());
  // Same fix as Overview/Devices (see renderOverview): the 8s auto-refresh
  // was tearing down and rebuilding this whole table every tick even when
  // nothing in it had changed, which is what kept flickering on tabs other
  // than Overview/Devices even after those two were fixed — and also reset
  // the user's current sort and scroll position on every tick.
  const sig = JSON.stringify(rows);
  if (sig === S._appsSig && $('#tbl')) return;
  S._appsSig = sig;
  $('#main').innerHTML = '<div class="card" id="tbl"></div>';
  const tbl = $('#tbl');
  makeTable(tbl, { id: 'apps', id_: 'id', rows, sortKey: 'ms', deletable: 'apps', reload: renderApps, freeze: 1, cols: [
    { k: 'label', label: t('app'), w: 200, html: x => labelCell(x.package, x.label), text: x => x.label },
    { k: 'ms', label: t('time'), num: true, fmt: v => fmtDur(v), w: 110 },
    { k: 'share', label: t('share'), num: true, fmt: v => v.toFixed(1) + '%', w: 90 },
    { k: 'sessions', label: t('sessionsN'), num: true, fmt: fmtNum, w: 90 },
    { k: 'avgMs', label: t('avg'), num: true, fmt: v => fmtDur(v), w: 110 },
    { k: 'last', label: t('last'), fmt: fmtTs, w: 150 },
    { k: 'prevMs', label: t('prevTime'), num: true, fmt: v => fmtDur(v), w: 110 },
    { k: 'delta', label: t('change'), num: true, w: 100, html: x => x.delta == null ? '—' : `<span class="delta ${x.delta > 0 ? 'neutral' : 'none'}">${x.delta > 0 ? '▲' : '▼'} ${Math.abs(x.delta).toFixed(0)}%</span>`, text: x => x.delta == null ? '' : x.delta.toFixed(0) + '%' },
    { k: 'package', label: t('package'), w: 240 },
  ] });
  wireLabelEdits(tbl, renderApps);
}
async function renderData() {
  const rows = await api('/api/table/data?' + qs());
  const sig = JSON.stringify(rows);
  if (sig === S._dataSig && $('#tbl')) return;
  S._dataSig = sig;
  $('#main').innerHTML = '<div class="card" id="tbl"></div>';
  const tbl = $('#tbl');
  makeTable(tbl, { id: 'data', id_: 'id', rows, sortKey: 'total', deletable: 'data', reload: renderData, freeze: 1, cols: [
    { k: 'label', label: t('app'), w: 200,
      html: x => x.package === '__device__' ? `<span class="lbl">${esc(t('liveNowDevTotal'))}</span>` : labelCell(x.package, x.label),
      text: x => x.package === '__device__' ? t('liveNowDevTotal') : x.label },
    { k: 'rx', label: t('rx'), num: true, fmt: v => fmtBytes(v), w: 110 },
    { k: 'tx', label: t('tx'), num: true, fmt: v => fmtBytes(v), w: 110 },
    { k: 'total', label: t('total'), num: true, fmt: v => fmtBytes(v), w: 110 },
    { k: 'share', label: t('share'), num: true, fmt: v => v.toFixed(1) + '%', w: 90 },
    { k: 'package', label: t('package'), w: 240 },
  ] });
  wireLabelEdits(tbl, renderData);
}
const CAT_KEY = { email: 'catEmail', social: 'catSocial', video: 'catVideo', gaming: 'catGaming',
  shopping: 'catShopping', news: 'catNews', education: 'catEducation', productivity: 'catProductivity',
  search: 'catSearch', finance: 'catFinance', government: 'catGovernment', other: 'catOther' };
const catLabel = c => t(CAT_KEY[c] || 'catOther');
async function renderBrowse() {
  const rows = await api('/api/table/browse?' + qs());
  const sig = JSON.stringify(rows);
  if (sig === S._browseSig && $('#tbl')) return;
  S._browseSig = sig;
  $('#main').innerHTML = '<div class="card" id="tbl"></div>';
  makeTable($('#tbl'), { id: 'browse', id_: 'id', rows, sortKey: 'ts', deletable: 'browse', reload: renderBrowse, freeze: 1, cols: [
    // DNS-sourced rows only ever capture the domain being looked up, never
    // a full URL (the device can see a DNS query, not the page it was
    // for) — falling back to the bare domain as the link target still
    // makes every row clickable instead of only the accessibility-sourced
    // ones that happen to have a full url.
    { k: 'domain', label: t('domain'), w: 200, html: x => linkify(x.domain, x.url || x.domain), text: x => x.domain },
    { k: 'category', label: t('category'), w: 140, html: x => `<span class="cat-badge">${esc(catLabel(x.category))}</span>`, text: x => catLabel(x.category) },
    { k: 'ts', label: t('date'), fmt: fmtTs, w: 150 },
    { k: 'title', label: t('title'), wrap: true, w: 220 },
    { k: 'url', label: t('url'), wrap: true, w: 300, html: x => linkify(x.url, x.url), text: x => x.url },
    { k: 'source', label: t('source'), fmt: v => t(v), w: 110 },
    { k: 'app', label: t('browser'), w: 170 },
    { k: 'device', label: t('device'), w: 130 },
  ] });
}
async function renderNet() {
  const rows = await api('/api/table/net?' + qs());
  const sig = JSON.stringify(rows);
  if (sig === S._netSig && $('#tbl')) return;
  S._netSig = sig;
  $('#main').innerHTML = '<div class="card" id="tbl"></div>';
  makeTable($('#tbl'), { id: 'net', id_: 'id', rows, sortKey: 'start', deletable: 'net', reload: renderNet, freeze: 1, cols: [
    { k: 'kind', label: t('kind'), w: 170, html: x => kindBadge(x.kind), text: x => t(x.kind) },
    { k: 'start', label: t('start'), fmt: fmtTs, w: 150 },
    { k: 'end', label: t('end'), w: 150, html: x => x.ongoing ? `<em>${t('ongoing')}</em>` : esc(fmtTs(x.end)), text: x => x.ongoing ? t('ongoing') : fmtTs(x.end), sortv: x => x.end == null ? Infinity : x.end },
    { k: 'durationMs', label: t('duration'), num: true, fmt: v => fmtDur(v), w: 110 },
    { k: 'transport', label: t('transport'), w: 100 },
    { k: 'detail', label: t('detail'), wrap: true, w: 220 },
    { k: 'device', label: t('device'), w: 130 },
  ] });
}
function showCode(d) {
  const box = $('#codeBox');
  if (!box) return;
  box.innerHTML = `<div class="codebox"><div><div>${t('enrollCode')}</div><div class="code">${esc(d.enrollCode)}</div></div><div>${t('enrollHint')}<br><b>${esc(d.name)}</b></div></div>`;
}
async function renderDevices() {
  const list = await api('/api/devices');
  S.allDevices = list; renderDevPop();
  const now = Date.now();
  // "Offline" used to always use a flat 15-minute window, which falsely flagged
  // a device as offline if its own (admin-configurable) update interval was
  // longer than that — the window now scales with the device's own interval.
  const rows = list.map(d => {
    const win = Math.max(15 * 60000, (d.pollIntervalS || 5) * 1000 * 3);
    return { ...d, status: !d.enrolled ? 'pending' : (d.lastSeen && now - d.lastSeen < win ? 'online' : 'offline') };
  });
  const code = rows.find(r => r.enrollCode && r._show);
  // Same flicker fix as Overview (see renderOverview): the 5s Devices-tab
  // auto-refresh was rebuilding the whole table — add card, codebox and
  // all — every single tick even when nothing about any device had
  // actually changed since the last one.
  const sig = JSON.stringify(rows) + '|' + (code ? code.id : '');
  if (sig === S._devicesSig && $('#tbl')) return;
  S._devicesSig = sig;
  $('#main').innerHTML = `
    ${canWrite() ? `<div class="card"><h3>${t('addDevice')}</h3>
      <div class="add"><input id="newName" placeholder="${esc(t('deviceName'))}"><button class="pbtn" id="addBtn">${t('create')}</button></div>
      <div id="codeBox"></div>
      <div class="apk"><a href="${esc(K.apk)}">${t('downloadApk')}</a></div></div>` : ''}
    <div class="card" id="tbl"></div>`;
  if (canWrite()) {
    $('#addBtn').onclick = async () => {
      const name = $('#newName').value.trim(); if (!name) return;
      const d = await jpost('/api/devices', { name }); await renderDevices(); showCode(d);
    };
    const pend = rows.filter(r => r.status === 'pending' && r.enrollCode)[0]; if (pend) showCode(pend);
  }
  const tbl = $('#tbl');
  makeTable(tbl, { id: 'devices', id_: 'id', rows, sortKey: 'name', sortDir: 'asc', deletable: canWrite() ? 'devices' : null, reload: renderDevices, freeze: 1, cols: [
    { k: 'name', label: t('name'), w: 180, html: x => canWrite()
        ? `<span class="lbl">${esc(x.name)}</span><button class="renamebtn" data-id="${x.id}" title="${esc(t('rename'))}">✎</button>`
        : `<span class="lbl">${esc(x.name)}</span>`, text: x => x.name },
    { k: 'status', label: t('status'), w: 150, html: x => `<span class="dot" style="background:${x.status === 'online' ? 'var(--good)' : x.status === 'pending' ? 'var(--warn)' : 'var(--grey)'}"></span>${esc(t(x.status))}` +
        // remoteCapable goes false the moment the device reboots (Android
        // revokes the screen-capture consent on every reboot — see
        // BootReceiver) and only a tap on the phone itself brings it back.
        // Surfacing it here means the admin sees which devices need that
        // one tap without having to open remote control on each one first
        // to discover it's silently not working.
        (x.enrolled && x.remoteCapable === false ? ` <span class="cat-badge" title="${esc(t('remoteCapableWarn'))}" style="background:#fde1c8;color:#9a5a12">${esc(t('remoteCapableBadge'))}</span>` : ''),
      text: x => t(x.status) },
    { k: 'lastSeen', label: t('lastSeen'), fmt: fmtTs, w: 150 },
    { k: 'ipAddress', label: t('ip'), w: 130, fmt: v => v || '—' },
    { k: 'connectionType', label: t('connectionType'), w: 150, html: x => {
        const c = x.connectionType;
        if (!x.enrolled) return '—';
        let lbl = c === 'wifi' ? t('wifi') : c === 'cellular' ? t('cellular')
          : c === 'ethernet' ? 'Ethernet' : c === 'none' ? t('connNone') : t('connUnknown');
        if (c === 'wifi' && x.wifiBand) lbl += ` (${x.wifiBand})`;
        return esc(lbl);
      }, text: x => x.connectionType },
    { k: 'wifiMbps', label: t('wifiSpeed'), w: 110, num: true, fmt: v => v ? `${v} Mbps` : '—' },
    // CPU/RAM/live network speed: only the Windows client reports these
    // today (see windows-client/pulse_agent/sysstats.py) — Android devices
    // simply show '—' here, same treatment connectionType above already
    // gives a device that hasn't reported one.
    { k: 'cpuPct', label: t('cpuUsage'), w: 90, num: true, fmt: v => v != null ? `${Math.round(v)}%` : '—' },
    { k: 'memUsedMb', label: t('ramUsage'), w: 130, num: true,
      fmt: (v, x) => v != null && x.memTotalMb ? `${Math.round(v / x.memTotalMb * 100)}% (${v}/${x.memTotalMb} MB)` : '—' },
    { k: 'netSpeed', label: t('netSpeed'), w: 140, num: true,
      html: x => (x.netDownKbps == null && x.netUpKbps == null) ? '—'
        : `↓${fmtKbps(x.netDownKbps)} ↑${fmtKbps(x.netUpKbps)}`,
      text: x => `${x.netDownKbps || 0}/${x.netUpKbps || 0}` },
    { k: 'pollIntervalS', label: t('pollIntervalS'), w: 130,
      html: x => canWrite()
        ? `<span class="lbl">${x.pollIntervalS || 5}</span><button class="pollbtn" data-id="${x.id}" title="${esc(t('pollIntervalHint'))}">✎</button>`
        : `<span class="lbl">${x.pollIntervalS || 5}</span>`,
      text: x => x.pollIntervalS },
    { k: 'model', label: t('model'), w: 150 },
    { k: 'osVersion', label: t('os'), w: 90 },
    { k: 'enrolledAt', label: t('enrolledAt'), fmt: fmtTs, w: 150 },
    { k: 'enrollCode', label: t('enrollCode'), w: 150, html: x => {
        const code = x.enrollCode ? `<b dir="ltr">${esc(x.enrollCode)}</b>` : (x.enrolled ? '—' : '—');
        const btn = canWrite() ? `<button class="newcodebtn" data-id="${x.id}" title="${esc(t('newCode'))}">↻ ${esc(t('newCode'))}</button>` : '';
        return `${code}${btn}`;
      }, text: x => x.enrollCode },
    { k: 'remote', label: t('remote'), w: 130, html: x => (x.enrolled && canWrite())
        ? `<button class="tbtn remotebtn" data-id="${x.id}" data-name="${esc(x.name)}">📱 ${esc(t('remote'))}</button>`
        : `<span class="muted">—</span>`, text: () => '' },
  ] });
  wireDeviceRename(tbl, renderDevices);
  wirePollEdit(tbl, renderDevices);
  tbl.addEventListener('click', e => {
    const rb = e.target.closest('.remotebtn[data-id]');
    if (rb) { openRemotePanel(rb.dataset.id, rb.dataset.name); return; }
    const nb = e.target.closest('.newcodebtn[data-id]');
    if (nb) {
      if (!confirm(t('confirmNewCode'))) return;
      jpost(`/api/devices/${nb.dataset.id}/code`, {}, 'POST').then(async d => { await renderDevices(); showCode(d); });
    }
  });
}

const WEEKDAY_KEYS = ['mon','tue','wed','thu','fri','sat','sun'];
let scheduleEditId = null; // null = "add" form; an id = editing that session

function scheduleFormHtml(sch, devices) {
  const s = sch || { name: '', recipient: '', frequency: 'daily', localTime: '08:00', weekday: 0, onceDate: '',
                      sections: ['overview', 'apps', 'net'], unrestricted: false, perDevice: false, deviceIds: [], enabled: true };
  return `
    <div class="formgrid">
      <label>${t('scheduleName')}<input id="rsName" value="${esc(s.name)}"></label>
      <label>${t('recipient')}<input id="rsRecipient" type="email" value="${esc(s.recipient)}" placeholder="a@x.com, b@x.com"></label>
      <label>${t('frequency')}<select id="rsFreq">
        <option value="daily" ${s.frequency==='daily'?'selected':''}>${t('daily')}</option>
        <option value="weekly" ${s.frequency==='weekly'?'selected':''}>${t('weekly')}</option>
        <option value="once" ${s.frequency==='once'?'selected':''}>${t('once')}</option>
      </select></label>
      <label>${t('localTime')}<input id="rsTime" type="time" value="${esc(s.localTime)}"></label>
      <label id="rsWeekdayWrap" style="${s.frequency==='weekly'?'':'display:none'}">${t('weekday')}<select id="rsWeekday">
        ${WEEKDAY_KEYS.map((k, i) => `<option value="${i}" ${s.weekday===i?'selected':''}>${t(k)}</option>`).join('')}
      </select></label>
      <label id="rsDateWrap" style="${s.frequency==='once'?'':'display:none'}">${t('onceDate')}<input id="rsDate" type="date" lang="en-GB" value="${esc(s.onceDate)}"></label>
    </div>
    <label class="chk" style="margin-top:10px"><input type="checkbox" id="rsEnabled" ${s.enabled ? 'checked' : ''}> ${t('enabledQ')}</label>
    <label class="chk"><input type="checkbox" id="rsUnrestricted" ${s.unrestricted ? 'checked' : ''}> ${t('unrestricted')}</label>
    <label class="chk"><input type="checkbox" id="rsPerDevice" ${s.perDevice ? 'checked' : ''}> ${t('perDevice')}</label>
    <div class="muted" id="rsSecLabel" style="margin:10px 0 4px${s.unrestricted ? ';opacity:.4' : ''}">${t('sections')}</div>
    <div class="seclist" id="rsSecList" style="${s.unrestricted ? 'opacity:.4;pointer-events:none' : ''}">
      ${['overview','apps','data','net','devices'].map(k => `<label class="chk"><input type="checkbox" class="rsSec" value="${k}" ${s.sections.includes(k) ? 'checked' : ''}> ${t('sec'+k[0].toUpperCase()+k.slice(1))}</label>`).join('')}
    </div>
    <div class="muted" style="margin:10px 0 4px">${t('devicesFilter')}</div>
    <div class="seclist" id="rsDevList">
      ${devices.map(d => `<label class="chk"><input type="checkbox" class="rsDev" value="${d.id}" ${s.deviceIds.includes(d.id) ? 'checked' : ''}> ${esc(d.name)}</label>`).join('')}
    </div>
    <button class="pbtn" id="rsSave" style="margin-top:14px">${t(sch ? 'update' : 'add')}</button>
    ${sch ? `<button class="tbtn" id="rsCancel" style="margin-top:14px;margin-inline-start:8px">${t('cancel')}</button>` : ''}`;
}

async function renderSettings() {
  const [es, schedules, devices, mem] = await Promise.all([
    api('/api/email-settings'), api('/api/report-schedules'), api('/api/devices'), api('/api/memory?' + qs()),
  ]);
  const latest = mem.latest;
  const memParts = latest ? [
    { name: t('memUsed'), v: latest.usedMb, color: '#d6577a' },
    { name: t('memFree'), v: Math.max(0, (latest.totalMb||0) - (latest.usedMb||0)), color: '#1ba39c' },
  ] : [];
  const editing = scheduleEditId ? schedules.find(s => s.id === scheduleEditId) : null;
  $('#main').innerHTML = `
    <div class="grid cols2">
      <div class="card"><h3>${t('mailTransport')}</h3>
        <div class="formgrid">
          <label>${t('provider')}<select id="esProvider">
            <option value="smtp" ${es.provider==='smtp'?'selected':''}>${t('providerSmtp')}</option>
            <option value="graph" ${es.provider==='graph'?'selected':''}>${t('providerGraph')}</option>
          </select></label>
        </div>
        <div id="esSmtpFields" style="${es.provider==='graph'?'display:none':''}">
          <div class="formgrid">
            <label>${t('smtpHost')}<input id="esHost" value="${esc(es.smtpHost)}" placeholder="smtp.gmail.com"></label>
            <label>${t('smtpPort')}<input id="esPort" type="number" value="${es.smtpPort}"></label>
            <label>${t('smtpUser')}<input id="esUser" value="${esc(es.smtpUser)}"></label>
            <label>${t('smtpPass')}<input id="esPass" type="password" placeholder="${esc(es.hasPassword ? '••••••••' : '')}"><span class="hint">${t('smtpPassHint')}</span></label>
          </div>
          <label class="chk"><input type="checkbox" id="esTls" ${es.useTls ? 'checked' : ''}> ${t('useTls')}</label>
        </div>
        <div id="esGraphFields" style="${es.provider==='graph'?'':'display:none'}">
          <div class="formgrid">
            <label>${t('graphTenantId')}<input id="esTenant" value="${esc(es.graphTenantId)}"></label>
            <label>${t('graphClientId')}<input id="esClientId" value="${esc(es.graphClientId)}"></label>
            <label>${t('graphClientSecret')}<input id="esSecret" type="password" placeholder="${esc(es.hasGraphSecret ? '••••••••' : '')}"><span class="hint">${t('graphClientSecretHint')}</span></label>
            <label>${t('graphSender')}<input id="esSender" type="email" value="${esc(es.graphSender)}"></label>
          </div>
        </div>
        <button class="pbtn" id="esSave" style="margin-top:14px">${t('saveSettings')}</button>
        <div class="formgrid" style="margin-top:14px">
          <label>${t('testRecipient')}<input id="esTestTo" type="email"></label>
        </div>
        <button class="tbtn" id="esTest">${t('testSend')}</button>
      </div>
      <div class="card"><h3>${t('memPie')}</h3>${latest ? pieChart(memParts, v => v + ' MB') : `<div class="empty">${t('noData')}</div>`}</div>
    </div>
    <div class="card"><h3>${editing ? t('editSchedule') : t('addSchedule')}</h3>${scheduleFormHtml(editing, devices)}</div>
    <div class="card"><h3>${t('reportSchedules')}</h3><div id="tbl"></div></div>`;

  $('#esProvider').onchange = () => {
    const graph = $('#esProvider').value === 'graph';
    $('#esSmtpFields').style.display = graph ? 'none' : '';
    $('#esGraphFields').style.display = graph ? '' : 'none';
  };
  $('#esSave').onclick = async () => {
    await jpost('/api/email-settings', {
      provider: $('#esProvider').value,
      smtpHost: $('#esHost').value.trim(), smtpPort: parseInt($('#esPort').value) || 587,
      smtpUser: $('#esUser').value.trim(), smtpPass: $('#esPass').value, useTls: $('#esTls').checked,
      graphTenantId: $('#esTenant').value.trim(), graphClientId: $('#esClientId').value.trim(),
      graphClientSecret: $('#esSecret').value, graphSender: $('#esSender').value.trim(),
    }, 'PUT');
    toast(t('savedOk')); renderSettings();
  };
  $('#esTest').onclick = async () => {
    const recipient = $('#esTestTo').value.trim();
    if (!recipient) { toast(t('testRecipient')); return; }
    const r = await jpost('/api/email-settings/test', { recipient }, 'POST');
    toast(r.ok ? t('testSentOk') : t('testFail') + ': ' + (r.error || ''));
  };

  $('#rsFreq').onchange = () => {
    const f = $('#rsFreq').value;
    $('#rsWeekdayWrap').style.display = f === 'weekly' ? '' : 'none';
    $('#rsDateWrap').style.display = f === 'once' ? '' : 'none';
  };
  $('#rsUnrestricted').onchange = e => {
    const on = e.target.checked;
    $('#rsSecList').style.cssText = on ? 'opacity:.4;pointer-events:none' : '';
    $('#rsSecLabel').style.opacity = on ? '.4' : '';
  };
  if ($('#rsCancel')) $('#rsCancel').onclick = () => { scheduleEditId = null; renderSettings(); };
  $('#rsSave').onclick = async () => {
    const payload = {
      name: $('#rsName').value.trim(), recipient: $('#rsRecipient').value.trim(), frequency: $('#rsFreq').value,
      localTime: $('#rsTime').value || '08:00', weekday: parseInt($('#rsWeekday').value, 10),
      onceDate: $('#rsDate').value, enabled: $('#rsEnabled').checked,
      sections: [...document.querySelectorAll('.rsSec:checked')].map(c => c.value),
      unrestricted: $('#rsUnrestricted').checked, perDevice: $('#rsPerDevice').checked,
      deviceIds: [...document.querySelectorAll('.rsDev:checked')].map(c => parseInt(c.value, 10)),
    };
    if (!payload.recipient) { toast(t('recipient')); return; }
    if (scheduleEditId) await jpost(`/api/report-schedules/${scheduleEditId}`, payload, 'PUT');
    else await jpost('/api/report-schedules', payload, 'POST');
    scheduleEditId = null;
    toast(t('savedOk')); renderSettings();
  };

  const tbl = $('#tbl');
  makeTable(tbl, { id: 'schedules', id_: 'id', rows: schedules, sortKey: 'localTime', sortDir: 'asc', deletable: 'report_schedules', reload: renderSettings, freeze: 1, cols: [
    { k: 'name', label: t('nameCol'), w: 140, text: x => x.name || (x.frequency === 'weekly' ? t(WEEKDAY_KEYS[x.weekday]) : t(x.frequency)) },
    { k: 'recipient', label: t('recipient'), w: 200 },
    { k: 'localTime', label: t('timeCol'), w: 90,
      text: x => `${x.localTime} · ${x.frequency === 'weekly' ? t(WEEKDAY_KEYS[x.weekday]) : x.frequency === 'once' ? x.onceDate : t('daily')}` },
    { k: 'enabled', label: t('statusCol'), w: 90, text: x => x.enabled ? t('on_') : t('off_') },
    { k: 'lastSent', label: t('lastSent'), w: 140, text: x => x.lastSent ? fmtTs(x.lastSent) : '—' },
    { k: 'edit', label: '', w: 70, html: x => `<button class="rsEditBtn" data-id="${x.id}">${t('edit')}</button>`, text: () => '' },
  ] });
  tbl.addEventListener('click', e => {
    const b = e.target.closest('.rsEditBtn[data-id]');
    if (!b) return;
    scheduleEditId = parseInt(b.dataset.id, 10);
    renderSettings();
  });
}

// ── users (superadmin only) ─────────────────────────────────────────────
function roleLabel(r) { return t('role' + r[0].toUpperCase() + r.slice(1)); }
function errToast(r) { toast(t(r.error) || r.error); }
async function editUserAccess(id, users, devices, reload) {
  const u = users.find(x => String(x.id) === String(id));
  if (!u) return;
  const role = (prompt(`${t('role')} — superadmin / admin / viewer`, u.role) || '').trim();
  if (!role) return;
  if (!['superadmin', 'admin', 'viewer'].includes(role)) { toast(t('bad_role')); return; }
  const payload = { role };
  if (role !== 'superadmin') {
    const names = devices.map(d => `${d.id}=${d.name}`).join(' | ');
    const v = prompt(`${t('deviceAccess')}\n${t('deviceIdsHint')}\n${names}`, (u.deviceIds || []).join(','));
    if (v == null) return;
    payload.deviceIds = v.trim() ? v.split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n)) : [];
  } else {
    payload.deviceIds = [];
  }
  const r = await jpost(`/api/users/${id}`, payload, 'PATCH');
  if (r.error) { errToast(r); return; }
  toast(t('roleUpdated')); reload();
}
async function resetUserPassword(id, reload) {
  const p = prompt(t('newPassword'));
  if (p == null || !p.trim()) return;
  const r = await jpost(`/api/users/${id}`, { password: p.trim() }, 'PATCH');
  if (r.error) { errToast(r); return; }
  toast(t('savedOk')); reload();
}
async function renderUsers() {
  const [users, devices] = await Promise.all([api('/api/users'), api('/api/devices')]);
  // Same dedupe as the other tables, plus a focus guard like Devices tab's
  // (startDevicesLive): this tab has a live "add user" form above the
  // table, and without this, the 8s auto-refresh was wiping out whatever
  // an admin was mid-typing into it (username/password) every single tick,
  // not just causing a visual flicker.
  const ae = document.activeElement, main = $('#main');
  if (ae && main && main.contains(ae) && ae.tagName !== 'BUTTON' && $('#tbl')) return;
  const sig = JSON.stringify(users) + '|' + JSON.stringify(devices);
  if (sig === S._usersSig && $('#tbl')) return;
  S._usersSig = sig;
  $('#main').innerHTML = `
    <div class="card"><h3>${t('addUser')}</h3>
      <div class="formgrid">
        <label>${t('username')}<input id="nuUser"></label>
        <label>${t('password')}<input id="nuPass" type="password"></label>
        <label>${t('role')}<select id="nuRole">
          <option value="viewer">${t('roleViewer')}</option>
          <option value="admin">${t('roleAdmin')}</option>
          <option value="superadmin">${t('roleSuperadmin')}</option>
        </select></label>
      </div>
      <div class="muted" id="nuDevLabel" style="margin:10px 0 4px">${t('deviceAccess')}</div>
      <div class="seclist" id="nuDevList">
        <label class="chk"><input type="checkbox" id="nuDevAll" checked> ${t('allDevices')} (${devices.length})</label>
        ${devices.map(d => `<label class="chk"><input type="checkbox" class="nuDev" value="${d.id}" disabled> ${esc(d.name)}</label>`).join('')}
      </div>
      <button class="pbtn" id="nuAdd" style="margin-top:14px">${t('addUser')}</button>
    </div>
    <div class="card" id="tbl"></div>`;
  $('#nuDevAll').onchange = e => {
    $('#nuDevList').querySelectorAll('.nuDev').forEach(c => { c.disabled = e.target.checked; if (e.target.checked) c.checked = false; });
  };
  $('#nuAdd').onclick = async () => {
    const username = $('#nuUser').value.trim(), password = $('#nuPass').value;
    const role = $('#nuRole').value;
    if (!username || !password) { toast(t('usernamePasswordRequired')); return; }
    const deviceIds = $('#nuDevAll').checked ? [] : [...$('#nuDevList').querySelectorAll('.nuDev:checked')].map(c => parseInt(c.value, 10));
    const r = await jpost('/api/users', { username, password, role, deviceIds });
    if (r.error) { errToast(r); return; }
    $('#nuUser').value = ''; $('#nuPass').value = '';
    toast(t('savedOk')); await renderUsers();
  };
  const tbl = $('#tbl');
  makeTable(tbl, { id: 'users', id_: 'id', rows: users, sortKey: 'username', sortDir: 'asc', deletable: 'users', reload: renderUsers, freeze: 1, cols: [
    { k: 'username', label: t('username'), w: 160 },
    { k: 'role', label: t('role'), w: 150,
      html: x => `<span class="lbl">${esc(roleLabel(x.role))}</span><button class="rolebtn" data-id="${x.id}" title="${esc(t('changeRole'))}">✎</button>`,
      text: x => roleLabel(x.role) },
    { k: 'deviceIds', label: t('deviceAccess'), w: 150,
      html: x => x.role === 'superadmin' || !x.deviceIds.length ? t('allDevices') : `${x.deviceIds.length} / ${devices.length}`,
      text: x => x.role === 'superadmin' || !x.deviceIds.length ? t('allDevices') : x.deviceIds.length, num: true },
    { k: 'active', label: t('active'), w: 90,
      html: x => `<input type="checkbox" class="activecb" data-id="${x.id}" ${x.active ? 'checked' : ''} ${x.id === ME.id ? 'disabled' : ''}>`,
      text: x => x.active ? t('active') : t('inactive') },
    { k: 'pw', label: '', w: 120, html: x => `<button class="tbtn pwbtn" data-id="${x.id}">${t('resetPassword')}</button>`, text: () => '' },
  ] });
  tbl.addEventListener('click', e => {
    const rb = e.target.closest('.rolebtn[data-id]');
    if (rb) { editUserAccess(rb.dataset.id, users, devices, renderUsers); return; }
    const pb = e.target.closest('.pwbtn[data-id]');
    if (pb) { resetUserPassword(pb.dataset.id, renderUsers); }
  });
  tbl.addEventListener('change', e => {
    const cb = e.target.closest('.activecb[data-id]');
    if (!cb) return;
    jpost(`/api/users/${cb.dataset.id}`, { active: cb.checked }, 'PATCH').then(r => { if (r.error) { errToast(r); renderUsers(); } });
  });
}

// ── remote screen view + control ────────────────────────────────────────
const RC = { id: null, timer: null, w: 0, h: 0, drag: null };
function openRemotePanel(id, name) {
  RC.id = id; RC.w = 0; RC.h = 0; RC.drag = null; RC.apps = null; RC.appsTries = 0;
  const dev = (S.allDevices || []).find(x => String(x.id) === String(id));
  // Windows devices get a real right-click (long-press on the image) and a
  // live keyboard instead of Android's "apps list"/app-close controls,
  // which have no Windows equivalent — detected off the free-text osVersion
  // the client reports at enroll ("Windows 10 (10.0.19045)"), since there's
  // no dedicated platform field on the device record.
  const isWindows = !!(dev && dev.osVersion && /windows/i.test(dev.osVersion));
  const modal = $('#remoteModal');
  modal.innerHTML = `
    <div class="remote-box">
      <div class="remote-head">
        <h3>${esc(t('remote'))} — ${esc(name)}</h3>
        <div class="remote-head-actions">
          ${!isWindows ? `<button class="rcicon" id="rcAppsBtn" title="${esc(t('remoteApps'))}">⊞</button>` : ''}
          <button class="rcicon" id="rcFull" title="${esc(t('remoteFullscreen'))}">⛶</button>
          <button class="rcicon" id="rcClose" title="${esc(t('remoteClose'))}">✕</button>
        </div>
      </div>
      ${dev && dev.accessibilityEnabled === false ? `<div class="remote-warn">${esc(t('accessibilityWarn'))}</div>` : ''}
      ${dev && dev.remoteCapable === false ? `<div class="remote-warn">${esc(t('remoteCapableWarn'))}</div>` : ''}
      <div class="remote-screen-wrap">
        <div class="remote-wait" id="rcWait">${esc(t('remoteWaiting'))}</div>
        <img id="rcImg" hidden>
        <div class="remote-stale hidden" id="rcStale">${esc(t('remoteStale'))}</div>
      </div>
      ${!isWindows ? `<div class="remote-apps-panel hidden" id="rcAppsPanel">
        <input id="rcAppsSearch" placeholder="${esc(t('remoteAppsSearch'))}">
        <div class="remote-apps-list" id="rcAppsList"><div class="remote-apps-msg">${esc(t('remoteAppsLoading'))}</div></div>
        <div class="remote-hint">${esc(t('remoteCloseHint'))}</div>
      </div>` : ''}
      <div class="remote-toolbar">
        <button class="rcicon" id="rcZoomOut" title="${esc(t('remoteZoomOut'))}">－</button>
        <button class="rcicon" id="rcZoomIn" title="${esc(t('remoteZoomIn'))}">＋</button>
        <span class="rcsep"></span>
        <button class="rcicon" id="rcBack" title="${esc(t('remoteBack'))}">⟲</button>
        <button class="rcicon" id="rcHome" title="${esc(t('remoteHome'))}">⌂</button>
        <button class="rcicon" id="rcRecents" title="${esc(t('remoteRecents'))}">▭</button>
        ${isWindows ? `<span class="rcsep"></span>
        <button class="rcicon" id="rcRightBtn" title="${esc(t('remoteRightClick'))}">🖱️</button>
        <button class="rcicon" id="rcKbBtn" title="${esc(t('remoteKeyboard'))}">⌨</button>` : ''}
      </div>
      ${isWindows ? `<div class="remote-keyboard hidden" id="rcKeyboard">
        <input id="rcKeyCapture" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="${esc(t('remoteTextPh'))}">
        <div class="rc-keyrow">
          <button class="rcicon sm" data-key="escape">Esc</button>
          <button class="rcicon sm" data-key="tab">Tab</button>
          <button class="rcicon sm" data-key="backspace">⌫</button>
          <button class="rcicon sm" data-key="enter">⏎</button>
          <button class="rcicon sm" data-key="win">⊞</button>
          <button class="rcicon sm" data-key="up">↑</button>
          <button class="rcicon sm" data-key="down">↓</button>
          <button class="rcicon sm" data-key="left">←</button>
          <button class="rcicon sm" data-key="right">→</button>
        </div>
      </div>` : `<div class="remote-text">
        <input id="rcText" placeholder="${esc(t('remoteTextPh'))}">
        <button class="tbtn" id="rcSendText">${esc(t('remoteSendText'))}</button>
      </div>`}
      <div class="remote-hint">${esc(t('remoteHint'))}${isWindows ? ' — ' + esc(t('remoteRightClickHint')) : ''}</div>
    </div>`;
  modal.hidden = false;
  // Rotating the screen to landscape makes a much better use of a phone's
  // width while actually working on a PC (the whole point of this card) —
  // most mobile browsers only honor an orientation lock request while in
  // fullscreen, so fullscreen is requested first and the lock piggybacks on
  // it; browsers/devices that support neither just silently keep whatever
  // orientation the phone is already in.
  RC.orientLocked = false;
  if (window.innerWidth <= 760 && screen.orientation && screen.orientation.lock) {
    const tryLock = () => { screen.orientation.lock('landscape').then(() => { RC.orientLocked = true; }).catch(() => {}); };
    const box = $('.remote-box');
    if (box && box.requestFullscreen) box.requestFullscreen().then(tryLock).catch(tryLock);
    else tryLock();
  }
  RC.zoom = 1;
  const img0 = $('#rcImg');
  $('#rcZoomIn').onclick = () => { RC.zoom = Math.min(2.5, RC.zoom + 0.25); img0.style.transform = `scale(${RC.zoom})`; };
  $('#rcZoomOut').onclick = () => { RC.zoom = Math.max(1, RC.zoom - 0.25); img0.style.transform = `scale(${RC.zoom})`; };
  $('#rcClose').onclick = closeRemotePanel;
  $('#rcFull').onclick = () => $('.remote-box').classList.toggle('rc-full');
  $('#rcBack').onclick = () => remoteCmd({ action: 'back' });
  $('#rcHome').onclick = () => remoteCmd({ action: 'home' });
  $('#rcRecents').onclick = () => remoteCmd({ action: 'recents' });
  if (!isWindows) {
    $('#rcAppsBtn').onclick = () => {
      const panel = $('#rcAppsPanel');
      panel.classList.toggle('hidden');
      if (!panel.classList.contains('hidden')) loadRemoteApps();
    };
    $('#rcAppsSearch').oninput = () => renderRemoteApps();
    $('#rcSendText').onclick = () => {
      const v = $('#rcText').value; if (!v) return;
      remoteCmd({ action: 'text', text: v }); $('#rcText').value = '';
    };
  } else {
    RC.rightClickMode = false;
    $('#rcRightBtn').onclick = () => {
      RC.rightClickMode = !RC.rightClickMode;
      $('#rcRightBtn').classList.toggle('on', RC.rightClickMode);
    };
    // Live keyboard: a hidden, always-focused input. Printable characters
    // (including whatever the phone's own on-screen keyboard produces,
    // which doesn't reliably fire keydown events at all — this is the
    // standard way to capture it regardless) are picked up via `input` and
    // forwarded as they're typed, not batched until a Send button is
    // pressed. Keys with no character of their own (Enter, Backspace,
    // arrows, Escape…) and any Ctrl/Alt combo are caught in `keydown`
    // instead and sent as named 'key' commands — see input_sim.key_press().
    const kb = $('#rcKeyboard'), cap = $('#rcKeyCapture');
    $('#rcKbBtn').onclick = () => {
      kb.classList.toggle('hidden');
      if (!kb.classList.contains('hidden')) { cap.value = ''; cap.focus(); }
    };
    const mods = e => { const m = []; if (e.ctrlKey) m.push('ctrl'); if (e.altKey) m.push('alt'); if (e.shiftKey) m.push('shift'); return m; };
    const NAMED = { Escape: 'escape', Tab: 'tab', Backspace: 'backspace', Enter: 'enter',
                     ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', Delete: 'delete' };
    cap.addEventListener('keydown', e => {
      if (NAMED[e.key]) {
        e.preventDefault();
        remoteCmd({ action: 'key', key: NAMED[e.key], modifiers: mods(e) });
        cap.value = '';
      } else if ((e.ctrlKey || e.altKey) && e.key.length === 1) {
        e.preventDefault();
        remoteCmd({ action: 'key', key: e.key, modifiers: mods(e) });
      }
    });
    cap.addEventListener('input', () => {
      const v = cap.value;
      if (v) { remoteCmd({ action: 'text', text: v }); cap.value = ''; }
    });
    kb.querySelectorAll('[data-key]').forEach(b => b.onclick = () => { remoteCmd({ action: 'key', key: b.dataset.key }); cap.focus(); });
  }
  const img = $('#rcImg');
  RC.failStreak = 0; RC.metaTick = 0; RC.lastFrameAt = null;
  img.onload = () => {
    RC.failStreak = 0;
    const w = $('#rcWait'); if (w) w.hidden = true;
    img.hidden = false;
  };
  img.onerror = () => {
    // A single missed poll is normal (a frame just wasn't ready yet at this
    // exact 300ms tick) and shouldn't disturb an already-showing image — it
    // used to: img stayed un-hidden with a now-broken src, so the browser's
    // broken-image glyph flashed in over whatever was last shown. Only after
    // several polls in a row fail (device actually dropped, not just a timing
    // miss) do we re-hide the image and say so, instead of leaving a stale
    // frame or a broken-image icon on screen indefinitely.
    RC.failStreak = (RC.failStreak || 0) + 1;
    if (RC.failStreak >= 5) {
      const w = $('#rcWait'); if (w) { w.textContent = t('remoteLost'); w.hidden = false; }
      img.hidden = true;
      const stale = $('#rcStale'); if (stale) stale.classList.add('hidden');
    }
  };
  // Instant visual feedback for a tap/click landing — a 300ms frame poll
  // can't itself show the result that fast, and without this the panel
  // felt unresponsive compared to AnyDesk/TeamViewer's live cursor, even
  // though the command had actually gone through.
  const tapFx = (px, py) => {
    const wrap = $('.remote-screen-wrap'); if (!wrap) return;
    const fx = el('div', { className: 'rc-tap-fx' });
    const ir = img.getBoundingClientRect(), wr = wrap.getBoundingClientRect();
    fx.style.left = (ir.left - wr.left + px) + 'px';
    fx.style.top = (ir.top - wr.top + py) + 'px';
    wrap.appendChild(fx);
    setTimeout(() => fx.remove(), 420);
  };
  const startDrag = (clientX, clientY) => {
    const r = img.getBoundingClientRect();
    RC.drag = { x: clientX - r.left, y: clientY - r.top, w: r.width, h: r.height, t: Date.now() };
  };
  const endDrag = (clientX, clientY) => {
    if (!RC.drag) return;
    const r = img.getBoundingClientRect();
    const x2 = clientX - r.left, y2 = clientY - r.top;
    const dx = x2 - RC.drag.x, dy = y2 - RC.drag.y;
    const toDevX = px => Math.round((px / RC.drag.w) * (RC.w || img.naturalWidth || 1080));
    const toDevY = px => Math.round((px / RC.drag.h) * (RC.h || img.naturalHeight || 1920));
    if (Math.hypot(dx, dy) < 12) {
      tapFx(RC.drag.x, RC.drag.y);
      // Detecting a right-click off hold duration (a long-press) turned out
      // unreliable on real phones from three different directions at once
      // (the live screen image's own ~300ms refresh cancelling the touch
      // sequence mid-hold, ordinary finger tremor over 500ms reading as
      // "moved", and the browser's own long-press handling on an <img>
      // racing ours) — fixing each one in turn still didn't make it solid.
      // An explicit toggle (🖱️ in the toolbar) sidesteps all three: it
      // reuses the already-reliable plain single tap path below, just
      // relabelled for one tap, instead of needing a held gesture to work
      // at all.
      if (isWindows && RC.rightClickMode) {
        remoteCmd({ action: 'rightclick', x: toDevX(RC.drag.x), y: toDevY(RC.drag.y) });
        RC.rightClickMode = false;
        const rb = $('#rcRightBtn'); if (rb) rb.classList.remove('on');
      } else {
        // Forwarding how long the admin actually held it down (not always a
        // fixed quick tap) is what makes a press-and-hold register on the
        // phone as a real long-press — opening a context menu, starting an
        // icon drag, etc. — instead of every hold just being a fast tap.
        remoteCmd({ action: 'tap', x: toDevX(RC.drag.x), y: toDevY(RC.drag.y), duration: Date.now() - RC.drag.t });
      }
    } else {
      tapFx(x2, y2);
      // A home-screen page swipe is a FLING, not just any drag: launchers
      // (MIUI's especially) only change pages when the gesture's velocity
      // crosses a threshold, and fall back to snapping back to the current
      // page otherwise. Forwarding the admin's *actual* elapsed drag time
      // (as tap's duration does, deliberately, for long-press) was wrong
      // here specifically — a deliberate, careful drag on the dashboard
      // (which is exactly what trying to "do it slower" produces) yields a
      // LOW-velocity synthetic swipe on the phone, under that fling
      // threshold, which is consistent with left/right paging failing
      // almost every time and a slower/longer drag not helping. Cap the
      // dispatched duration well below what a real elapsed drag usually
      // is, so the synthetic gesture is always a quick flick regardless of
      // how carefully the admin dragged — same distance, much less time,
      // much higher velocity.
      const elapsed = Date.now() - RC.drag.t;
      const dur = elapsed < 500 ? Math.max(80, elapsed) : 220;
      remoteCmd({ action: 'swipe', x: toDevX(RC.drag.x), y: toDevY(RC.drag.y), x2: toDevX(x2), y2: toDevY(y2),
                  duration: dur });
    }
    RC.drag = null;
  };
  img.onmousedown = e => { e.preventDefault(); startDrag(e.clientX, e.clientY); };
  img.onmouseup = e => endDrag(e.clientX, e.clientY);
  // Belt-and-suspenders: a real right-click on the image (testing from a
  // desktop mouse) shouldn't pop the browser's own context menu over it.
  img.oncontextmenu = e => e.preventDefault();
  // Two-finger gesture (pinch zoom, or a two-finger pan/scroll) relayed to
  // the phone as two concurrent moving touches — what the phone actually
  // does with it (zoom in/out, scroll, select...) depends on whatever app
  // is open there, same as it would with a real finger; this just replays
  // the two finger paths as drawn here. Only the gesture's start and end
  // points are sent (one discrete command, like swipe), not a continuous
  // live stream — consistent with this panel's whole polling design, but
  // it means mid-gesture motion on the phone only appears once released,
  // not fluidly as it's drawn.
  const startPinch = (t0, t1) => {
    const r = img.getBoundingClientRect();
    RC.pinch = {
      w: r.width, h: r.height, t: Date.now(),
      id0: t0.identifier, id1: t1.identifier,
      s0: { x: t0.clientX - r.left, y: t0.clientY - r.top },
      s1: { x: t1.clientX - r.left, y: t1.clientY - r.top },
      e0: null, e1: null,
    };
    RC.drag = null; // a two-finger gesture always wins over a stray single-finger one
  };
  const trackPinch = touches => {
    const p = RC.pinch; if (!p) return;
    const r = img.getBoundingClientRect();
    for (const t of touches) {
      if (t.identifier === p.id0) p.e0 = { x: t.clientX - r.left, y: t.clientY - r.top };
      if (t.identifier === p.id1) p.e1 = { x: t.clientX - r.left, y: t.clientY - r.top };
    }
  };
  const finishPinch = () => {
    const p = RC.pinch; if (!p) return;
    RC.pinch = null;
    const e0 = p.e0 || p.s0, e1 = p.e1 || p.s1;
    const dur = Math.max(80, Math.min(1500, Date.now() - p.t));
    const midX = (p.s0.x + p.s1.x) / 2, midY = (p.s0.y + p.s1.y) / 2;
    tapFx(midX, midY);
    const dx = px => Math.round((px / p.w) * (RC.w || img.naturalWidth || 1080));
    const dy = px => Math.round((px / p.h) * (RC.h || img.naturalHeight || 1920));
    // A quick two-finger TAP (both fingers barely moved, released quickly)
    // is a right-click — same gesture a laptop trackpad already uses,
    // which AnyDesk/TeamViewer also rely on for this. Only on Windows
    // devices; Android has no such gesture (pinch/zoom is all it ever
    // means there), so a real pinch there is never misread as this.
    const moved0 = Math.hypot(e0.x - p.s0.x, e0.y - p.s0.y);
    const moved1 = Math.hypot(e1.x - p.s1.x, e1.y - p.s1.y);
    if (isWindows && moved0 < 16 && moved1 < 16 && dur < 450) {
      remoteCmd({ action: 'rightclick', x: dx(midX), y: dy(midY) });
      return;
    }
    remoteCmd({ action: 'pinch', duration: dur, touches: [
      [dx(p.s0.x), dy(p.s0.y), dx(e0.x), dy(e0.y)],
      [dx(p.s1.x), dy(p.s1.y), dx(e1.x), dy(e1.y)],
    ] });
  };
  // Touch support: mouse-only handlers meant tap/swipe never worked when
  // the admin used their own touchscreen (phone/tablet browser, or the
  // Admin app's WebView) instead of a mouse — a real gap for an app that's
  // meant to be used from a phone.
  img.ontouchstart = e => {
    e.preventDefault();
    if (e.touches.length >= 2) {
      startPinch(e.touches[0], e.touches[1]);
    } else if (e.touches.length === 1 && !RC.pinch) {
      const tt = e.touches[0];
      startDrag(tt.clientX, tt.clientY);
    }
  };
  img.ontouchmove = e => {
    if (RC.pinch) { e.preventDefault(); trackPinch(e.touches); }
    else if (RC.drag) { e.preventDefault(); } // block page scroll while swiping
  };
  img.ontouchend = e => {
    e.preventDefault();
    if (RC.pinch) {
      if (e.touches.length < 2) finishPinch();
      return;
    }
    const tt = e.changedTouches[0];
    if (tt) endDrag(tt.clientX, tt.clientY);
  };
  img.ontouchcancel = () => { RC.drag = null; RC.pinch = null; };
  jpost(`/api/devices/${id}/remote/start`, {}, 'POST');
  tickRemoteFrame();
  RC.timer = setInterval(tickRemoteFrame, 300);
}
async function tickRemoteFrame() {
  if (!RC.id) return;
  // The dashboard's own auto-refresh is deliberately paused while a remote
  // session is open (it would fight the live screen feed for #main), which
  // means S.allDevices sits frozen at whatever it was when the panel opened
  // — so reading remoteFrameAt from that cache would show "updating" forever
  // using the snapshot from the moment the session started, never actually
  // detecting a stalled stream. Polled on its own slower cadence (~1.2s, not
  // every 300ms tick) so this still catches a real phone-side freeze without
  // hitting /api/devices as hard as the frame fetch itself.
  RC.metaTick = (RC.metaTick || 0) + 1;
  if (RC.metaTick % 4 === 0) {
    try {
      const d = await api('/api/devices').then(l => l.find(x => String(x.id) === String(RC.id)));
      if (d) {
        RC.w = d.remoteScreenW || RC.w; RC.h = d.remoteScreenH || RC.h;
        const stale = $('#rcStale');
        if (stale && d.remoteFrameAt) {
          // A single unchanged reading here only means the phone's next
          // capture (every ~250ms) hasn't landed within this ~1.2s check —
          // normal network jitter, not a real stall. Flagging it on the very
          // first miss made the "stream stalled" banner flash on and off
          // constantly during ordinary use; only showing it after several
          // consecutive misses (~3.6s with nothing new) keeps it for an
          // actual freeze instead.
          // Raised from 3 misses (~3.6s) to 6 (~7.2s): most of what was
          // tripping this was the same CPU-sleep gap behind the "Offline"
          // bug (see CollectorService's wake lock) — a brief, harmless
          // pause, not a real freeze. A longer, more tolerant threshold
          // keeps the banner for genuine stalls without flashing it in
          // during ordinary jitter.
          if (RC.lastFrameAt && d.remoteFrameAt === RC.lastFrameAt && !$('#rcImg').hidden) {
            RC.staleStreak = (RC.staleStreak || 0) + 1;
            if (RC.staleStreak >= 6) stale.classList.remove('hidden');
          } else {
            RC.staleStreak = 0;
            stale.classList.add('hidden');
          }
          RC.lastFrameAt = d.remoteFrameAt;
        }
      }
    } catch (e) { /* ignore — keep last known resolution/state */ }
  }
  const img = $('#rcImg'); if (!img) return;
  img.src = `/api/devices/${RC.id}/screen.jpg?t=${Date.now()}` + (K.key ? `&key=${encodeURIComponent(K.key)}` : '');
}
function remoteCmd(body) {
  if (!RC.id) return;
  jpost(`/api/devices/${RC.id}/remote/command`, body, 'POST');
}
// The phone only uploads its app list on-demand, the first time this remote
// session asks for it (server's /api/v1/remote-state tells it to) — so the
// first fetch here often arrives before that upload lands. Retry a few times
// a couple seconds apart instead of showing "no apps" on the first miss.
async function loadRemoteApps() {
  if (!RC.id) return;
  const id = RC.id;
  try {
    const r = await api(`/api/devices/${id}/apps`);
    if (String(RC.id) !== String(id)) return; // panel was closed/switched meanwhile
    if ((!r.apps || !r.apps.length) && RC.appsTries < 6) {
      RC.appsTries++;
      setTimeout(loadRemoteApps, 2000);
      return;
    }
    RC.apps = r.apps || [];
    renderRemoteApps();
  } catch (e) { /* leave the loading message; next open will retry */ }
}
function renderRemoteApps() {
  const list = $('#rcAppsList'); if (!list) return;
  if (RC.apps == null) { list.innerHTML = `<div class="remote-apps-msg">${esc(t('remoteAppsLoading'))}</div>`; return; }
  if (!RC.apps.length) { list.innerHTML = `<div class="remote-apps-msg">${esc(t('remoteAppsEmpty'))}</div>`; return; }
  const q = ($('#rcAppsSearch').value || '').trim().toLowerCase();
  const rows = q ? RC.apps.filter(a => a.label.toLowerCase().includes(q) || a.pkg.toLowerCase().includes(q)) : RC.apps;
  const sorted = rows.slice().sort((a, b) => a.label.localeCompare(b.label));
  list.innerHTML = sorted.length ? sorted.map(a => `
    <div class="remote-app-row">
      <span class="remote-app-label" title="${esc(a.pkg)}">${esc(a.label)}</span>
      <button class="rcicon sm" data-launch="${esc(a.pkg)}" title="${esc(t('remoteLaunch'))}">▶</button>
      <button class="rcicon sm danger" data-close="${esc(a.pkg)}" title="${esc(t('remoteCloseApp'))}">⏻</button>
    </div>`).join('') : `<div class="remote-apps-msg">${esc(t('remoteAppsNone'))}</div>`;
  list.querySelectorAll('[data-launch]').forEach(b => b.onclick = () => remoteCmd({ action: 'launch', pkg: b.dataset.launch }));
  list.querySelectorAll('[data-close]').forEach(b => b.onclick = () => { if (confirm(t('remoteCloseApp') + '?')) remoteCmd({ action: 'close', pkg: b.dataset.close }); });
}
function closeRemotePanel() {
  if (RC.timer) clearInterval(RC.timer);
  if (RC.id) jpost(`/api/devices/${RC.id}/remote/stop`, {}, 'POST');
  RC.id = null; RC.timer = null;
  $('#remoteModal').hidden = true;
  $('#remoteModal').innerHTML = '';
  try { if (screen.orientation && screen.orientation.unlock) screen.orientation.unlock(); } catch (e) {}
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
}

// ── chrome: chips, device popover, tabs ───────────────────────────────────
const TABS = [['overview', renderOverview], ['apps', renderApps], ['data', renderData], ['browse', renderBrowse], ['net', renderNet], ['devices', renderDevices], ['settings', renderSettings], ['users', renderUsers]];
function visibleTabs() { return TABS.filter(([k]) => (k !== 'settings' && k !== 'users') || isSuper()); }
function renderChips() {
  const items = [['today','today'],['yesterday','yesterday'],['d7','d7'],['d30','d30'],['month','month'],['custom','custom']];
  $('#periodChips').innerHTML = items.map(([k, l]) => `<button class="chip ${S.period === k ? 'on' : ''}" data-p="${k}">${t(l)}</button>`).join('');
  $('#periodChips').querySelectorAll('.chip').forEach(b => b.onclick = () => { S.period = b.dataset.p; $('#customRange').hidden = S.period !== 'custom'; renderChips(); load(); });
}
function renderDevPop() {
  const all = S.allDevices, sel = S.devices;
  const n = sel ? sel.length : all.length;
  $('#devSummary').textContent = `${t('devices')}: ${sel ? n + ' / ' + all.length : t('allDevices') + ' (' + all.length + ')'}`;
  $('#devList').innerHTML = `<label><input type="checkbox" id="devAll" ${!sel ? 'checked' : ''}> <b>${t('allDevices')} (${all.length})</b></label><div class="sep"></div>` +
    all.map(d => `<label><input type="checkbox" class="devcb" value="${d.id}" ${!sel || sel.includes(d.id) ? 'checked' : ''}> ${esc(d.name)}</label>`).join('') +
    `<div class="sep"></div><button type="button" class="btn" id="devDone" style="width:100%">${t('done')}</button>`;
  $('#devAll').onchange = e => { S.devices = null; renderDevPop(); load(); };
  $('#devList').querySelectorAll('.devcb').forEach(cb => cb.onchange = () => {
    const ids = [...$('#devList').querySelectorAll('.devcb')].filter(x => x.checked).map(x => parseInt(x.value, 10));
    S.devices = ids.length === all.length || !ids.length ? null : ids; renderDevPop(); load();
  });
  // Explicit close (mobile-friendly) — the popover otherwise stays open
  // until the summary is clicked again, which reads as "stuck".
  $('#devDone').onclick = () => { $('#devPop').open = false; };
}
// Click outside the device popover (or press Escape) closes it too.
document.addEventListener('click', e => {
  const pop = $('#devPop');
  if (pop && pop.open && !pop.contains(e.target)) pop.open = false;
});
document.addEventListener('keydown', e => {
  const pop = $('#devPop');
  if (pop && pop.open && e.key === 'Escape') pop.open = false;
});
const TAB_LABELS = { devices: 'devices', data: 'dataUsage', settings: 'settings', users: 'users' };
function renderTabs() {
  const tb = $('#tabs'); if (!tb) return;
  const vis = visibleTabs();
  if (!vis.some(([k]) => k === S.tab)) S.tab = 'overview';
  tb.innerHTML = vis.map(([k]) => `<button class="tab ${S.tab === k ? 'on' : ''}" data-t="${k}">${t(TAB_LABELS[k] || k)}</button>`).join('');
  tb.querySelectorAll('.tab').forEach(b => b.onclick = () => { S.tab = b.dataset.t; renderTabs(); renderSidebar(); load(); });
}
// Mobile sidebar nav: the same section list as .tabs, but as a slide-in
// drawer instead of a horizontal strip — see app.css's @media(max-width:760px)
// for why (tabs either wrapped onto their own row on every screen, or
// scrolled sideways with later ones clipped off and no hint more existed).
function renderSidebar() {
  const sb = $('#sidebar'); if (!sb) return;
  const vis = visibleTabs();
  sb.innerHTML = vis.map(([k]) => `<button class="tab ${S.tab === k ? 'on' : ''}" data-t="${k}">${t(TAB_LABELS[k] || k)}</button>`).join('');
  sb.querySelectorAll('.tab').forEach(b => b.onclick = () => { S.tab = b.dataset.t; closeSidebar(); renderTabs(); renderSidebar(); load(); });
}
function openSidebar() {
  const sb = $('#sidebar'), bd = $('#sidebarBackdrop'); if (!sb || !bd) return;
  sb.hidden = false; bd.hidden = false;
  requestAnimationFrame(() => sb.classList.add('open'));
}
function closeSidebar() {
  const sb = $('#sidebar'), bd = $('#sidebarBackdrop'); if (!sb || !bd) return;
  sb.classList.remove('open');
  setTimeout(() => { sb.hidden = true; bd.hidden = true; }, 220);
}
function paintStatic() {
  $('#langBtn').textContent = t('lang'); $('#refreshBtn').textContent = t('refresh');
  $('#exportPdfBtn').textContent = t('exportPdf');
  const lo = $('#logoutBtn'); if (lo) lo.textContent = t('logout');
  renderChips(); renderTabs(); renderSidebar(); renderDevPop();
  watchStickyOffsets();
}
// .top (the navy header bar) wraps onto a second line once its buttons
// don't fit one row — a different point in ar vs en, and it shifts further
// whenever a button is added/removed. .tabs sticks below it, so a
// hardcoded pixel offset drifts out of sync and lets it render partly
// hidden behind the taller bar. This measures the real rendered height
// instead and republishes it as a CSS variable app.css's sticky offset reads.
//
// The table's own <th> row used to need a second variable (--th-top) for
// the same reason, stacked on top of this one — but that was chasing the
// wrong bug: .tw's `overflow-x:auto` makes its computed overflow-y `auto`
// too (plain CSS axis-coupling, not something a pixel offset can fix),
// which makes .tw — not the page — the sticky header's containing box. No
// page-relative offset can ever be right in a box sized to its own content,
// which is why the header kept drifting back to "landing mid-table" every
// time this got re-tuned. app.css now gives .tw a real bounded height and
// pins <th> to top:0 within it, so there's nothing left here to compute.
function syncStickyOffsets() {
  const top = $('.top'); if (!top) return;
  const topH = Math.ceil(top.getBoundingClientRect().height);
  document.documentElement.style.setProperty('--top-h', topH + 'px');
}
// syncStickyOffsets() used to only be called from a handful of spots (init,
// language switch, window resize) — anything else that changes .top's real
// height (a web font finishing its swap-in after first paint, a tab's label
// going from one line to two) left the old, now-wrong offset in place. A
// ResizeObserver tracks it directly — it fires on *any* real size change,
// from whatever caused it, so the offset can't go stale again.
let stickyRO = null;
function watchStickyOffsets() {
  const top = $('.top');
  if (!top) return;
  if (!('ResizeObserver' in window)) { syncStickyOffsets(); return; }
  if (!stickyRO) stickyRO = new ResizeObserver(() => syncStickyOffsets());
  else stickyRO.disconnect();
  stickyRO.observe(top);
  syncStickyOffsets();
}
async function load() {
  try {
    const fn = (TABS.find(x => x[0] === S.tab) || TABS[0])[1];
    await fn(); S.lastLoad = Date.now();
    if (K.kiosk) $('#kioskInfo').innerHTML = `<span id="clock"></span><span>${t('updated')}: ${pad(new Date().getHours())}:${pad(new Date().getMinutes())}</span>`;
  } catch (e) { if (String(e.message) !== '401') console.error(e); }
}

// Keeps the Devices tab's status/last-seen/connection columns current on
// their own fast cadence — the general dashboard auto-refresh (20s, and
// paused entirely during a remote-control session) was far too coarse for
// "catch the information momently" and made Offline/online look stuck for
// minutes at a time. Runs independently of RC.id: the remote panel is a
// separate #remoteModal overlay, not a replacement of #main, so refreshing
// the devices table underneath it is safe and doesn't fight it for
// anything. Skips a tick rather than re-rendering out from under someone
// who is mid-edit (typing a search query or a new device name, renaming a
// device) so the 5s cadence doesn't yank their cursor away.
function startDevicesLive() {
  setInterval(() => {
    if (S.tab !== 'devices' || document.hidden) return;
    const ae = document.activeElement;
    const main = $('#main');
    if (ae && main && main.contains(ae) && ae.tagName !== 'BUTTON') return;
    renderDevices();
  }, 5000);
}
async function init() {
  setLang(lang);
  try {
    const r = await fetch('/api/me' + (K.key ? '?key=' + encodeURIComponent(K.key) : ''));
    ME = r.ok ? await r.json() : { role: 'viewer', deviceIds: [] };
  } catch (e) { ME = { role: 'viewer', deviceIds: [] }; }
  try { S.allDevices = await api('/api/devices?' + (K.key ? 'key=' + encodeURIComponent(K.key) : '')); } catch (e) { S.allDevices = []; }
  $('#langBtn').onclick = () => { setLang(lang === 'ar' ? 'en' : 'ar'); paintStatic(); load(); };
  $('#refreshBtn').onclick = load;
  const menuBtn = $('#menuBtn'), sidebarBackdrop = $('#sidebarBackdrop');
  if (menuBtn) menuBtn.onclick = () => { if ($('#sidebar').classList.contains('open')) closeSidebar(); else openSidebar(); };
  if (sidebarBackdrop) sidebarBackdrop.onclick = closeSidebar;
  $('#exportPdfBtn').onclick = () => window.open('/report/print?' + qs(), '_blank');
  const fd = $('#fromDate'), td = $('#toDate');
  // datetime-local values ("YYYY-MM-DDTHH:mm") parse directly — the user
  // now picks an exact start/end moment, not just whole days.
  const onRange = () => { if (fd.value && td.value) { S.from = new Date(fd.value).getTime(); S.to = new Date(td.value).getTime(); load(); } };
  fd.onchange = td.onchange = onRange;
  paintStatic();
  initChartTooltip();
  startDevicesLive();
  startLiveNow();
  if (K.kiosk) {
    S.tab = 'overview'; S.period = 'd7';
    const tick = () => { const c = $('#clock'); if (c) { const d = new Date(); c.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}`; } };
    setInterval(tick, 15000);
    let flip = false;
    setInterval(() => { flip = !flip; S.period = flip ? 'today' : 'd7'; load(); }, 30000);
    setInterval(load, 60000);
  } else {
    // Auto-refresh the dashboard itself so it reflects new data as it
    // arrives, instead of only on a manual click of the refresh button.
    // Was 20s — too slow once the phone itself can push every few seconds
    // (see CollectorService's syncTask, now tied to the same configurable
    // interval instead of a fixed 2 minutes) for the dashboard to still
    // feel "momently". Paused while the tab isn't visible or the
    // remote-control view is open (a refresh there would interrupt the
    // live screen feed) — the Devices tab gets its own faster, unpaused
    // refresh separately (startDevicesLive above) since it isn't fighting
    // anything for #main.
    setInterval(() => { if (!document.hidden && !RC.id) load(); }, 8000);
  }
  // Re-measure on resize/orientation change (debounced) — window width
  // changes how many header buttons fit per row, and crossing the 760px
  // breakpoint takes .tabs in and out of the sticky stack entirely.
  let roTimer = null;
  window.addEventListener('resize', () => { clearTimeout(roTimer); roTimer = setTimeout(syncStickyOffsets, 150); });
  load();
}
init();
})();
