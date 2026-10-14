package org.pulse.monitor;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.net.TrafficStats;

import java.util.List;

/**
 * Samples cumulative per-UID network byte counters from TrafficStats and turns
 * them into per-poll deltas (TrafficStats itself only exposes totals-since-boot,
 * not per-interval usage, so this class is the thing that makes it a time series).
 * Also emits one '__device__' sentinel row per poll with the whole-device total,
 * matching the server's DataUsage model (see server/models.py).
 *
 * No special permission is required: TrafficStats' per-UID counters and
 * ActivityManager/PackageManager app enumeration are both plain public APIs.
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

        // Per-app totals via each app's UID. Some OEMs/Android versions restrict or
        // zero this out for apps without matching UIDs or without usage-access-like
        // permissions — those simply come back as 0/0 and are skipped (addDataUsage
        // already no-ops on a zero delta), so this degrades gracefully.
        List<ApplicationInfo> apps;
        try {
            apps = pm.getInstalledApplications(PackageManager.GET_META_DATA);
        } catch (Exception e) {
            apps = java.util.Collections.emptyList();
        }
        String self = ctx.getPackageName();
        for (ApplicationInfo ai : apps) {
            if (ai.packageName.equals(self)) continue;
            long rx = TrafficStats.getUidRxBytes(ai.uid);
            long tx = TrafficStats.getUidTxBytes(ai.uid);
            if (rx == TrafficStats.UNSUPPORTED || tx == TrafficStats.UNSUPPORTED) continue;
            long[] delta = diff("uid:" + ai.uid, rx, tx);
            if (delta[0] <= 0 && delta[1] <= 0) continue;
            db.addDataUsage(ai.packageName, label(pm, ai), now, delta[0], delta[1], transport);
        }
        db.put("data_poll_ts", String.valueOf(now));
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
