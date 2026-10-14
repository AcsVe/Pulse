package org.pulse.monitor;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Classifies connectivity state into: connected / no_internet / failed / disconnected.
 *  - connected    : a network is validated (has real internet).
 *  - no_internet  : a network is up (wifi/cellular associated) but not validated,
 *                   confirmed by an active HTTP probe that also fails.
 *  - failed       : no network is up at all AND the last attempt to associate failed
 *                   (best-effort — Android doesn't expose "association failed" directly,
 *                   so this is inferred as a short disconnected spell right after losing
 *                   a network, before settling into a longer "disconnected").
 *  - disconnected : no network at all, sustained.
 */
public class NetMonitor {
    private final Context ctx;
    private final Db db;
    private ConnectivityManager cm;
    private ConnectivityManager.NetworkCallback callback;
    private HandlerThread thread;
    private Handler handler;
    private String currentKind = null;
    private long currentNetRowId = -1;
    private long currentSegmentStart = 0;
    private final Runnable probeTask = new Runnable() {
        @Override public void run() {
            probeAndMaybeSwitch();
            handler.postDelayed(this, 45_000);
        }
    };

    public NetMonitor(Context ctx) {
        this.ctx = ctx.getApplicationContext();
        this.db = Db.get(this.ctx);
    }

    public void start() {
        cm = (ConnectivityManager) ctx.getSystemService(Context.CONNECTIVITY_SERVICE);
        thread = new HandlerThread("pulse-net");
        thread.start();
        handler = new Handler(thread.getLooper());
        if (cm != null) {
            NetworkRequest req = new NetworkRequest.Builder()
                    .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build();
            callback = new ConnectivityManager.NetworkCallback() {
                @Override public void onAvailable(Network network) { handler.post(() -> probeAndMaybeSwitch()); }
                @Override public void onLost(Network network) { handler.post(() -> probeAndMaybeSwitch()); }
                @Override public void onCapabilitiesChanged(Network network, NetworkCapabilities caps) {
                    handler.post(() -> probeAndMaybeSwitch());
                }
            };
            try { cm.registerNetworkCallback(req, callback); } catch (Exception ignored) { }
        }
        handler.post(probeTask);
    }

    public void stop() {
        if (cm != null && callback != null) {
            try { cm.unregisterNetworkCallback(callback); } catch (Exception ignored) { }
        }
        if (handler != null) handler.removeCallbacks(probeTask);
        if (thread != null) thread.quitSafely();
        if (currentNetRowId >= 0) db.closeNet(currentNetRowId, System.currentTimeMillis());
    }

    private void probeAndMaybeSwitch() {
        String kind = classify();
        long now = System.currentTimeMillis();
        sampleWifiSpeed();
        // A "disconnected" reading that follows a very short-lived connected/no_internet
        // spell (<10s) usually means a connection attempt bounced rather than the radio
        // being truly idle — record that single event as "failed" instead.
        if ("disconnected".equals(kind) && currentKind != null && !"disconnected".equals(currentKind)
                && !"failed".equals(currentKind) && (now - currentSegmentStart) < 10_000) {
            kind = "failed";
        }
        if (kind.equals(currentKind)) return; // no state change
        if (currentNetRowId >= 0) db.closeNet(currentNetRowId, now);
        currentKind = kind;
        currentSegmentStart = now;
        currentNetRowId = db.openNet(kind, transportName(), now, "");
    }

    private String classify() {
        boolean hasNetwork = false;
        boolean validatedByOs = false;
        if (cm != null) {
            Network active = cm.getActiveNetwork();
            if (active != null) {
                NetworkCapabilities caps = cm.getNetworkCapabilities(active);
                if (caps != null) {
                    hasNetwork = true;
                    validatedByOs = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
                }
            }
        }
        if (!hasNetwork) return "disconnected";
        if (validatedByOs) return "connected";
        // OS hasn't validated (or doesn't say) — confirm with an active probe.
        boolean probeOk = httpProbeOk();
        return probeOk ? "connected" : "no_internet";
    }

    private boolean httpProbeOk() {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL("https://connectivitycheck.gstatic.com/generate_204").openConnection();
            c.setConnectTimeout(6000);
            c.setReadTimeout(6000);
            c.setInstanceFollowRedirects(false);
            int code = c.getResponseCode();
            c.disconnect();
            return code == 204 || code == 200;
        } catch (IOException e) {
            return false;
        }
    }

    /** Wi-Fi link speed (Mbps), the figure the OS reports for the current
     *  association — not a throughput measurement. Stored in the kv store so
     *  Uploader can ship the latest reading with the next sync, the same way
     *  it ships the local IP address. Only meaningful while on Wi-Fi; left
     *  unset (and so unreported) otherwise. */
    private void sampleWifiSpeed() {
        if (!"wifi".equals(transportName())) return;
        try {
            WifiManager wm = (WifiManager) ctx.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            if (wm == null) return;
            int mbps = wm.getConnectionInfo().getLinkSpeed(); // WifiManager always reports Mbps
            if (mbps > 0) db.put("wifi_mbps", String.valueOf(mbps));
        } catch (Exception ignored) { }
    }

    private String transportName() { return currentTransport(ctx); }

    /** Static variant other collectors (data usage, etc.) can call without an instance. */
    public static String currentTransport(Context ctx) {
        ConnectivityManager cm = (ConnectivityManager) ctx.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return "";
        Network active = cm.getActiveNetwork();
        if (active == null) return "";
        NetworkCapabilities caps = cm.getNetworkCapabilities(active);
        if (caps == null) return "";
        if (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) return "wifi";
        if (caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)) return "cellular";
        if (caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) return "ethernet";
        return "";
    }
}
