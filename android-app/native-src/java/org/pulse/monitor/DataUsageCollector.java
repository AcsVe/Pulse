package org.pulse.monitor;

import android.app.AppOpsManager;
import android.app.usage.NetworkStats;
import android.app.usage.NetworkStatsManager;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.net.ConnectivityManager;
import android.net.TrafficStats;
import android.os.Build;
import android.os.Process;

import java.util.List;

/**
 * Turns cumulative network byte counters into per-poll deltas and emits one
 * '__device__' sentinel row per poll with the whole-device total, matching
 * the server's DataUsage model (see server/models.py).
 *
 * Per-app breakdown used to come from TrafficStats.getUid{Rx,Tx}Bytes(uid),
 * which only works for the calling app's own UID on modern Android — for
 * every other app it silently returns 0 (not UNSUPPORTED), so the "<=0 skip"
 * below quietly dropped every app's row forever. That's why the dashboard's
 * Data usage tab and "App data usage" card looked permanently empty even
 * though device-wide totals (which don't depend on per-UID access) were
 * fine. NetworkStatsManager.queryDetailsForUid is the real per-app API —
 * it needs the same Usage access (PACKAGE_USAGE_STATS) permission Pulse
 * already asks for elsewhere, so it's used here whenever that's granted,
 * with the old TrafficStats path kept as a fallback for devices where it
 * isn't (per-app rows just won't show there, same as before).
 */
public class DataUsageCollector {
    private final Context ctx;
    private final Db db;

    public DataUsageCollector(Context ctx) {
        this.ctx = ctx.getApplicationContext();
        this.db = Db.get(this.ctx);
    }

    public void poll() {
        long now = System.currentTimeMillis();
        String transport = NetMonitor.currentTransport(ctx);
        PackageManager pm = ctx.getPackageManager();

        // Whole-device totals (independent of per-app support — always available).
        long devRx = TrafficStats.getTotalRxBytes();
        long devTx = TrafficStats.getTotalTxBytes();
        if (devRx != TrafficStats.UNSUPPORTED && devTx != TrafficStats.UNSUPPORTED) {
            long[] delta = diff("__device__", devRx, devTx);
            db.addDataUsage("__device__", "", now, delta[0], delta[1], transport);
        }

        // Window to ask NetworkStatsManager about: since the last poll (so this
        // reports a true per-interval delta, same shape as the TrafficStats path).
        // On the very first poll there's no prior timestamp — fall back to "the
        // last 5 minutes" rather than querying since epoch (slow, and would count
        // ancient usage as if it just happened).
        long lastPoll = Long.parseLong(db.getStr("data_poll_ts", String.valueOf(now - 300_000)));
        NetworkStatsManager nsm = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && hasUsageAccess(ctx))
                ? (NetworkStatsManager) ctx.getSystemService(Context.NETWORK_STATS_SERVICE) : null;

        List<ApplicationInfo> apps;
        try {
            apps = pm.getInstalledApplications(PackageManager.GET_META_DATA);
        } catch (Exception e) {
            apps = java.util.Collections.emptyList();
        }
        String self = ctx.getPackageName();
        for (ApplicationInfo ai : apps) {
            if (ai.packageName.equals(self)) continue;
            long rxDelta, txDelta;
            if (nsm != null) {
                long[] s = queryStatsForUid(nsm, ai.uid, lastPoll, now);
                if (s == null) continue; // query failed for this uid — skip, don't report a false zero
                rxDelta = s[0]; txDelta = s[1];
            } else {
                long rx = TrafficStats.getUidRxBytes(ai.uid);
                long tx = TrafficStats.getUidTxBytes(ai.uid);
                if (rx == TrafficStats.UNSUPPORTED || tx == TrafficStats.UNSUPPORTED) continue;
                long[] delta = diff("uid:" + ai.uid, rx, tx);
                rxDelta = delta[0]; txDelta = delta[1];
            }
            if (rxDelta <= 0 && txDelta <= 0) continue;
            db.addDataUsage(ai.packageName, label(pm, ai), now, rxDelta, txDelta, transport);
        }
        db.put("data_poll_ts", String.valueOf(now));
    }

    /** Sums Wi-Fi + mobile usage for one UID over [start, end). Returns null on
     *  failure (permission revoked mid-flight, OEM quirk, etc.) so the caller can
     *  skip the uid instead of reporting a misleading 0. */
    private long[] queryStatsForUid(NetworkStatsManager nsm, int uid, long start, long end) {
        long rx = 0, tx = 0;
        boolean any = false;
        for (int type : new int[]{ConnectivityManager.TYPE_WIFI, ConnectivityManager.TYPE_MOBILE}) {
            NetworkStats stats = null;
            try {
                stats = nsm.queryDetailsForUid(type, null, start, end, uid);
                NetworkStats.Bucket bucket = new NetworkStats.Bucket();
                while (stats.hasNextBucket()) {
                    stats.getNextBucket(bucket);
                    rx += bucket.getRxBytes();
                    tx += bucket.getTxBytes();
                }
                any = true;
            } catch (Exception ignored) {
                // Thrown for a type this device/UID has no stats for — not fatal,
                // the other transport type may still succeed.
            } finally {
                if (stats != null) stats.close();
            }
        }
        return any ? new long[]{rx, tx} : null;
    }

    private boolean hasUsageAccess(Context c) {
        AppOpsManager aom = (AppOpsManager) c.getSystemService(Context.APP_OPS_SERVICE);
        if (aom == null) return false;
        int mode;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            mode = aom.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), c.getPackageName());
        } else {
            mode = aom.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), c.getPackageName());
        }
        return mode == AppOpsManager.MODE_ALLOWED;
    }

    /** TrafficStats counters are cumulative since boot; diff against the last stored
     *  reading and reset the baseline to the raw value on every call. A counter that
     *  goes backwards (reboot, counter wrap) is treated as "no prior baseline". */
    private long[] diff(String key, long rx, long tx) {
        long prevRx = Long.parseLong(db.getStr("tx_rx_" + key, "-1"));
        long prevTx = Long.parseLong(db.getStr("tx_tx_" + key, "-1"));
        db.put("tx_rx_" + key, String.valueOf(rx));
        db.put("tx_tx_" + key, String.valueOf(tx));
        if (prevRx < 0 || prevTx < 0 || rx < prevRx || tx < prevTx) return new long[]{0, 0};
        return new long[]{rx - prevRx, tx - prevTx};
    }

    private String label(PackageManager pm, ApplicationInfo ai) {
        try {
            CharSequence l = pm.getApplicationLabel(ai);
            return l == null ? ai.packageName : l.toString();
        } catch (Exception e) {
            return ai.packageName;
        }
    }
}
