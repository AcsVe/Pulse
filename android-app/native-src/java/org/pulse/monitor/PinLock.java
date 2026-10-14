package org.pulse.monitor;

import android.content.Context;

import java.security.MessageDigest;
import java.security.SecureRandom;

/** A local PIN gate (4–6 digits) for opening the app and for stopping monitoring from inside it. */
public class PinLock {
    public static boolean hasPin(Context ctx) {
        return Db.get(ctx).getStr("pin_hash", null) != null;
    }

    public static void setPin(Context ctx, String pin) {
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        String saltHex = toHex(salt);
        Db db = Db.get(ctx);
        db.put("pin_salt", saltHex);
        db.put("pin_hash", hash(pin, saltHex));
    }

    public static boolean verify(Context ctx, String pin) {
        Db db = Db.get(ctx);
        String storedHash = db.getStr("pin_hash", null);
        String salt = db.getStr("pin_salt", null);
        if (storedHash == null || salt == null || pin == null) return false;
        return constantTimeEquals(storedHash, hash(pin, salt));
    }

    public static void clear(Context ctx) {
        Db db = Db.get(ctx);
        db.put("pin_hash", "");
        db.put("pin_salt", "");
    }

    private static String hash(String pin, String saltHex) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            md.update(fromHex(saltHex));
            md.update(pin.getBytes("UTF-8"));
            return toHex(md.digest());
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private static boolean constantTimeEquals(String a, String b) {
        if (a.length() != b.length()) return false;
        int r = 0;
        for (int i = 0; i < a.length(); i++) r |= a.charAt(i) ^ b.charAt(i);
        return r == 0;
    }

    private static String toHex(byte[] b) {
        StringBuilder sb = new StringBuilder();
        for (byte x : b) sb.append(String.format("%02x", x));
        return sb.toString();
    }

    private static byte[] fromHex(String s) {
        byte[] out = new byte[s.length() / 2];
        for (int i = 0; i < out.length; i++) out[i] = (byte) Integer.parseInt(s.substring(i * 2, i * 2 + 2), 16);
        return out;
    }
}
