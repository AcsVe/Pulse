package org.pulse.monitor;

import android.app.admin.DeviceAdminReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;

/**
 * Being an active Device Admin is the only lever a normal (non-MDM-enrolled)
 * Android app has over uninstallation: while active, the system's own
 * "Uninstall" button (in Settings and in app stores) is disabled for this
 * app, and removing it first requires the owner to deactivate device admin
 * from Settings > Security > "Apps with device admin access" — Android does
 * not let a regular app put its own passcode prompt in front of that system
 * screen, so this is friction, not a true lock.
 */
public class PulseDeviceAdminReceiver extends DeviceAdminReceiver {
    public static ComponentName componentName(Context ctx) {
        return new ComponentName(ctx.getApplicationContext(), PulseDeviceAdminReceiver.class);
    }

    @Override
    public CharSequence onDisableRequested(Context context, Intent intent) {
        return "إيقاف هذه الحماية سيسمح بإلغاء تثبيت Pulse دون رمز سري. تابع فقط إذا كنت تقصد ذلك.";
    }
}
