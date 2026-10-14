package org.pulse.monitor;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.util.DisplayMetrics;
import android.view.WindowManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.ByteBuffer;

/**
 * Captures the device's own screen (MediaProjection) and streams it to the
 * server as a sequence of JPEG snapshots (not real video — a simple "refresh
 * every ~800ms" loop, which keeps this on the same plain-HTTP infrastructure
 * as the rest of the app instead of adding a WebSocket/RTC stack), and polls
 * for queued remote-control commands, executed via PulseAccessibilityService.
 *
 * Lifecycle: started once the device owner grants the screen-capture consent
 * from the app's own setup UI (PulsePlugin#requestScreenCapture — Android
 * requires that consent to come from an on-device system dialog; it cannot be
 * granted remotely or silently, and is lost if this process dies, needing a
 * fresh grant). Once running, it only *captures and uploads* while the
 * dashboard has started a remote session (polled via /api/v1/remote-state);
 * otherwise it idles cheaply so the persistent grant doesn't drain battery.
 */
public class ScreenCaptureService extends Service {
    private static final String CHANNEL_ID = "pulse_remote";
    private static final int NOTIF_ID = 1002;
    public static final String EXTRA_RESULT_CODE = "resultCode";
    public static final String EXTRA_RESULT_DATA = "resultData";
    private static final long WATCH_MS = 1500;   // how often to check remote-state when idle
    private static final long FRAME_MS = 400;     // how often to capture+upload while active
    private static final long CMD_MS = 300;       // how often to poll for commands while active

    private MediaProjection projection;
    private VirtualDisplay virtualDisplay;
    private ImageReader imageReader;
    private HandlerThread thread;
    private Handler handler;
    private int width, height, density;
    private volatile boolean active = false;

    public static void start(Context ctx, int resultCode, Intent data) {
        Intent i = new Intent(ctx, ScreenCaptureService.class);
        i.putExtra(EXTRA_RESULT_CODE, resultCode);
        i.putExtra(EXTRA_RESULT_DATA, data);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) ctx.startForegroundService(i);
        else ctx.startService(i);
    }

    public static void stop(Context ctx) {
        ctx.stopService(new Intent(ctx, ScreenCaptureService.class));
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, buildNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
        } else {
            startForeground(NOTIF_ID, buildNotification());
        }
        thread = new HandlerThread("pulse-screencap");
        thread.start();
        handler = new Handler(thread.getLooper());
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && projection == null) {
            int resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0);
            Intent data = intent.getParcelableExtra(EXTRA_RESULT_DATA);
            if (data != null) {
                handler.post(() -> setUpProjection(resultCode, data));
                handler.post(watchTask);
            }
        }
        return START_STICKY;
    }

    private final Runnable watchTask = new Runnable() {
        @Override public void run() {
            boolean wasActive = active;
            active = checkRemoteActive();
            if (active && !wasActive) {
                handler.post(frameTask);
                handler.post(cmdTask);
            }
            handler.postDelayed(this, WATCH_MS);
        }
    };
    private final Runnable frameTask = new Runnable() {
        @Override public void run() {
            if (!active) return; // stop this loop; watchTask will restart it next time active flips on
            try { captureAndUpload(); } catch (Exception ignored) { }
            handler.postDelayed(this, FRAME_MS);
        }
    };
    private final Runnable cmdTask = new Runnable() {
        @Override public void run() {
            if (!active) return;
            try { pollAndRunCommands(); } catch (Exception ignored) { }
            handler.postDelayed(this, CMD_MS);
        }
    };

    private void setUpProjection(int resultCode, Intent data) {
        MediaProjectionManager mpm = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        if (mpm == null) return;
        try {
            projection = mpm.getMediaProjection(resultCode, data);
        } catch (Exception e) {
            return; // consent token invalid/expired — needs a fresh grant from the app UI
        }
        if (projection == null) return;
        WindowManager wm = (WindowManager) getSystemService(Context.WINDOW_SERVICE);
        DisplayMetrics dm = new DisplayMetrics();
        if (wm != null) wm.getDefaultDisplay().getRealMetrics(dm);
        density = dm.densityDpi > 0 ? dm.densityDpi : 160;
        int rawW = dm.widthPixels > 0 ? dm.widthPixels : 1080;
        int rawH = dm.heightPixels > 0 ? dm.heightPixels : 1920;
        // Cap to ~720p-equivalent — a remote-control view doesn't need native
        // resolution, and this keeps JPEGs small (cheap, frequent uploads).
        float scale = Math.min(1f, 720f / Math.max(rawW, rawH));
        width = Math.max(2, Math.round(rawW * scale));
        height = Math.max(2, Math.round(rawH * scale));
        imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
        virtualDisplay = projection.createVirtualDisplay("pulse-screen", width, height, density,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, imageReader.getSurface(), null, handler);
    }

    private boolean checkRemoteActive() {
        Db db = Db.get(this);
        String serverUrl = db.getStr("server_url", null);
        String token = db.getStr("device_token", null);
        if (serverUrl == null || token == null) return false;
        try {
            JSONObject res = get(serverUrl + "/api/v1/remote-state", token);
            return res != null && res.optBoolean("active", false);
        } catch (IOException e) {
            return false;
        }
    }

    private void captureAndUpload() throws IOException {
        if (imageReader == null) return;
        byte[] jpeg = captureJpeg();
        if (jpeg == null) return;
        Db db = Db.get(this);
        String serverUrl = db.getStr("server_url", null);
        String token = db.getStr("device_token", null);
        if (serverUrl == null || token == null) return;
        HttpURLConnection conn = (HttpURLConnection) new URL(serverUrl + "/api/v1/screen?w=" + width + "&h=" + height).openConnection();
        try {
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(8000);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "image/jpeg");
            conn.setRequestProperty("Authorization", "Bearer " + token);
            try (OutputStream os = conn.getOutputStream()) { os.write(jpeg); }
            conn.getResponseCode(); // drain; ignore result, next tick will just try again
        } finally {
            conn.disconnect();
        }
    }

    private byte[] captureJpeg() {
        Image image;
        try {
            image = imageReader.acquireLatestImage();
        } catch (Exception e) {
            return null;
        }
        if (image == null) return null;
        try {
            Image.Plane[] planes = image.getPlanes();
            ByteBuffer buffer = planes[0].getBuffer();
            int pixelStride = planes[0].getPixelStride();
            int rowStride = planes[0].getRowStride();
            int rowPadding = rowStride - pixelStride * width;
            Bitmap bitmap = Bitmap.createBitmap(width + rowPadding / pixelStride, height, Bitmap.Config.ARGB_8888);
            bitmap.copyPixelsFromBuffer(buffer);
            Bitmap cropped = width == bitmap.getWidth() ? bitmap : Bitmap.createBitmap(bitmap, 0, 0, width, height);
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            cropped.compress(Bitmap.CompressFormat.JPEG, 55, bos);
            if (cropped != bitmap) cropped.recycle();
            bitmap.recycle();
            return bos.toByteArray();
        } finally {
            image.close();
        }
    }

    private void pollAndRunCommands() throws IOException {
        Db db = Db.get(this);
        String serverUrl = db.getStr("server_url", null);
        String token = db.getStr("device_token", null);
        if (serverUrl == null || token == null) return;
        JSONObject res = get(serverUrl + "/api/v1/commands", token);
        if (res == null) return;
        JSONArray cmds = res.optJSONArray("commands");
        if (cmds == null) return;
        PulseAccessibilityService svc = PulseAccessibilityService.get();
        if (svc == null) return; // accessibility not enabled — commands are silently dropped
        for (int i = 0; i < cmds.length(); i++) {
            JSONObject c = cmds.optJSONObject(i);
            if (c == null) continue;
            String action = c.optString("action", "");
            JSONObject p = c.optJSONObject("params");
            if (p == null) p = new JSONObject();
            switch (action) {
                case "tap": svc.tap(p.optInt("x"), p.optInt("y")); break;
                case "swipe": svc.swipe(p.optInt("x"), p.optInt("y"), p.optInt("x2"), p.optInt("y2"), p.optInt("duration", 300)); break;
                case "text": svc.setFocusedText(p.optString("text", "")); break;
                case "back": case "home": case "recents": svc.globalAction(action); break;
                default: break;
            }
        }
    }

    private JSONObject get(String urlStr, String token) throws IOException {
        HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
        try {
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(6000);
            conn.setReadTimeout(6000);
            conn.setRequestProperty("Authorization", "Bearer " + token);
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) return null;
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[2048];
            int n;
            java.io.InputStream is = conn.getInputStream();
            while ((n = is.read(buf)) != -1) bos.write(buf, 0, n);
            return new JSONObject(bos.toString("UTF-8"));
        } catch (org.json.JSONException je) {
            return null;
        } finally {
            conn.disconnect();
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        active = false;
        if (handler != null) {
            handler.removeCallbacks(watchTask);
            handler.removeCallbacks(frameTask);
            handler.removeCallbacks(cmdTask);
        }
        if (virtualDisplay != null) virtualDisplay.release();
        if (imageReader != null) imageReader.close();
        if (projection != null) projection.stop();
        if (thread != null) thread.quitSafely();
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm == null) return;
        NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "Pulse — Remote", NotificationManager.IMPORTANCE_LOW);
        ch.setDescription("Pulse remote-control capability is enabled on this device");
        ch.setShowBadge(false);
        nm.createNotificationChannel(ch);
    }

    private Notification buildNotification() {
        Intent showIntent = new Intent(this, ShowIconReceiver.class);
        android.app.PendingIntent pi = android.app.PendingIntent.getBroadcast(this, 1, showIntent,
                android.app.PendingIntent.FLAG_IMMUTABLE | android.app.PendingIntent.FLAG_UPDATE_CURRENT);
        Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL_ID) : new Notification.Builder(this);
        b.setContentTitle("Pulse")
         .setContentText("إمكانية التحكم عن بعد مفعّلة")
         .setSmallIcon(android.R.drawable.ic_menu_info_details)
         .setOngoing(true)
         .setContentIntent(pi);
        return b.build();
    }
}
