package org.pulse.monitor;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;

/**
 * Foreground service: keeps a persistent notification visible (the app is
 * deliberately NOT hidden — this is a disclosed monitor, not spyware), polls
 * UsageStatsManager periodically, and flushes the local queue to the server.
 */
public class CollectorService extends Service {
    public static final String ACTION_SYNC_NOW = "org.pulse.monitor.SYNC_NOW";
    private static final String CHANNEL_ID = "pulse_running";
    private static final int NOTIF_ID = 1001;
    private static final long POLL_MS = 60_000;
    private static final long DATA_POLL_MS = 15 * 60_000;  // TrafficStats: coarse buckets are plenty
    // "Live sync" toggle on the status screen — overrides the configured
    // interval with this fixed fast one while on, independent of whatever
    // the dashboard's "Update interval" is set to.
    private static final long LIVE_SYNC_MS = 5_000;
    private static final long MEM_POLL_MS = 5 * 60_000;

    private HandlerThread thread;
    private Handler handler;
    private NetMonitor netMonitor;
    // A foreground service with "ignore battery optimizations" granted is
    // still not enough on its own: that exemption stops the *system* from
    // deferring this app's jobs/network, but it does nothing to stop the
    // CPU itself from going to sleep in Doze once the screen is off, and a
    // sleeping CPU just doesn't run a Handler's postDelayed() callbacks —
    // they queue up and fire whenever something else next wakes the device
    // (an unlock, a push...), which could be minutes or hours later. That
    // gap is exactly what made a genuinely connected device sit at
    // "Offline" on the dashboard for long stretches: last_seen really did
    // stop updating, because this service really did stop running, even
    // though nothing had crashed and the notification was still showing.
    // Holding a PARTIAL_WAKE_LOCK for as long as the service is alive keeps
    // the CPU (not the screen) awake so the poll/sync timers actually fire
    // on schedule.
    private PowerManager.WakeLock wakeLock;
    private final Runnable pollTask = new Runnable() {
        @Override public void run() {
            try {
                new UsageCollector(getApplicationContext()).poll();
                Db.get(getApplicationContext()).vacuumOld();
            } catch (Exception ignored) { }
            handler.postDelayed(this, currentPollMs());
        }
    };
    /** The dashboard's per-device "update interval" (Devices tab), clamped
     *  5s..1h — picked up from the kv store, which Uploader refreshes from
     *  every sync response. Falls back to the default when unset.
     *  Also drives syncTask below: this used to be the usage-poll cadence
     *  only, while the actual upload-to-server was a separate, fixed
     *  120-second timer — so the dashboard's "Update interval" field never
     *  meant what it looked like it meant, and setting it to a few seconds
     *  still left the server (and the devices table) up to 2 minutes stale.
     *  One interval now governs both: how often this collects local usage
     *  data AND how often it pushes it to the server. */
    private long currentPollMs() {
        Db db = Db.get(getApplicationContext());
        // Defaults to ON. The opt-in toggle made "fast sync" something you
        // had to remember to go turn on after every install — after enough
        // rounds of "where's the automatic sync button" even after it
        // existed, the simpler fix is to stop making it optional: a fresh
        // (or freshly-updated) install now syncs live by default, and the
        // button on the status screen is there to turn it OFF for battery
        // saving, not to turn it on.
        if (db.getBool("live_sync", true)) return LIVE_SYNC_MS;
        try {
            int s = Integer.parseInt(db.getStr("poll_interval_s", "5"));
            return Math.max(5, Math.min(s, 3600)) * 1000L;
        } catch (NumberFormatException e) {
            return POLL_MS;
        }
    }
    // Live sync also speeds up per-app bandwidth sampling (for the
    // dashboard's "live now" data-usage feed) — but not down to LIVE_SYNC_MS:
    // each sample walks every installed app's UID counters via
    // PackageManager + TrafficStats, which is meaningfully heavier than a
    // sync tick, so this settles for "every 20s" (still 45x more often than
    // the old fixed 15 minutes) rather than hammering that loop every 5s.
    private static final long LIVE_DATA_POLL_MS = 20_000;
    private long currentDataPollMs() {
        return Db.get(getApplicationContext()).getBool("live_sync", true) ? LIVE_DATA_POLL_MS : DATA_POLL_MS;
    }
    private final Runnable dataTask = new Runnable() {
        @Override public void run() {
            try { new DataUsageCollector(getApplicationContext()).poll(); } catch (Exception ignored) { }
            handler.postDelayed(this, currentDataPollMs());
        }
    };
    private final Runnable memTask = new Runnable() {
        @Override public void run() {
            try { MemorySampler.poll(getApplicationContext()); } catch (Exception ignored) { }
            handler.postDelayed(this, MEM_POLL_MS);
        }
    };
    private final Runnable syncTask = new Runnable() {
        @Override public void run() {
            Uploader.syncOnce(getApplicationContext());
            handler.postDelayed(this, currentPollMs());
        }
    };

    public static void start(Context ctx) {
        Intent i = new Intent(ctx, CollectorService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) ctx.startForegroundService(i);
        else ctx.startService(i);
    }

    public static void stop(Context ctx) {
        ctx.stopService(new Intent(ctx, CollectorService.class));
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
        startForeground(NOTIF_ID, buildNotification());
        acquireWakeLock();
        thread = new HandlerThread("pulse-collector");
        thread.start();
        handler = new Handler(thread.getLooper());
        netMonitor = new NetMonitor(getApplicationContext());
        netMonitor.start();
        handler.post(pollTask);
        handler.post(dataTask);
        handler.post(memTask);
        handler.post(syncTask);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_SYNC_NOW.equals(intent.getAction()) && handler != null) {
            handler.post(() -> Uploader.syncOnce(getApplicationContext()));
        }
        return START_STICKY;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        // Some OEM launchers kill every service tied to a task when the user
        // swipes the app away from Recents, even a foreground one. This is a
        // setup-UI task, not the monitoring itself, so immediately restart the
        // service if it's still meant to be running.
        super.onTaskRemoved(rootIntent);
        if (Db.get(getApplicationContext()).getBool("enabled", false)) {
            start(getApplicationContext());
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (netMonitor != null) netMonitor.stop();
        if (handler != null) {
            handler.removeCallbacks(pollTask);
            handler.removeCallbacks(dataTask);
            handler.removeCallbacks(memTask);
            handler.removeCallbacks(syncTask);
        }
        if (thread != null) thread.quitSafely();
        releaseWakeLock();
    }

    private void acquireWakeLock() {
        try {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            if (pm == null) return;
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "pulse:collector");
            wakeLock.setReferenceCounted(false);
            // No timeout: this is meant to be held for the service's whole
            // lifetime (release() below is what ends it), not a short burst.
            wakeLock.acquire();
        } catch (Exception ignored) { }
    }

    private void releaseWakeLock() {
        try {
            if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        } catch (Exception ignored) { }
        wakeLock = null;
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm == null) return;
        NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "Pulse", NotificationManager.IMPORTANCE_LOW);
        ch.setDescription("Pulse monitoring is active on this device");
        ch.setShowBadge(false);
        nm.createNotificationChannel(ch);
    }

    private Notification buildNotification() {
        // Always route through ShowIconReceiver, not a plain launch intent: if the
        // launcher icon is currently hidden, getLaunchIntentForPackage() would
        // return null and the owner would have no way back into their own app.
        // Tapping this notification re-enables the icon and opens the app, whatever
        // the current hidden state is.
        Intent showIntent = new Intent(this, ShowIconReceiver.class);
        PendingIntent pi = PendingIntent.getBroadcast(this, 0, showIntent,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID) : new Notification.Builder(this);
        b.setContentTitle("Pulse")
         .setContentText("مراقبة الجهاز نشطة")
         .setSmallIcon(android.R.drawable.ic_menu_info_details)
         .setOngoing(true)
         .setContentIntent(pi);
        return b.build();
    }
}
