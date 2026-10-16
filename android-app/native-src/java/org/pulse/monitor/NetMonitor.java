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
        currentNetRowId = db.openNet(kind, transportName(), now, describeDetail(kind));
    }

    /** A one-line human-readable reason for this state, shown in the dashboard's
     *  net-events "Detail" column — previously always sent as "" (every row
     *  looked blank there, including for drops and outages, with nothing to
     *  say why). Best-effort: whatever's cheaply available from the APIs we
     *  already queried for classify()/transportName(), not a full diagnostic. */
    private String describeDetail(String kind) {
        switch (kind) {
            case "connected": {
                if (!"wifi".equals(transportName())) return "";
                String band = db.getStr("wifi_band", null);
                String mbps = db.getStr("wifi_mbps", null);
                if (band == null && mbps == null) return "";
                StringBuilder sb = new StringBuilder("Wi-Fi");
                if (band != null) sb.append(' ').append(band);
                if (mbps != null) sb.append(", ").append(mbps).append(" Mbps");
                return sb.toString();
            }
            case "no_internet":
                return transportName().isEmpty()
                        ? "Network up but not validated"
                        : transportName() + " associated, but no internet (probe failed)";
            case "failed":
                return "Connection attempt dropped within 10s of starting";
            case "disconnected":
            default:
                return "";
        }
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
            android.net.wifi.WifiInfo info = wm.getConnectionInfo();
            int mbps = info.getLinkSpeed(); // WifiManager always reports Mbps
            if (mbps > 0) db.put("wifi_mbps", String.valueOf(mbps));
            // getFrequency() (MHz) is the only reliable, OEM-independent way to tell a
            // 2.4GHz association from 5GHz/6GHz — the band isn't exposed anywhere else.
            int freq = info.getFrequency();
            String band = freq <= 0 ? null : freq < 3000 ? "2.4GHz" : freq < 5925 ? "5GHz" : "6GHz";
            if (band != null) db.put("wifi_band", band);
        } catch (Exception ignored) { }
    }

    private String transportName() { return currentTransport(ctx); }

    /** Static variant other collectors (data usage, etc.) can call without an instance.
     *
     *  getActiveNetwork() normally returns the wifi/cellular/ethernet network directly —
     *  but Pulse runs its own always-on local VPN (DnsVpnService, for DNS-based browse
     *  capture), and once that's up, Android reports *it* as the active network instead.
     *  A VPN's own NetworkCapabilities only advertise TRANSPORT_VPN, not the underlying
     *  radio, so every caller here (sync's connType, the per-device "connection type" and
     *  Wi-Fi speed/band shown on the dashboard, and each net-event's transport field) was
     *  silently going blank the moment the DNS monitor started — which for most phones is
     *  "basically always". When the active network is a VPN, walk the underlying networks
     *  (cm.getAllNetworks()) and report whichever one is actually carrying traffic instead. */
    public static String currentTransport(Context ctx) {
        ConnectivityManager cm = (ConnectivityManager) ctx.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return "";
        Network active = cm.getActiveNetwork();
        if (active == null) return "";
        NetworkCapabilities caps = cm.getNetworkCapabilities(active);
        if (caps == null) return "";
        String fromCaps = transportFromCaps(caps);
        if (fromCaps != null) return fromCaps;
        if (caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) {
            String underlying = underlyingTransport(cm);
            if (underlying != null) return underlying;
        }
        return "";
    }

    private static String transportFromCaps(NetworkCapabilities caps) {
        if (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) return "wifi";
        if (caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)) return "cellular";
        if (caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) return "ethernet";
        return null;
    }

    /** Best real (non-VPN) network currently up, preferring one the OS has validated. */
    private static String underlyingTransport(ConnectivityManager cm) {
        Network[] nets;
        try { nets = cm.getAllNetworks(); } catch (Exception e) { return null; }
        String fallback = null;
        for (Network n : nets) {
            NetworkCapabilities c = cm.getNetworkCapabilities(n);
            if (c == null || c.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) continue;
            String t = transportFromCaps(c);
            if (t == null) continue;
            if (c.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) return t;
            if (fallback == null) fallback = t;
        }
        return fallback;
    }
}
