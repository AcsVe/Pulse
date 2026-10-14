package org.pulse.monitor;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * Safety net: whatever the icon-hidden state is, tapping the persistent
 * notification always re-enables the launcher icon and opens the app — so
 * hiding the icon can never lock the owner out of their own app.
 */
public class ShowIconReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        IconVisibility.show(context);
        Intent launch = new Intent(context, MainActivity.class);
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        context.startActivity(launch);
    }
}
