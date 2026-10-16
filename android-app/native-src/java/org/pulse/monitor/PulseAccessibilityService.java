package org.pulse.monitor;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.graphics.Path;
import android.os.Build;
import android.os.Bundle;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.HashMap;
import java.util.Map;

/**
 * Reads the address bar of common Android browsers to log visited URLs, as a
 * second, independent signal alongside the DNS-based capture (DnsVpnService) —
 * the DNS path sees the domain for every app, this path sees the exact URL
 * (with path) but only for browsers whose address-bar view it recognizes.
 */
public class PulseAccessibilityService extends AccessibilityService {
    // resource-id of the omnibox/address-bar TextView per known browser package.
    private static final Map<String, String> ADDRESS_BAR_ID = new HashMap<>();
    static {
        ADDRESS_BAR_ID.put("com.android.chrome", "com.android.chrome:id/url_bar");
        ADDRESS_BAR_ID.put("com.chrome.beta", "com.chrome.beta:id/url_bar");
        ADDRESS_BAR_ID.put("com.chrome.dev", "com.chrome.dev:id/url_bar");
        ADDRESS_BAR_ID.put("com.android.browser", "com.android.browser:id/url");
        ADDRESS_BAR_ID.put("org.mozilla.firefox", "org.mozilla.firefox:id/mozac_browser_toolbar_url_view");
        ADDRESS_BAR_ID.put("com.sec.android.app.sbrowser", "com.sec.android.app.sbrowser:id/location_bar_edit_text");
        ADDRESS_BAR_ID.put("com.microsoft.emmx", "com.microsoft.emmx:id/url_bar");
        ADDRESS_BAR_ID.put("com.opera.browser", "com.opera.browser:id/url_field");
        ADDRESS_BAR_ID.put("com.UCMobile.intl", "com.UCMobile.intl:id/address");
        ADDRESS_BAR_ID.put("com.mi.globalbrowser", "com.mi.globalbrowser:id/url");
        ADDRESS_BAR_ID.put("com.kiwibrowser.browser", "com.kiwibrowser.browser:id/url_bar");
        ADDRESS_BAR_ID.put("com.brave.browser", "com.brave.browser:id/url_bar");
    }

    private Db db;
    private String lastUrl = "";
    private long lastAt = 0;

    // Set while the service is bound, cleared on destroy — lets RemoteControlPoller
    // (a plain background task, not itself an AccessibilityService) reach this
    // instance to execute queued remote-control commands (see README's "remote
    // control" section: this is the input-injection half of it).
    private static volatile PulseAccessibilityService instance;
    public static PulseAccessibilityService get() { return instance; }

    @Override
    public void onCreate() {
        super.onCreate();
        db = Db.get(getApplicationContext());
    }

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
    }

    @Override
    public boolean onUnbind(android.content.Intent intent) {
        instance = null;
        return super.onUnbind(intent);
    }

    // ── remote control: input injection ─────────────────────────────────
    /** durationMs lets a held-down tap on the dashboard register as an
     *  actual long-press on the phone (e.g. to open a context menu or
     *  start dragging an icon) instead of always being a fixed quick tap —
     *  see ScreenCaptureService's "tap" case, which forwards how long the
     *  admin actually held the click/touch down. */
    public boolean tap(int x, int y, int durationMs) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return false;
        Path path = new Path();
        path.moveTo(x, y);
        long d = Math.max(40, Math.min(durationMs, 1500));
        GestureDescription.StrokeDescription stroke = new GestureDescription.StrokeDescription(path, 0, d);
        return dispatchGesture(new GestureDescription.Builder().addStroke(stroke).build(), null, null);
    }

    public boolean swipe(int x1, int y1, int x2, int y2, int durationMs) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return false;
        Path path = new Path();
        path.moveTo(x1, y1);
        path.lineTo(x2, y2);
        long d = Math.max(50, Math.min(durationMs, 3000));
        GestureDescription.StrokeDescription stroke = new GestureDescription.StrokeDescription(path, 0, d);
        return dispatchGesture(new GestureDescription.Builder().addStroke(stroke).build(), null, null);
    }

    public boolean globalAction(String name) {
        int action;
        switch (name) {
            case "back": action = GLOBAL_ACTION_BACK; break;
            case "home": action = GLOBAL_ACTION_HOME; break;
            case "recents": action = GLOBAL_ACTION_RECENTS; break;
            default: return false;
        }
        return performGlobalAction(action);
    }

    /** Sets text on whichever editable field currently has input focus — there is
     *  no public API to "type" characters into an arbitrary app, so this is the
     *  practical equivalent: find the focused field, replace its text. */
    public boolean setFocusedText(String text) {
        AccessibilityNodeInfo node = findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
        if (node == null) return false;
        try {
            Bundle args = new Bundle();
            args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
            return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
        } finally {
            node.recycle();
        }
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null) return;
        CharSequence pkgCs = event.getPackageName();
        if (pkgCs == null) return;
        String pkg = pkgCs.toString();
        String fieldId = ADDRESS_BAR_ID.get(pkg);
        if (fieldId == null) return;
        int type = event.getEventType();
        if (type != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
                && type != AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
                && type != AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED) {
            return;
        }
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return;
        try {
            String url = findUrl(root, fieldId);
            if (url == null || url.isEmpty()) return;
            long now = System.currentTimeMillis();
            if (url.equals(lastUrl) && (now - lastAt) < 4000) return; // de-dupe rapid repeats
            lastUrl = url; lastAt = now;
            String domain = extractDomain(url);
            db.addBrowse(now, "accessibility", appLabel(pkg), url, domain, "");
        } finally {
            root.recycle();
        }
    }

    private String findUrl(AccessibilityNodeInfo root, String fieldId) {
        java.util.List<AccessibilityNodeInfo> nodes = root.findAccessibilityNodeInfosByViewId(fieldId);
        if (nodes == null || nodes.isEmpty()) return null;
        try {
            AccessibilityNodeInfo node = nodes.get(0);
            CharSequence text = node.getText();
            return text == null ? null : text.toString().trim();
        } finally {
            for (AccessibilityNodeInfo n : nodes) n.recycle();
        }
    }

    private String extractDomain(String url) {
        String u = url;
        if (!u.contains("://")) u = "http://" + u;
        try {
            java.net.URI uri = java.net.URI.create(u);
            String host = uri.getHost();
            return host == null ? "" : host.toLowerCase();
        } catch (Exception e) {
            // Address bars often show a bare "example.com/path" without scheme and
            // sometimes with spaces from "Search or type URL" placeholders — fall
            // back to a cheap first-token split instead of dropping the event.
            String s = url.split("[ /]")[0];
            return s.toLowerCase();
        }
    }

    private String appLabel(String pkg) {
        try {
            return getPackageManager().getApplicationLabel(getPackageManager().getApplicationInfo(pkg, 0)).toString();
        } catch (Exception e) {
            return pkg;
        }
    }

    @Override
    public void onInterrupt() { }

    @Override
    public void onDestroy() {
        super.onDestroy();
        instance = null;
    }
}
