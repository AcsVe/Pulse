package org.pulse.monitor;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/** Talks to the Pulse server: /api/v1/enroll and /api/v1/ingest. */
public class Uploader {
    private static final int BATCH = 300;
    private static final int TIMEOUT = 15000;

    public static class EnrollResult { public String token; public long deviceId; public String name; }

    public static EnrollResult enroll(Context ctx, String serverUrl, String code) throws IOException {
        JSONObject body = new JSONObject();
        try {
            body.put("code", code);
            body.put("model", Build.MANUFACTURER + " " + Build.MODEL);
            body.put("os", String.valueOf(Build.VERSION.SDK_INT));
            body.put("app", appVersionName(ctx));
        } catch (Exception ignored) { }
        JSONObject res = post(serverUrl + "/api/v1/enroll", body, null);
        if (res == null) throw new IOException("empty response");
        EnrollResult r = new EnrollResult();
        r.token = res.optString("token", null);
        r.deviceId = res.optLong("deviceId");
        r.name = res.optString("name", "");
        if (r.token == null) throw new IOException(res.optString("error", "enroll failed"));
        return r;
    }

    /** Pulls up to BATCH unsynced rows per table, posts them, marks synced on success. Safe to call repeatedly. */
    public static boolean syncOnce(Context ctx) {
        Db db = Db.get(ctx);
        String serverUrl = db.getStr("server_url", null);
        String token = db.getStr("device_token", null);
        if (serverUrl == null || token == null) return false;

        JSONObject body = new JSONObject();
        List<Long> usageIds = new ArrayList<>(), netIds = new ArrayList<>(), browseIds = new ArrayList<>(),
                dataIds = new ArrayList<>(), memIds = new ArrayList<>();
        try {
            JSONArray usage = new JSONArray();
            try (Cursor c = db.queryPending("usage_q", new String[]{"id", "package", "label", "start_ts", "end_ts"}, BATCH)) {
                while (c.moveToNext()) {
                    JSONObject o = new JSONObject();
                    o.put("package", c.getString(1)); o.put("label", c.getString(2));
                    o.put("start", c.getLong(3)); o.put("end", c.getLong(4));
                    usage.put(o); usageIds.add(c.getLong(0));
                }
            }
            JSONArray net = new JSONArray();
            try (Cursor c = db.queryPending("net_q", new String[]{"id", "kind", "transport", "start_ts", "end_ts", "detail", "open_row"}, BATCH)) {
                while (c.moveToNext()) {
                    if (c.getInt(6) == 1) continue; // don't ship still-open rows yet
                    JSONObject o = new JSONObject();
                    o.put("kind", c.getString(1)); o.put("transport", c.getString(2));
                    o.put("start", c.getLong(3)); o.put("end", c.isNull(4) ? JSONObject.NULL : c.getLong(4));
                    o.put("detail", c.getString(5) == null ? "" : c.getString(5));
                    net.put(o); netIds.add(c.getLong(0));
                }
            }
            JSONArray browse = new JSONArray();
            try (Cursor c = db.queryPending("browse_q", new String[]{"id", "ts", "source", "app", "url", "domain", "title"}, BATCH)) {
                while (c.moveToNext()) {
                    JSONObject o = new JSONObject();
                    o.put("ts", c.getLong(1)); o.put("source", c.getString(2)); o.put("app", c.getString(3));
                    o.put("url", c.getString(4)); o.put("domain", c.getString(5)); o.put("title", c.getString(6));
                    browse.put(o); browseIds.add(c.getLong(0));
                }
            }
            JSONArray dataUsage = new JSONArray();
            try (Cursor c = db.queryPending("data_q", new String[]{"id", "package", "label", "ts", "rx", "tx", "transport"}, BATCH)) {
                while (c.moveToNext()) {
                    JSONObject o = new JSONObject();
                    o.put("package", c.getString(1)); o.put("label", c.getString(2) == null ? "" : c.getString(2));
                    o.put("ts", c.getLong(3)); o.put("rx", c.getLong(4)); o.put("tx", c.getLong(5));
                    o.put("transport", c.getString(6) == null ? "" : c.getString(6));
                    dataUsage.put(o); dataIds.add(c.getLong(0));
                }
            }
            JSONArray memory = new JSONArray();
            try (Cursor c = db.queryPending("mem_q", new String[]{"id", "ts", "used_mb", "total_mb"}, BATCH)) {
                while (c.moveToNext()) {
                    JSONObject o = new JSONObject();
                    o.put("ts", c.getLong(1)); o.put("usedMb", c.getLong(2)); o.put("totalMb", c.getLong(3));
                    memory.put(o); memIds.add(c.getLong(0));
                }
            }

            // Note: no early-return when every queue above is empty — this call
            // also doubles as the device's "I'm alive" heartbeat (last_seen,
            // connection type, permission status), which used to go stale and
            // make an idle-but-online phone look "Offline" on the dashboard.
            body.put("usage", usage); body.put("net", net); body.put("browse", browse);
            body.put("dataUsage", dataUsage); body.put("memory", memory);
            body.put("model", Build.MANUFACTURER + " " + Build.MODEL);
            body.put("os", String.valueOf(Build.VERSION.SDK_INT));
            body.put("app", appVersionName(ctx));
            String ip = DeviceInfo.localIpv4();
            if (ip != null) body.put("ip", ip);
            String wifiMbps = db.getStr("wifi_mbps", null);
            if (wifiMbps != null) body.put("wifiMbps", Integer.parseInt(wifiMbps));
            String connType = NetMonitor.currentTransport(ctx);
            body.put("connType", connType.isEmpty() ? "none" : connType);
            body.put("accessibilityEnabled", PulsePlugin.isAccessibilityEnabled(ctx));
        } catch (Exception e) {
            return false;
        }

        try {
            JSONObject res = post(serverUrl + "/api/v1/ingest", body, token);
            if (res == null || !res.optBoolean("ok", false)) return false;
            db.markSynced("usage_q", usageIds);
            db.markSynced("net_q", netIds);
            db.markSynced("browse_q", browseIds);
            db.markSynced("data_q", dataIds);
            db.markSynced("mem_q", memIds);
            db.put("last_sync", String.valueOf(System.currentTimeMillis()));
            // The dashboard's per-device "update interval" setting (see the
            // Devices tab) rides along on every sync response, so the device
            // picks up a change within one sync cycle without a dedicated
            // polling endpoint for it.
            if (res.has("pollIntervalS")) db.put("poll_interval_s", String.valueOf(res.optInt("pollIntervalS", 60)));
            return true;
        } catch (IOException e) {
            return false;
        }
    }

    /** The app's own version name (e.g. "1.0.0"), read at runtime via
     * PackageManager instead of the generated BuildConfig class — Capacitor's
     * default build.gradle doesn't turn on the `buildConfig` feature flag
     * that AGP 8+ requires for BuildConfig fields to exist. */
    private static String appVersionName(Context ctx) {
        try {
            PackageInfo pi = ctx.getPackageManager().getPackageInfo(ctx.getPackageName(), 0);
            return pi.versionName != null ? pi.versionName : "";
        } catch (PackageManager.NameNotFoundException e) {
            return "";
        }
    }

    public static void requestImmediateSync(Context ctx) {
        Intent i = new Intent(ctx, CollectorService.class);
        i.setAction(CollectorService.ACTION_SYNC_NOW);
        try { ctx.startService(i); } catch (Exception ignored) { }
    }

    private static JSONObject post(String urlStr, JSONObject body, String bearer) throws IOException {
        HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
        try {
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(TIMEOUT);
            conn.setReadTimeout(TIMEOUT);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            if (bearer != null) conn.setRequestProperty("Authorization", "Bearer " + bearer);
            byte[] data = body.toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream os = conn.getOutputStream()) { os.write(data); }
            int code = conn.getResponseCode();
            InputStream is = code >= 200 && code < 300 ? conn.getInputStream() : conn.getErrorStream();
            String text = is == null ? "" : readAll(is);
            if (code < 200 || code >= 300) throw new IOException("http " + code + ": " + text);
            return new JSONObject(text);
        } catch (org.json.JSONException je) {
            throw new IOException("bad json response", je);
        } finally {
            conn.disconnect();
        }
    }

    private static String readAll(InputStream is) throws IOException {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = is.read(buf)) != -1) bos.write(buf, 0, n);
        return bos.toString("UTF-8");
    }
}
