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
    private static final long WATCH_MS = 1000;   // how often to check remote-state when idle
    private static final long FRAME_MS = 250;     // how often to capture+upload while active
    private static final long CMD_MS = 150;       // how often to poll for commands while active

    private MediaProjection projection;
    private VirtualDisplay virtualDisplay;
    private ImageReader imageReader;
    private HandlerThread thread;
    private Handler handler;
    private int width, height, density;
    // Real (un-downscaled) screen size, in the same pixel space the
    // accessibility service's dispatchGesture() expects. width/height above
    // are the capped-to-720p capture dimensions sent to the dashboard —
    // tap/swipe coordinates arrive back in THAT space and must be scaled up
    // to these before dispatch, or every touch lands at `width/rawWidth` of
    // where the dashboard image was actually tapped (see tap()/swipe() below).
    private int rawWidth, rawHeight;
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
            JSONObject state = fetchRemoteState();
            active = state != null && state.optBoolean("active", false);
            if (active && !wasActive) {
                handler.post(frameTask);
                handler.post(cmdTask);
            }
            // Fire-and-forget on the same background thread — the server only
            // asks for this once per fresh/stale remote session (see
            // /api/v1/remote-state's needApps), not on every watch tick.
            if (state != null && state.optBoolean("needApps", false)) {
                try { Uploader.uploadApps(ScreenCaptureService.this); } catch (Exception ignored) { }
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
        rawWidth = rawW; rawHeight = rawH;
        // Cap to ~720p-equivalent — a remote-control view doesn't need native
        // resolution, and this keeps JPEGs small (cheap, frequent uploads).
        float scale = Math.min(1f, 720f / Math.max(rawW, rawH));
        width = Math.max(2, Math.round(rawW * scale));
        height = Math.max(2, Math.round(rawH * scale));
        imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
        virtualDisplay = projection.createVirtualDisplay("pulse-screen", width, height, density,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, imageReader.getSurface(), null, handler);
    }

    private JSONObject fetchRemoteState() {
        Db db = Db.get(this);
        String serverUrl = db.getStr("server_url", null);
        String token = db.getStr("device_token", null);
        if (serverUrl == null || token == null) return null;
        try {
            return get(serverUrl + "/api/v1/remote-state", token);
        } catch (IOException e) {
            return null;
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

    private int scaleX(int x) { return width > 0 && rawWidth > 0 ? Math.round(x * (rawWidth / (float) width)) : x; }
    private int scaleY(int y) { return height > 0 && rawHeight > 0 ? Math.round(y * (rawHeight / (float) height)) : y; }

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
        for (int i = 0; i < cmds.length(); i++) {
            JSONObject c = cmds.optJSONObject(i);
            if (c == null) continue;
            String action = c.optString("action", "");
            JSONObject p = c.optJSONObject("params");
            if (p == null) p = new JSONObject();
            // launch/close don't need the accessibility service — they go
            // through PackageManager/ActivityManager directly — so they still
            // work even if accessibility isn't bound. Everything else (taps,
            // swipes, typing, back/home/recents) genuinely needs it.
            if ("launch".equals(action)) { launchApp(p.optString("pkg", "")); continue; }
            if ("close".equals(action)) { closeApp(p.optString("pkg", ""), svc); continue; }
            if (svc == null) continue; // accessibility not enabled — the rest are silently dropped
            switch (action) {
                // x/y/x2/y2 arrive in the downscaled capture's pixel space (the
                // dashboard computes them against the screenshot it's showing,
                // which is `width`x`height`, not the device's real resolution) —
                // scale them up to rawWidth/rawHeight before dispatching, or
                // every tap/swipe lands at the wrong spot (worse the further
                // from the top-left corner it is).
                case "tap": svc.tap(scaleX(p.optInt("x")), scaleY(p.optInt("y")), p.optInt("duration", 80)); break;
                case "swipe": svc.swipe(scaleX(p.optInt("x")), scaleY(p.optInt("y")),
                        scaleX(p.optInt("x2")), scaleY(p.optInt("y2")), p.optInt("duration", 300)); break;
                case "text": svc.setFocusedText(p.optString("text", "")); break;
                case "back": case "home": case "recents": svc.globalAction(action); break;
                // Two-finger gesture (pinch zoom or a two-finger pan/scroll) —
                // one generic relay covers both, since what the phone does
                // with two concurrent moving touch points depends on the app
                // underneath, not on us labeling the gesture. "touches" is a
                // JSON array of [startX,startY,endX,endY] per finger, in the
                // same downscaled capture space as tap/swipe above.
                case "pinch": {
                    JSONArray touches = p.optJSONArray("touches");
                    if (touches == null) break;
                    int n = Math.min(touches.length(), 2); // dispatchGesture caps concurrent strokes low enough that only 2 is reliable
                    int[][] strokes = new int[n][4];
                    for (int ti = 0; ti < n; ti++) {
                        JSONArray t = touches.optJSONArray(ti);
                        if (t == null || t.length() < 4) continue;
                        strokes[ti][0] = scaleX(t.optInt(0));
                        strokes[ti][1] = scaleY(t.optInt(1));
                        strokes[ti][2] = scaleX(t.optInt(2));
                        strokes[ti][3] = scaleY(t.optInt(3));
                    }
                    svc.multiTouch(strokes, p.optInt("duration", 200));
                    break;
                }
                default: break;
            }
        }
    }

    private void launchApp(String pkg) {
        if (pkg.isEmpty()) return;
        try {
            Intent i = getPackageManager().getLaunchIntentForPackage(pkg);
            if (i == null) return; // uninstalled since the app list was fetched, or not launchable
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            startActivity(i);
        } catch (Exception ignored) { }
    }

    /** The real ceiling of what a normal (non Device-Owner, non-root) app can
     *  do to ANOTHER app's process on modern Android: there is no public API
     *  for a true force-stop (that needs the signature-level
     *  FORCE_STOP_PACKAGES permission, which only system/privileged apps get).
     *  This is the same thing swiping an app off the Recents screen does —
     *  send it to the background, then let the OS reclaim its now-cached
     *  process — not a guaranteed kill for an app that's actively holding a
     *  wakelock or running a foreground service of its own. */
    private void closeApp(String pkg, PulseAccessibilityService svc) {
        if (pkg.isEmpty()) return;
        if (svc != null) svc.globalAction("home");
        try {
            android.app.ActivityManager am = (android.app.ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
            if (am != null) am.killBackgroundProcesses(pkg);
        } catch (Exception ignored) { }
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
