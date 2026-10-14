package org.pulse.monitor;

import android.app.ActivityManager;
import android.content.Context;

/**
 * Whole-device memory snapshot via ActivityManager.getMemoryInfo(). There is no
 * public, permission-free API for per-app or per-process memory on modern Android
 * (ActivityManager#getProcessMemoryInfo is restricted since Android 9, and
 * per-app CPU usage has no public API at all since Android 8 — see the "cpuNote"
 * string shown in the dashboard's Settings tab) so this is device-level only.
 */
public class MemorySampler {
    public static void poll(Context ctx) {
        ActivityManager am = (ActivityManager) ctx.getSystemService(Context.ACTIVITY_SERVICE);
        if (am == null) return;
        ActivityManager.MemoryInfo mi = new ActivityManager.MemoryInfo();
        try {
            am.getMemoryInfo(mi);
        } catch (Exception e) {
            return;
        }
        if (mi.totalMem <= 0) return;
        long totalMb = mi.totalMem / (1024 * 1024);
        long usedMb = totalMb - (mi.availMem / (1024 * 1024));
        Db.get(ctx).addMemSample(System.currentTimeMillis(), Math.max(0, usedMb), totalMb);
    }
}
