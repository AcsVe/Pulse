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
    private static final long SYNC_MS = 120_000;
    private static final long DATA_POLL_MS = 15 * 60_000;  // TrafficStats: coarse buckets are plenty
    private static final long MEM_POLL_MS = 5 * 60_000;

    private HandlerThread thread;
    private Handler handler;
    private NetMonitor netMonitor;
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
     *  every sync response. Falls back to the default when unset. */
    private long currentPollMs() {
        try {
            int s = Integer.parseInt(Db.get(getApplicationContext()).getStr("poll_interval_s", "60"));
            return Math.max(5, Math.min(s, 3600)) * 1000L;
        } catch (NumberFormatException e) {
            return POLL_MS;
        }
    }
    private final Runnable dataTask = new Runnable() {
        @Override public void run() {
            try { new DataUsageCollector(getApplicationContext()).poll(); } catch (Exception ignored) { }
            handler.postDelayed(this, DATA_POLL_MS);
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
            handler.postDelayed(this, SYNC_MS);
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
