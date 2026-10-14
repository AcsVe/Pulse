package org.pulse.monitor;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.net.VpnService;

/** Restarts the collector (and DNS VPN, if it was granted) after a reboot, only if the user had it enabled. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) return;
        String action = intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action) && !"android.intent.action.QUICKBOOT_POWERON".equals(action)) {
            return;
        }
        Db db = Db.get(context);
        // The MediaProjection consent token doesn't survive a reboot (an Android
        // platform rule, not something this app can work around) — clear the
        // flag so the setup UI correctly shows "needs re-enabling" rather than a
        // stale "on" that silently stopped working.
        db.putBool("remote_capable", false);
        if (!db.getBool("enabled", false)) return;
        CollectorService.start(context);
        if (VpnService.prepare(context) == null) DnsVpnService.start(context);
    }
}
