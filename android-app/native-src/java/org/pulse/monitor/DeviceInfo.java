package org.pulse.monitor;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Collections;
import java.util.Enumeration;

/** Small static helpers for device-identifying info sent alongside the queued data. */
public class DeviceInfo {
    /** Best-effort local IPv4 address (Wi-Fi or cellular), for display in the dashboard's
     *  device list / settings. No network call — just reads interface info already known
     *  to the OS. Returns null if nothing usable is found (e.g. airplane mode). */
    public static String localIpv4() {
        try {
            Enumeration<NetworkInterface> intfs = NetworkInterface.getNetworkInterfaces();
            if (intfs == null) return null;
            for (NetworkInterface intf : Collections.list(intfs)) {
                if (!intf.isUp() || intf.isLoopback() || intf.isVirtual()) continue;
                Enumeration<InetAddress> addrs = intf.getInetAddresses();
                for (InetAddress addr : Collections.list(addrs)) {
                    if (!addr.isLoopbackAddress() && addr instanceof Inet4Address) {
                        return addr.getHostAddress();
                    }
                }
            }
        } catch (Exception ignored) { }
        return null;
    }
}
