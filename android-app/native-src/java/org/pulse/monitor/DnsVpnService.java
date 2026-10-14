package org.pulse.monitor;

import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.net.VpnService;
import android.os.Build;
import android.os.ParcelFileDescriptor;
import android.util.Log;

import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * A DNS-only VPN: it does NOT tunnel general traffic. It advertises itself as
 * the device's DNS server and routes ONLY that one address through the TUN
 * (addRoute for the fake resolver's /32), so every app's plain-DNS lookups
 * pass through here for logging while all other traffic (and DNS-over-HTTPS,
 * which this cannot see) continues over the real network untouched.
 *
 * For each intercepted query this: (1) logs the domain name being resolved,
 * (2) forwards the exact same query to a real upstream resolver over a
 * protected socket (so the forward itself doesn't loop back into the VPN),
 * and (3) relays the upstream's answer back to the querying app, so normal
 * DNS resolution keeps working for anything that uses the system resolver.
 */
public class DnsVpnService extends VpnService {
    private static final String TAG = "PulseDnsVpn";
    private static final String FAKE_DNS = "10.111.222.2";
    private static final String TUN_ADDR = "10.111.222.1";
    private static final int FAKE_DNS_PORT = 53;
    private static final String UPSTREAM_DNS = "1.1.1.1";

    private ParcelFileDescriptor tun;
    private Thread worker;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public static void start(Context ctx) {
        ctx.startService(new Intent(ctx, DnsVpnService.class));
    }
    public static void stop(Context ctx) {
        ctx.startService(new Intent(ctx, DnsVpnService.class).setAction("STOP"));
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && "STOP".equals(intent.getAction())) {
            teardown();
            stopSelf();
            return START_NOT_STICKY;
        }
        if (running.get()) return START_STICKY;
        try {
            establish();
        } catch (Exception e) {
            Log.w(TAG, "could not establish DNS VPN: " + e.getMessage());
            stopSelf();
        }
        return START_STICKY;
    }

    private void establish() {
        Builder b = new Builder();
        b.setSession("Pulse DNS monitor")
         .addAddress(TUN_ADDR, 24)
         .addDnsServer(FAKE_DNS)
         .addRoute(FAKE_DNS, 32)
         .setBlocking(true)
         .setMtu(1500);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) b.setMetered(false);
        tun = b.establish();
        if (tun == null) throw new IllegalStateException("VPN permission not granted");
        running.set(true);
        worker = new Thread(this::loop, "pulse-dns-vpn");
        worker.start();
    }

    private void teardown() {
        running.set(false);
        if (worker != null) { worker.interrupt(); worker = null; }
        if (tun != null) { try { tun.close(); } catch (IOException ignored) { } tun = null; }
    }

    @Override
    public void onDestroy() { teardown(); super.onDestroy(); }

    private void loop() {
        Db db = Db.get(getApplicationContext());
        FileInputStream in = new FileInputStream(tun.getFileDescriptor());
        FileOutputStream out = new FileOutputStream(tun.getFileDescriptor());
        byte[] buf = new byte[32767];
        while (running.get()) {
            int len;
            try { len = in.read(buf); } catch (IOException e) { break; }
            if (len <= 0) continue;
            try {
                handlePacket(buf, len, out, db);
            } catch (Exception e) {
                // Malformed/unsupported packet (IPv6, fragmented, non-UDP, etc.) — skip it.
            }
        }
        try { in.close(); } catch (IOException ignored) { }
        try { out.close(); } catch (IOException ignored) { }
    }

    /** Minimal IPv4+UDP parse/rewrite — no options, no fragmentation support (DNS queries don't need them). */
    private void handlePacket(byte[] buf, int len, FileOutputStream out, Db db) throws IOException {
        if (len < 28) return; // smaller than IPv4(20)+UDP(8) header
        int ipVer = (buf[0] >> 4) & 0xF;
        if (ipVer != 4) return;
        int ihl = (buf[0] & 0xF) * 4;
        int protocol = buf[9] & 0xFF;
        if (protocol != 17) return; // UDP only
        int udpOff = ihl;
        int srcPort = ((buf[udpOff] & 0xFF) << 8) | (buf[udpOff + 1] & 0xFF);
        int dstPort = ((buf[udpOff + 2] & 0xFF) << 8) | (buf[udpOff + 3] & 0xFF);
        if (dstPort != FAKE_DNS_PORT) return;
        int udpLen = ((buf[udpOff + 4] & 0xFF) << 8) | (buf[udpOff + 5] & 0xFF);
        int dnsOff = udpOff + 8;
        int dnsLen = udpLen - 8;
        if (dnsLen <= 0 || dnsOff + dnsLen > len) return;

        byte[] query = new byte[dnsLen];
        System.arraycopy(buf, dnsOff, query, 0, dnsLen);
        String qname = parseQName(query);
        if (qname != null && !qname.isEmpty()) {
            db.addBrowse(System.currentTimeMillis(), "dns", "", "", qname.toLowerCase(), "");
        }

        byte[] srcIp = new byte[4]; System.arraycopy(buf, 12, srcIp, 0, 4);
        byte[] dstIp = new byte[4]; System.arraycopy(buf, 16, dstIp, 0, 4);

        byte[] response = forwardToUpstream(query);
        if (response == null) return;

        byte[] reply = buildReply(srcIp, dstIp, srcPort, response);
        out.write(reply);
    }

    private byte[] forwardToUpstream(byte[] query) {
        DatagramSocket sock = null;
        try {
            sock = new DatagramSocket();
            protect(sock); // exempt this socket from the VPN's own routing, so it uses the real network
            sock.setSoTimeout(5000);
            InetAddress upstream = InetAddress.getByName(UPSTREAM_DNS);
            sock.send(new DatagramPacket(query, query.length, upstream, 53));
            byte[] resp = new byte[2048];
            DatagramPacket pkt = new DatagramPacket(resp, resp.length);
            sock.receive(pkt);
            byte[] out = new byte[pkt.getLength()];
            System.arraycopy(resp, 0, out, 0, pkt.getLength());
            return out;
        } catch (IOException e) {
            return null;
        } finally {
            if (sock != null) sock.close();
        }
    }

    /** Builds IPv4 + UDP wrapping the already-complete DNS response, addressed back to the querying app. */
    private byte[] buildReply(byte[] origSrcIp, byte[] origDstIp, int origSrcPort, byte[] dnsResponse) {
        int udpLen = 8 + dnsResponse.length;
        int totalLen = 20 + udpLen;
        byte[] p = new byte[totalLen];

        p[0] = (byte) 0x45; // version 4, IHL 5
        p[1] = 0;
        p[2] = (byte) (totalLen >> 8); p[3] = (byte) totalLen;
        p[4] = 0; p[5] = 0;  // identification
        p[6] = 0x40; p[7] = 0; // don't fragment
        p[8] = 64;  // TTL
        p[9] = 17;  // UDP
        p[10] = 0; p[11] = 0; // checksum placeholder
        System.arraycopy(origDstIp, 0, p, 12, 4); // reply source = the fake DNS server the app queried
        System.arraycopy(origSrcIp, 0, p, 16, 4); // reply dest = the original querying app's address

        int ipChecksum = checksum(p, 0, 20);
        p[10] = (byte) (ipChecksum >> 8); p[11] = (byte) ipChecksum;

        int udpOff = 20;
        p[udpOff] = (byte) (FAKE_DNS_PORT >> 8); p[udpOff + 1] = (byte) FAKE_DNS_PORT;
        p[udpOff + 2] = (byte) (origSrcPort >> 8); p[udpOff + 3] = (byte) origSrcPort;
        p[udpOff + 4] = (byte) (udpLen >> 8); p[udpOff + 5] = (byte) udpLen;
        p[udpOff + 6] = 0; p[udpOff + 7] = 0; // UDP checksum optional over IPv4 — left as 0 (disabled)
        System.arraycopy(dnsResponse, 0, p, udpOff + 8, dnsResponse.length);
        return p;
    }

    private int checksum(byte[] buf, int offset, int length) {
        int sum = 0;
        int i = offset;
        while (length > 1) {
            int word = ((buf[i] & 0xFF) << 8) | (buf[i + 1] & 0xFF);
            sum += word;
            i += 2;
            length -= 2;
        }
        if (length > 0) sum += (buf[i] & 0xFF) << 8;
        while ((sum >> 16) != 0) sum = (sum & 0xFFFF) + (sum >> 16);
        return (~sum) & 0xFFFF;
    }

    /** Pulls just the QNAME out of a raw DNS message's first question (ID(2) FLAGS(2) QD(2) ANS(2) NS(2) AR(2) = 12-byte header). */
    private String parseQName(byte[] msg) {
        if (msg.length < 13) return null;
        StringBuilder sb = new StringBuilder();
        int i = 12;
        while (i < msg.length) {
            int lbl = msg[i] & 0xFF;
            if (lbl == 0) break;
            if ((lbl & 0xC0) == 0xC0) break; // compression pointer — shouldn't appear in a question, bail out
            i++;
            if (i + lbl > msg.length) return null;
            if (sb.length() > 0) sb.append('.');
            sb.append(new String(msg, i, lbl, java.nio.charset.StandardCharsets.US_ASCII));
            i += lbl;
        }
        return sb.length() == 0 ? null : sb.toString();
    }
}
