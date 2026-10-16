package org.pulse.admin;

import android.annotation.SuppressLint;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.text.TextUtils;
import android.util.Patterns;
import android.view.Menu;
import android.view.MenuItem;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.Toolbar;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

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

    private WebView webView;
    private SwipeRefreshLayout swipe;
    private SharedPreferences prefs;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);

        Toolbar toolbar = findViewById(R.id.toolbar);
        setSupportActionBar(toolbar);

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
        ws.setSupportZoom(false);

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
        if (TextUtils.isEmpty(saved)) {
            promptForServerUrl(true);
        } else {
            webView.loadUrl(saved);
        }
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        getMenuInflater().inflate(R.menu.main_menu, menu);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        int id = item.getItemId();
        if (id == R.id.action_reload) {
            webView.reload();
            return true;
        } else if (id == R.id.action_change_server) {
            promptForServerUrl(false);
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    @Override
    public void onBackPressed() {
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
