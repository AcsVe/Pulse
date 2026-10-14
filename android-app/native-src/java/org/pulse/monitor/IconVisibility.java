package org.pulse.monitor;

import android.content.ComponentName;
import android.content.Context;
import android.content.pm.PackageManager;

/** Toggles the launcher icon by enabling/disabling the LauncherAlias activity-alias. */
public class IconVisibility {
    private static ComponentName alias(Context ctx) {
        return new ComponentName(ctx.getPackageName(), "org.pulse.monitor.LauncherAlias");
    }

    public static void hide(Context ctx) {
        ctx.getPackageManager().setComponentEnabledSetting(alias(ctx),
                PackageManager.COMPONENT_ENABLED_STATE_DISABLED, PackageManager.DONT_KILL_APP);
        Db.get(ctx).putBool("icon_hidden", true);
    }

    public static void show(Context ctx) {
        ctx.getPackageManager().setComponentEnabledSetting(alias(ctx),
                PackageManager.COMPONENT_ENABLED_STATE_ENABLED, PackageManager.DONT_KILL_APP);
        Db.get(ctx).putBool("icon_hidden", false);
    }

    public static boolean isHidden(Context ctx) {
        return Db.get(ctx).getBool("icon_hidden", false);
    }
}
