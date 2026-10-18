package org.pulse.monitor;

import android.app.AppOpsManager;
import android.app.admin.DevicePolicyManager;
import android.content.Context;
import android.content.Intent;
import android.media.projection.MediaProjectionManager;
import android.net.VpnService;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.os.Process;
import android.provider.Settings;
import android.text.TextUtils;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import org.json.JSONObject;

/** JS <-> native bridge. Heavy lifting lives in CollectorService / Uploader / Db. */
@CapacitorPlugin(name = "Pulse", permissions = {
        @Permission(alias = "notifications", strings = { android.Manifest.permission.POST_NOTIFICATIONS })
})
public class PulsePlugin extends Plugin {

    @PluginMethod
    public void getConfig(PluginCall call) {
        Db db = Db.get(getContext());
        JSObject r = new JSObject();
        r.put("consented", db.getBool("consented", false));
        r.put("serverUrl", db.getStr("server_url", ""));
        r.put("deviceName", db.getStr("device_name", ""));
        r.put("enabled", db.getBool("enabled", false));
        call.resolve(r);
    }

    @PluginMethod
    public void setConsented(PluginCall call) {
        Db.get(getContext()).putBool("consented", true);
        call.resolve();
    }

    @PluginMethod
    public void enroll(PluginCall call) {
        String serverUrl = call.getString("serverUrl", "");
        String code = call.getString("code", "");
        if (TextUtils.isEmpty(serverUrl) || TextUtils.isEmpty(code)) {
            call.reject("serverUrl and code are required");
            return;
        }
        new Thread(() -> {
            try {
                Uploader.EnrollResult res = Uploader.enroll(getContext(), serverUrl, code);
                Db db = Db.get(getContext());
                db.put("server_url", serverUrl);
                db.put("device_token", res.token);
                db.put("device_id", String.valueOf(res.deviceId));
                db.put("device_name", res.name);
                JSObject r = new JSObject();
                r.put("deviceId", res.deviceId);
                r.put("name", res.name);
                call.resolve(r);
            } catch (Exception e) {
                call.reject("enroll_failed: " + e.getMessage());
            }
        }).start();
    }

    /**
     * Lightweight counterpart to enroll(): changes ONLY the stored server address,
     * keeping the device's existing token/id as-is. enroll() always burns a fresh
     * one-time code and issues a brand-new token (see the server's /api/v1/enroll),
     * which is overkill when nothing about the registration changed — just the
     * network address of the same server (moved to another PC, new LAN IP after a
     * router reboot, a different port, a domain swapped in for a raw IP, ...).
     * Without `force`, the new address is verified (device's current token still
     * accepted there) before it's saved, so a typo or wrong address doesn't silently
     * break syncing until the next failed attempt.
     */
    @PluginMethod
    public void setServerUrl(PluginCall call) {
        String serverUrl = call.getString("serverUrl", "").trim().replaceAll("/+$", "");
        boolean force = call.getBoolean("force", false);
        if (TextUtils.isEmpty(serverUrl)) {
            call.reject("serverUrl is required");
            return;
        }
        Db db = Db.get(getContext());
        String token = db.getStr("device_token", null);
        if (TextUtils.isEmpty(token)) {
            call.reject("not_enrolled");
            return;
        }
        if (force) {
            db.put("server_url", serverUrl);
            call.resolve();
            return;
        }
        new Thread(() -> {
            boolean ok = Uploader.checkServer(serverUrl, token);
            if (ok) {
                db.put("server_url", serverUrl);
                call.resolve();
            } else {
                call.reject("unreachable");
            }
        }).start();
    }

    @PluginMethod
    public void getPermStatus(PluginCall call) {
        Context ctx = getContext();
        JSObject r = new JSObject();
        r.put("usageAccess", hasUsageAccess(ctx));
        r.put("accessibility", isAccessibilityEnabled(ctx));
        r.put("battery", isIgnoringBattery(ctx));
        r.put("notifications", hasNotifPermission(ctx));
        r.put("vpn", VpnService.prepare(ctx) == null);
        call.resolve(r);
    }

    private boolean hasUsageAccess(Context ctx) {
        AppOpsManager aom = (AppOpsManager) ctx.getSystemService(Context.APP_OPS_SERVICE);
        if (aom == null) return false;
        int mode;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            mode = aom.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), ctx.getPackageName());
        } else {
            mode = aom.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), ctx.getPackageName());
        }
        return mode == AppOpsManager.MODE_ALLOWED;
    }

    /** Also called from Uploader so the dashboard can show a warning when remote
     *  control's taps/swipes won't work because this is off on the phone. */
    public static boolean isAccessibilityEnabled(Context ctx) {
        String enabled = Settings.Secure.getString(ctx.getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        String me = ctx.getPackageName() + "/" + PulseAccessibilityService.class.getName();
        if (TextUtils.isEmpty(enabled)) return false;
        for (String s : enabled.split(":")) if (s.equalsIgnoreCase(me)) return true;
        return false;
    }

    private boolean isIgnoringBattery(Context ctx) {
        PowerManager pm = (PowerManager) ctx.getSystemService(Context.POWER_SERVICE);
        return pm != null && pm.isIgnoringBatteryOptimizations(ctx.getPackageName());
    }

    private boolean hasNotifPermission(Context ctx) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true;
        return ctx.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) == android.content.pm.PackageManager.PERMISSION_GRANTED;
    }

    @PluginMethod
    public void openUsageAccessSettings(PluginCall call) {
        startActivitySafely(new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)
                .setData(Uri.parse("package:" + getContext().getPackageName())));
        call.resolve();
    }

    @PluginMethod
    public void openAccessibilitySettings(PluginCall call) {
        startActivitySafely(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
        call.resolve();
    }

    /** Best-effort deep link into the OEM-specific "autostart on boot" settings
     *  screen (MIUI, EMUI, ColorOS, FuntouchOS, ZenUI, ...). There is no public
     *  Android API for this — every OEM that restricts it ships its own settings
     *  screen under its own package, so this tries the known ones in turn and
     *  falls back to the generic app-info screen if none exist on this phone. */
    @PluginMethod
    public void requestAutostart(PluginCall call) {
        Context ctx = getContext();
        String pkg = ctx.getPackageName();
        Intent[] candidates = new Intent[]{
            new Intent().setClassName("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"),
            new Intent("miui.intent.action.APP_PERM_EDITOR")
                .setClassName("com.miui.securitycenter", "com.miui.permcenter.permissions.PermissionsEditorActivity")
                .putExtra("extra_pkgname", pkg),
            new Intent().setClassName("com.letv.android.letvsafe", "com.letv.android.letvsafe.AutobootManageActivity"),
            new Intent().setClassName("com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"),
            new Intent().setClassName("com.huawei.systemmanager", "com.huawei.systemmanager.optimize.process.ProtectActivity"),
            new Intent().setClassName("com.coloros.safecenter", "com.coloros.safecenter.permission.startup.StartupAppListActivity"),
            new Intent().setClassName("com.oppo.safe", "com.oppo.safe.permission.startup.StartupAppListActivity"),
            new Intent().setClassName("com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity"),
            new Intent().setClassName("com.asus.mobilemanager", "com.asus.mobilemanager.autostart.AutoStartActivity"),
        };
        for (Intent i : candidates) {
            if (startActivitySafely(i)) { call.resolve(); return; }
        }
        // Nothing OEM-specific on this phone (stock Android doesn't restrict
        // autostart) — fall back to this app's own settings screen so there's
        // still somewhere useful to land instead of a dead button.
        Intent fallback = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                .setData(Uri.parse("package:" + pkg));
        if (startActivitySafely(fallback)) call.resolve(); else call.reject("could_not_open_autostart_settings");
    }

    @PluginMethod
    public void requestBattery(PluginCall call) {
        Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
        i.setData(Uri.parse("package:" + getContext().getPackageName()));
        if (startActivitySafely(i)) call.resolve(); else call.reject("could_not_open_battery_settings");
    }

    @PluginMethod
    public void requestNotifications(PluginCall call) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            requestPermissionForAlias("notifications", call, "notifResult");
        } else {
            call.resolve();
        }
    }

    @PermissionCallback
    private void notifResult(PluginCall call) { call.resolve(); }

    @PluginMethod
    public void requestVpn(PluginCall call) {
        Intent intent = VpnService.prepare(getContext());
        if (intent == null) { call.resolve(); return; }
        saveCall(call);
        startActivityForResult(call, intent, "vpnResult");
    }

    @ActivityCallback
    private void vpnResult(PluginCall call, androidx.activity.result.ActivityResult result) {
        if (call != null) call.resolve();
    }

    @PluginMethod
    public void start(PluginCall call) {
        Context ctx = getContext();
        Db.get(ctx).putBool("enabled", true);
        CollectorService.start(ctx);
        if (VpnService.prepare(ctx) == null) DnsVpnService.start(ctx);
        call.resolve();
    }

    @PluginMethod
    public void stop(PluginCall call) {
        Context ctx = getContext();
        Db.get(ctx).putBool("enabled", false);
        CollectorService.stop(ctx);
        DnsVpnService.stop(ctx);
        call.resolve();
    }

    @PluginMethod
    public void syncNow(PluginCall call) {
        Uploader.requestImmediateSync(getContext());
        call.resolve();
    }

    // "Live sync" toggle (status screen, next to Sync now): overrides the
    // dashboard's per-device "Update interval" with a fixed fast interval
    // (see CollectorService.LIVE_SYNC_MS) regardless of what that field is
    // set to, for someone who wants the phone pushing as fast as possible
    // right now without going to the dashboard to change it. Off reverts to
    // the normal configured interval. Persisted so it survives a restart —
    // CollectorService re-reads it on every cycle, no service restart needed.
    @PluginMethod
    public void setLiveSync(PluginCall call) {
        boolean on = call.getBoolean("on", false);
        Db.get(getContext()).putBool("live_sync", on);
        if (on) Uploader.requestImmediateSync(getContext());
        call.resolve();
    }

    @PluginMethod
    public void getStatus(PluginCall call) {
        Db db = Db.get(getContext());
        JSObject r = new JSObject();
        String last = db.getStr("last_sync", null);
        r.put("lastSync", last == null ? JSONObject.NULL : Long.parseLong(last));
        r.put("queueCount", db.countPending());
        r.put("iconHidden", IconVisibility.isHidden(getContext()));
        r.put("remoteCapable", db.getBool("remote_capable", false));
        r.put("liveSync", db.getBool("live_sync", true));
        call.resolve(r);
    }

    @PluginMethod
    public void hideIcon(PluginCall call) {
        IconVisibility.hide(getContext());
        call.resolve();
    }

    @PluginMethod
    public void showIcon(PluginCall call) {
        IconVisibility.show(getContext());
        call.resolve();
    }

    // ── PIN lock ─────────────────────────────────────────────────────────
    @PluginMethod
    public void hasPin(PluginCall call) {
        JSObject r = new JSObject(); r.put("value", PinLock.hasPin(getContext())); call.resolve(r);
    }

    @PluginMethod
    public void setPin(PluginCall call) {
        String pin = call.getString("pin", "");
        if (pin.length() < 4 || pin.length() > 6 || !pin.matches("\\d+")) {
            call.reject("pin must be 4-6 digits");
            return;
        }
        PinLock.setPin(getContext(), pin);
        call.resolve();
    }

    @PluginMethod
    public void verifyPin(PluginCall call) {
        boolean ok = PinLock.verify(getContext(), call.getString("pin", ""));
        JSObject r = new JSObject(); r.put("ok", ok); call.resolve(r);
    }

    // ── Device admin (uninstall friction) ───────────────────────────────
    @PluginMethod
    public void isDeviceAdminActive(PluginCall call) {
        DevicePolicyManager dpm = (DevicePolicyManager) getContext().getSystemService(Context.DEVICE_POLICY_SERVICE);
        boolean active = dpm != null && dpm.isAdminActive(PulseDeviceAdminReceiver.componentName(getContext()));
        JSObject r = new JSObject(); r.put("value", active); call.resolve(r);
    }

    @PluginMethod
    public void requestDeviceAdmin(PluginCall call) {
        // Some OEM system UIs (MIUI in particular) render this exact system
        // screen as blank/black for some users — an OS-level quirk, not
        // something this intent's extras control. We can't fix that render,
        // but we used to also leave the JS side with no idea what happened:
        // a plain startActivity() resolves the moment the screen *opens*, so
        // "Grant" flips straight to "Granted"-looking silence whether or not
        // the user ever actually saw and tapped Activate. Routing it through
        // startActivityForResult means we resolve only once that screen
        // closes, with the real isAdminActive() value — so the JS layer can
        // tell a genuine grant from "nothing happened" and point at the
        // manual Settings path for the latter.
        Intent i = new Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN);
        i.putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, PulseDeviceAdminReceiver.componentName(getContext()));
        i.putExtra(DevicePolicyManager.EXTRA_ADD_EXPLANATION, getContext().getString(R.string.pulse_device_admin_desc));
        try {
            saveCall(call);
            startActivityForResult(call, i, "deviceAdminResult");
        } catch (Exception e) {
            call.reject("could_not_open_device_admin_settings");
        }
    }

    @ActivityCallback
    private void deviceAdminResult(PluginCall call, androidx.activity.result.ActivityResult result) {
        if (call == null) return;
        DevicePolicyManager dpm = (DevicePolicyManager) getContext().getSystemService(Context.DEVICE_POLICY_SERVICE);
        boolean active = dpm != null && dpm.isAdminActive(PulseDeviceAdminReceiver.componentName(getContext()));
        JSObject r = new JSObject(); r.put("value", active); call.resolve(r);
    }

    /** Fallback for phones where ACTION_ADD_DEVICE_ADMIN itself misbehaves (seen on some
     *  MIUI builds as a blank/black screen): the generic security settings list, where
     *  "Device admin apps" (wording varies by OEM/Android version) is always reachable. */
    @PluginMethod
    public void openSecuritySettings(PluginCall call) {
        if (startActivitySafely(new Intent(Settings.ACTION_SECURITY_SETTINGS))) call.resolve();
        else call.reject("could_not_open_security_settings");
    }

    // ── remote screen view + control ────────────────────────────────────
    // Android requires this consent to come from an on-device system dialog —
    // it cannot be granted remotely or silently (see ScreenCaptureService's
    // class doc). Once granted, the capability persists until the app process
    // is killed (reboot, OOM, force-stop), after which it needs re-granting.
    @PluginMethod
    public void requestScreenCapture(PluginCall call) {
        MediaProjectionManager mpm = (MediaProjectionManager) getContext().getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        if (mpm == null) { call.reject("media_projection_unavailable"); return; }
        saveCall(call);
        startActivityForResult(call, mpm.createScreenCaptureIntent(), "screenCaptureResult");
    }

    @ActivityCallback
    private void screenCaptureResult(PluginCall call, androidx.activity.result.ActivityResult result) {
        if (call == null) return;
        if (result.getResultCode() != android.app.Activity.RESULT_OK || result.getData() == null) {
            Db.get(getContext()).putBool("remote_capable", false);
            call.reject("consent_denied");
            return;
        }
        ScreenCaptureService.start(getContext(), result.getResultCode(), result.getData());
        Db.get(getContext()).putBool("remote_capable", true);
        call.resolve();
    }

    @PluginMethod
    public void stopScreenCapture(PluginCall call) {
        ScreenCaptureService.stop(getContext());
        Db.get(getContext()).putBool("remote_capable", false);
        call.resolve();
    }

    /** @return true if the activity actually launched. Several callers used to
     * swallow this silently (missing manifest permission, no activity able to
     * handle the intent, OEM restrictions, ...) which made their buttons look
     * like they "did nothing" when tapped — now surfaced via call.reject(). */
    private boolean startActivitySafely(Intent intent) {
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try { getContext().startActivity(intent); return true; } catch (Exception e) { return false; }
    }
}
