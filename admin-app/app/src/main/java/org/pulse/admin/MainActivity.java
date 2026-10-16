package org.pulse.admin;

import android.annotation.SuppressLint;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.text.TextUtils;
import android.util.Patterns;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.ActionBarDrawerToggle;
import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.Toolbar;
import androidx.drawerlayout.widget.DrawerLayout;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import com.google.android.material.navigation.NavigationView;

/**
 * Pulse Admin: a thin WebView wrapper around the Pulse dashboard an admin
 * already uses in a browser — a real installed app (home-screen icon,
 * no browser chrome/URL bar) for admins who'd rather tap an icon than open
 * Chrome and remember a bookmark, distinct from the PWA "Add to Home
 * Screen" option the dashboard itself also offers (this is the same idea
 * as a native app instead; either works, this is for whoever prefers it).
 *
 * Unlike android-app/ (the on-device collector, which does real native work:
 * accessibility service, VPN, screen capture), this app has exactly one job
 * — show the dashboard — so there's no bundled server address: the admin
 * types their own Pulse server URL in on first launch (same as typing it
 * into a browser once), and it's remembered after that.
 */
public class MainActivity extends AppCompatActivity {
    private static final String PREFS = "pulse_admin";
    private static final String KEY_SERVER_URL = "server_url";
    // Whether the admin last left the drawer open or closed — restored on
    // the next launch so the menu doesn't reset to "closed" every time
    // (that's the "remembers the menu's position" part of the request).
    private static final String KEY_DRAWER_OPEN = "drawer_open";

    private WebView webView;
    private SwipeRefreshLayout swipe;
    private SharedPreferences prefs;
    private DrawerLayout drawerLayout;
    private TextView navServer;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);

        Toolbar toolbar = findViewById(R.id.toolbar);
        setSupportActionBar(toolbar);

        drawerLayout = findViewById(R.id.drawer_layout);
        NavigationView navView = findViewById(R.id.nav_view);

        // ActionBarDrawerToggle draws its own animated hamburger/arrow icon
        // (no drawable resource needed) and wires it to the toolbar, plus
        // handles the edge-swipe-to-open gesture — this is the persistent
        // "مرسال" toggle: it's always in the same spot in the toolbar,
        // never buried in an overflow menu.
        ActionBarDrawerToggle toggle = new ActionBarDrawerToggle(
                this, drawerLayout, toolbar, R.string.drawer_open, R.string.drawer_close) {
            @Override
            public void onDrawerOpened(android.view.View drawerView) {
                super.onDrawerOpened(drawerView);
                prefs.edit().putBoolean(KEY_DRAWER_OPEN, true).apply();
            }

            @Override
            public void onDrawerClosed(android.view.View drawerView) {
                super.onDrawerClosed(drawerView);
                prefs.edit().putBoolean(KEY_DRAWER_OPEN, false).apply();
            }
        };
        drawerLayout.addDrawerListener(toggle);
        toggle.syncState();

        navServer = navView.getHeaderView(0).findViewById(R.id.nav_header_server);
        navView.setNavigationItemSelectedListener(item -> {
            drawerLayout.closeDrawers();
            int id = item.getItemId();
            if (id == R.id.action_reload) {
                webView.reload();
                return true;
            } else if (id == R.id.action_change_server) {
                promptForServerUrl(false);
                return true;
            }
            return false;
        });

        webView = findViewById(R.id.webview);
        swipe = findViewById(R.id.swipe);

        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        // The dashboard stores the language toggle, table sort, etc. in
        // localStorage (see app.js's setLang/S) — without DOM storage every
        // preference would reset on each relaunch.
        ws.setDomStorageEnabled(true);
        ws.setLoadWithOverviewMode(true);
        ws.setUseWideViewPort(true);
        // The dashboard's own CSS already handles mobile widths, but a
        // WebView's viewport math isn't always identical to Chrome's, so a
        // wide table or a card that assumes slightly more room than is
        // actually there can get clipped off the right/bottom edge with no
        // way to reach it. Disabling zoom (as this did before) removes the
        // user's only escape hatch for that case. Pinch-zoom is re-enabled
        // here, with the on-screen +/- controls hidden so it doesn't look
        // like a browser — the gesture is there if something is cut off,
        // but nothing changes for pages that already fit.
        ws.setSupportZoom(true);
        ws.setBuiltInZoomControls(true);
        ws.setDisplayZoomControls(false);
        // Default OVER_SCROLL_ALWAYS fights with SwipeRefreshLayout's own
        // pull-down gesture right at the top of the page (both try to
        // handle the same drag), which is what made panning feel stuck
        // there. IF_CONTENT_SCROLLS only engages the WebView's own overscroll
        // once its content is actually larger than the viewport, leaving the
        // top-of-page drag to SwipeRefreshLayout.
        webView.setOverScrollMode(WebView.OVER_SCROLL_IF_CONTENT_SCROLLS);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                swipe.setRefreshing(false);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                // Only treat a failure of the top-level page load as fatal —
                // a single failed sub-resource (an image, a stray request)
                // shouldn't blank out an otherwise-working dashboard.
                if (request.isForMainFrame()) {
                    swipe.setRefreshing(false);
                    String url = getServerUrl();
                    view.loadData("<html><body style='font-family:sans-serif;text-align:center;padding:40px 20px;color:#5d7283'>"
                            + android.text.Html.escapeHtml(getString(R.string.load_error, url)) + "</body></html>",
                            "text/html", "utf-8");
                }
            }
        });

        swipe.setOnRefreshListener(() -> webView.reload());

        String saved = getServerUrl();
        updateNavHeader(saved);
        if (TextUtils.isEmpty(saved)) {
            promptForServerUrl(true);
        } else {
            webView.loadUrl(saved);
        }

        // Restore the drawer to however the admin last left it, rather than
        // always starting closed — posted so it runs after this layout pass
        // has actually measured the drawer (opening it before that can be a
        // no-op on some devices).
        if (prefs.getBoolean(KEY_DRAWER_OPEN, false)) {
            drawerLayout.post(() -> drawerLayout.openDrawer(navView));
        }
    }

    @Override
    public void onBackPressed() {
        // Closing an open drawer is the more expected "back" action than
        // navigating the page underneath it or closing the app outright.
        if (drawerLayout.isDrawerOpen(androidx.core.view.GravityCompat.START)) {
            drawerLayout.closeDrawers();
            return;
        }
        // Back inside the dashboard's own navigation (tabs are client-side
        // routing, not real page loads, so WebView history is mostly about
        // the remote-control panel and similar in-page state) before
        // falling back to actually closing the app.
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    private String getServerUrl() {
        return prefs.getString(KEY_SERVER_URL, null);
    }

    private void updateNavHeader(String url) {
        if (navServer != null) {
            navServer.setText(TextUtils.isEmpty(url) ? getString(R.string.server_url_hint) : url);
        }
    }

    /** cancelable=false on first launch (there's nothing useful to show yet
     *  without a server) — once a URL is already set, changing it can be
     *  dismissed to keep the current one. */
    private void promptForServerUrl(boolean firstLaunch) {
        FrameLayout container = new FrameLayout(this);
        int pad = (int) (20 * getResources().getDisplayMetrics().density);
        container.setPadding(pad, pad, pad, 0);
        final EditText input = new EditText(this);
        input.setHint(R.string.server_url_hint);
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        String current = getServerUrl();
        if (current != null) input.setText(current);
        container.addView(input);

        AlertDialog.Builder b = new AlertDialog.Builder(this)
                .setTitle(R.string.server_url_title)
                .setView(container)
                .setCancelable(!firstLaunch)
                .setPositiveButton(R.string.server_url_save, null); // set below, to validate before dismissing
        if (!firstLaunch) {
            b.setNegativeButton(android.R.string.cancel, null);
        }
        AlertDialog dialog = b.create();
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String url = normalizeUrl(input.getText().toString().trim());
            if (TextUtils.isEmpty(url) || !Patterns.WEB_URL.matcher(url).matches()) {
                Toast.makeText(this, R.string.server_url_empty, Toast.LENGTH_SHORT).show();
                return;
            }
            prefs.edit().putString(KEY_SERVER_URL, url).apply();
            updateNavHeader(url);
            webView.loadUrl(url);
            dialog.dismiss();
        }));
        dialog.show();
    }

    /** Admins will naturally type "myserver.onrender.com" without a scheme —
     *  default to https (what every real Pulse deployment uses; cleartext
     *  is still allowed for the LAN-server case, but that's the exception,
     *  not what a bare hostname should assume). */
    private String normalizeUrl(String url) {
        if (TextUtils.isEmpty(url)) return url;
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "https://" + url;
        }
        return url;
    }
}
