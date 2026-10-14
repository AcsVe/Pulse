package org.pulse.monitor;

import android.app.usage.UsageEvents;
import android.app.usage.UsageStatsManager;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;

import java.util.HashMap;
import java.util.Map;

/**
 * Reconstructs foreground sessions from UsageStatsManager's raw event stream
 * (MOVE_TO_FOREGROUND / MOVE_TO_BACKGROUND pairs) since the last poll.
 */
public class UsageCollector {
    private final Context ctx;
    private final Db db;

    public UsageCollector(Context ctx) {
        this.ctx = ctx.getApplicationContext();
        this.db = Db.get(this.ctx);
    }

    public void poll() {
        UsageStatsManager usm = (UsageStatsManager) ctx.getSystemService(Context.USAGE_STATS_SERVICE);
        if (usm == null) return;
        long now = System.currentTimeMillis();
        long since = Long.parseLong(db.getStr("usage_cursor", String.valueOf(now - 24L * 3600 * 1000)));
        // Clamp: never look back more than 7 days even after a long time offline.
        if (since < now - 7L * 24 * 3600 * 1000) since = now - 7L * 24 * 3600 * 1000;

        UsageEvents events = usm.queryEvents(since, now);
        UsageEvents.Event e = new UsageEvents.Event();
        Map<String, Long> openSince = new HashMap<>();
        PackageManager pm = ctx.getPackageManager();

        while (events.hasNextEvent()) {
            events.getNextEvent(e);
            String pkg = e.getPackageName();
            if (pkg == null || pkg.equals(ctx.getPackageName())) continue;
            int type = e.getEventType();
            if (type == UsageEvents.Event.MOVE_TO_FOREGROUND) {
                openSince.put(pkg, e.getTimeStamp());
            } else if (type == UsageEvents.Event.MOVE_TO_BACKGROUND) {
                Long start = openSince.remove(pkg);
                if (start != null && e.getTimeStamp() > start) {
                    db.addUsage(pkg, label(pm, pkg), start, e.getTimeStamp());
                }
            }
        }
        // Still-foreground apps at the time of this poll: record up to "now" so
        // a long session isn't invisible until it finally backgrounds; next
        // poll's cursor starts from "now" so it won't be double-counted, it
        // just continues to accrue in a fresh row (sessions get merged
        // server-side when keys collide: same package + same original start
        // happens only on true continuations, otherwise simply adjacent rows).
        for (Map.Entry<String, Long> en : openSince.entrySet()) {
            if (now > en.getValue()) db.addUsage(en.getKey(), label(pm, en.getKey()), en.getValue(), now);
        }

        db.put("usage_cursor", String.valueOf(now));
    }

    private String label(PackageManager pm, String pkg) {
        try {
            ApplicationInfo ai = pm.getApplicationInfo(pkg, 0);
            CharSequence l = pm.getApplicationLabel(ai);
            return l == null ? pkg : l.toString();
        } catch (PackageManager.NameNotFoundException e) {
            return pkg;
        }
    }
}
