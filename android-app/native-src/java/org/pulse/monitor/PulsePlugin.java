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
import com.getcapacitor.CapacitorPlugin;
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
                Uploader.EnrollResult res = Uploader.enroll(serverUrl, code);
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

    private boolean isAccessibilityEnabled(Context ctx) {
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

    @PluginMethod
    public void requestBattery(PluginCall call) {
        Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
        i.setData(Uri.parse("package:" + getContext().getPackageName()));
        startActivitySafely(i);
        call.resolve();
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

    @PluginMethod
    public void getStatus(PluginCall call) {
        Db db = Db.get(getContext());
        JSObject r = new JSObject();
        String last = db.getStr("last_sync", null);
        r.put("lastSync", last == null ? JSONObject.NULL : Long.parseLong(last));
        r.put("queueCount", db.countPending());
        r.put("iconHidden", IconVisibility.isHidden(getContext()));
        r.put("remoteCapable", db.getBool("remote_capable", false));
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
        Intent i = new Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN);
        i.putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, PulseDeviceAdminReceiver.componentName(getContext()));
        i.putExtra(DevicePolicyManager.EXTRA_ADD_EXPLANATION, getContext().getString(R.string.pulse_device_admin_desc));
        startActivitySafely(i);
        call.resolve();
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

    private void startActivitySafely(Intent intent) {
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try { getContext().startActivity(intent); } catch (Exception ignored) { }
    }
}
