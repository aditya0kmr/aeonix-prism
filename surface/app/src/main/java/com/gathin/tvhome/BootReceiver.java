package com.gathin.tvhome;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * Boots straight into CleanYourTV launcher upon device restart or power-on.
 */
public class BootReceiver extends BroadcastReceiver {
    private static final String TAG = "CleanYourTVBoot";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent != null ? intent.getAction() : null;
        Log.i(TAG, "Boot event received: " + action);

        try {
            ServiceRepair.restore(context);
        } catch (Exception ignored) {
        }

        Intent home = new Intent(context, MainActivity.class)
                .addCategory(Intent.CATEGORY_HOME)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
        try {
            context.startActivity(home);
        } catch (Exception e) {
            Log.e(TAG, "Failed to start MainActivity on boot", e);
        }
    }
}
