package org.pulse.monitor;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import java.util.ArrayList;
import java.util.List;

/** Local queue for usage / network / browse events, plus small key-value config. */
public class Db extends SQLiteOpenHelper {
    private static final String NAME = "pulse.db";
    private static final int VERSION = 2;
    private static Db instance;

    public static synchronized Db get(Context ctx) {
        if (instance == null) instance = new Db(ctx.getApplicationContext());
        return instance;
    }

    private Db(Context ctx) { super(ctx, NAME, null, VERSION); }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE usage_q (id INTEGER PRIMARY KEY AUTOINCREMENT, package TEXT, label TEXT, " +
                "start_ts INTEGER, end_ts INTEGER, synced INTEGER DEFAULT 0)");
        db.execSQL("CREATE TABLE net_q (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, transport TEXT, " +
                "start_ts INTEGER, end_ts INTEGER, detail TEXT, synced INTEGER DEFAULT 0, open_row INTEGER DEFAULT 0)");
        db.execSQL("CREATE TABLE browse_q (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, source TEXT, " +
                "app TEXT, url TEXT, domain TEXT, title TEXT, synced INTEGER DEFAULT 0)");
        createV2Tables(db);
        db.execSQL("CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT)");
        db.execSQL("CREATE INDEX idx_usage_sync ON usage_q(synced)");
        db.execSQL("CREATE INDEX idx_net_sync ON net_q(synced)");
        db.execSQL("CREATE INDEX idx_browse_sync ON browse_q(synced)");
    }

    private void createV2Tables(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE data_q (id INTEGER PRIMARY KEY AUTOINCREMENT, package TEXT, label TEXT, " +
                "ts INTEGER, rx INTEGER, tx INTEGER, transport TEXT, synced INTEGER DEFAULT 0)");
        db.execSQL("CREATE TABLE mem_q (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, " +
                "used_mb INTEGER, total_mb INTEGER, synced INTEGER DEFAULT 0)");
        db.execSQL("CREATE INDEX idx_data_sync ON data_q(synced)");
        db.execSQL("CREATE INDEX idx_mem_sync ON mem_q(synced)");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldV, int newV) {
        if (oldV < 2) createV2Tables(db);
    }

    // ── config kv store ──────────────────────────────────────────────────
    public String getStr(String k, String def) {
        try (Cursor c = getReadableDatabase().query("kv", new String[]{"v"}, "k=?", new String[]{k}, null, null, null)) {
            return c.moveToFirst() ? c.getString(0) : def;
        }
    }
    public boolean getBool(String k, boolean def) { return "1".equals(getStr(k, def ? "1" : "0")); }
    public void put(String k, String v) {
        ContentValues cv = new ContentValues(); cv.put("k", k); cv.put("v", v);
        getWritableDatabase().insertWithOnConflict("kv", null, cv, SQLiteDatabase.CONFLICT_REPLACE);
    }
    public void putBool(String k, boolean v) { put(k, v ? "1" : "0"); }

    // ── usage sessions ───────────────────────────────────────────────────
    public void addUsage(String pkg, String label, long start, long end) {
        ContentValues cv = new ContentValues();
        cv.put("package", pkg); cv.put("label", label); cv.put("start_ts", start); cv.put("end_ts", end);
        getWritableDatabase().insert("usage_q", null, cv);
    }

    // ── net events — upsert the currently-open row by kind, or close + open a new one ──
    public long openNet(String kind, String transport, long start, String detail) {
        ContentValues cv = new ContentValues();
        cv.put("kind", kind); cv.put("transport", transport); cv.put("start_ts", start);
        cv.put("detail", detail); cv.put("open_row", 1);
        return getWritableDatabase().insert("net_q", null, cv);
    }
    public void closeNet(long id, long end) {
        ContentValues cv = new ContentValues(); cv.put("end_ts", end); cv.put("open_row", 0);
        getWritableDatabase().update("net_q", cv, "id=?", new String[]{String.valueOf(id)});
    }
    public Long currentOpenNetId() {
        try (Cursor c = getReadableDatabase().query("net_q", new String[]{"id"}, "open_row=1", null, null, null, "id DESC", "1")) {
            return c.moveToFirst() ? c.getLong(0) : null;
        }
    }

    // ── data usage samples (per-app, plus a '__device__' sentinel row for totals) ──
    public void addDataUsage(String pkg, String label, long ts, long rx, long tx, String transport) {
        if (rx <= 0 && tx <= 0) return; // nothing moved — skip the no-op row
        ContentValues cv = new ContentValues();
        cv.put("package", pkg); cv.put("label", label); cv.put("ts", ts);
        cv.put("rx", rx); cv.put("tx", tx); cv.put("transport", transport);
        getWritableDatabase().insert("data_q", null, cv);
    }

    // ── memory samples ───────────────────────────────────────────────────
    public void addMemSample(long ts, long usedMb, long totalMb) {
        ContentValues cv = new ContentValues();
        cv.put("ts", ts); cv.put("used_mb", usedMb); cv.put("total_mb", totalMb);
        getWritableDatabase().insert("mem_q", null, cv);
    }

    // ── browse events ────────────────────────────────────────────────────
    public void addBrowse(long ts, String source, String app, String url, String domain, String title) {
        ContentValues cv = new ContentValues();
        cv.put("ts", ts); cv.put("source", source); cv.put("app", app);
        cv.put("url", url); cv.put("domain", domain); cv.put("title", title);
        getWritableDatabase().insert("browse_q", null, cv);
    }

    // ── sync ──────────────────────────────────────────────────────────────
    public interface RowVisitor { void row(ContentValues values, long id); }

    public List<long[]> pendingIds(String table, int limit) {
        List<long[]> ids = new ArrayList<>();
        try (Cursor c = getReadableDatabase().query(table, new String[]{"id"}, "synced=0", null, null, null, "id ASC", String.valueOf(limit))) {
            while (c.moveToNext()) ids.add(new long[]{c.getLong(0)});
        }
        return ids;
    }

    public Cursor queryPending(String table, String[] cols, int limit) {
        return getReadableDatabase().query(table, cols, "synced=0", null, null, null, "id ASC", String.valueOf(limit));
    }

    public void markSynced(String table, List<Long> ids) {
        if (ids.isEmpty()) return;
        SQLiteDatabase db = getWritableDatabase();
        db.beginTransaction();
        try {
            for (Long id : ids) db.execSQL("UPDATE " + table + " SET synced=1 WHERE id=?", new Object[]{id});
            db.setTransactionSuccessful();
        } finally { db.endTransaction(); }
    }

    public int countPending() {
        int n = 0;
        for (String t : new String[]{"usage_q", "net_q", "browse_q", "data_q", "mem_q"}) {
            try (Cursor c = getReadableDatabase().rawQuery("SELECT COUNT(*) FROM " + t + " WHERE synced=0", null)) {
                if (c.moveToFirst()) n += c.getInt(0);
            }
        }
        return n;
    }

    /** Housekeeping: drop synced rows older than 7 days so the local db doesn't grow forever. */
    public void vacuumOld() {
        long cutoff = System.currentTimeMillis() - 7L * 24 * 3600 * 1000;
        SQLiteDatabase db = getWritableDatabase();
        db.execSQL("DELETE FROM usage_q WHERE synced=1 AND end_ts < ?", new Object[]{cutoff});
        db.execSQL("DELETE FROM net_q WHERE synced=1 AND open_row=0 AND end_ts < ?", new Object[]{cutoff});
        db.execSQL("DELETE FROM browse_q WHERE synced=1 AND ts < ?", new Object[]{cutoff});
        db.execSQL("DELETE FROM data_q WHERE synced=1 AND ts < ?", new Object[]{cutoff});
        db.execSQL("DELETE FROM mem_q WHERE synced=1 AND ts < ?", new Object[]{cutoff});
    }
}
