package com.home.bernd.automatedyoutubesimulation;/*
 * Copyright 2015, The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */


import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import android.support.test.InstrumentationRegistry;
import android.support.test.filters.SdkSuppress;
import android.support.test.runner.AndroidJUnit4;
import android.support.test.uiautomator.By;
import android.support.test.uiautomator.Direction;
import android.support.test.uiautomator.UiDevice;
import android.support.test.uiautomator.UiObject2;
import android.support.test.uiautomator.Until;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.regex.Pattern;

import static java.lang.Thread.sleep;
import static org.hamcrest.CoreMatchers.is;
import static org.hamcrest.CoreMatchers.notNullValue;
import static org.junit.Assert.assertThat;

/**
 * Basic sample for unbundled UiAutomator.
 */
@RunWith(AndroidJUnit4.class)
@SdkSuppress(minSdkVersion = 18)
public class MainTest {

    private static final String BASIC_SAMPLE_PACKAGE
            = "com.google.android.youtube";

    private static final int LAUNCH_TIMEOUT = 200000;

    private static final String STRING_TO_BE_TYPED = "UiAutomator";

    private UiDevice mDevice;

    @Before
    public void startMainActivityFromHomeScreen() {
        // Initialize UiDevice instance
        mDevice = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());


        // Wait for launcher
        final String launcherPackage = getLauncherPackageName();
        assertThat(launcherPackage, notNullValue());
        mDevice.wait(Until.hasObject(By.pkg(launcherPackage).depth(0)), 25000);

        // Launch the blueprint app
        Context context = InstrumentationRegistry.getContext();
        final Intent intent = context.getPackageManager()
                .getLaunchIntentForPackage(BASIC_SAMPLE_PACKAGE);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK);    // Clear out any previous instances
        context.startActivity(intent);

        // Wait for the app to appear
        try {
            Thread.sleep(10000);
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
        mDevice.wait(Until.hasObject(By.pkg(BASIC_SAMPLE_PACKAGE).depth(0)), 250000);
    }

    @Test
    public void checkPreconditions() {
        assertThat(mDevice, notNullValue());
    }

    @Test
    public void testClickOptions_sameActivity() {


    }

    @Test
    public void startTest() {

        // Enable stats for nerds.
        UiObject2 optionsButton = mDevice.findObject(By.desc("More options"));

        while (optionsButton == null)
            optionsButton = mDevice.wait(Until.findObject(By.desc("Account")), 500);
        optionsButton.click();

        UiObject2 settingsButton = mDevice.wait(Until.findObject(By.text("Settings")), 500);
        while (settingsButton == null)
            settingsButton = mDevice.wait(Until.findObject(By.text("Settings")), 500);
        settingsButton.click();

        boolean autoplayClicked = false;

        UiObject2 autoplayButton = mDevice.wait(Until.findObject(By.text("Autoplay")), 1000);
        int tries = 0;
        while (autoplayButton == null && tries < 3) {
            autoplayButton = mDevice.wait(Until.findObject(By.text("Autoplay")), 1000);
            tries++;
        }

        if (autoplayButton != null) {
            autoplayButton.click();
            autoplayClicked = true;
        }


        mDevice.wait(Until.findObject(By.text("General")), 1000);
        UiObject2 generalButton = mDevice.wait(Until.findObject(By.text("General")), 500);
        while (generalButton == null)
            generalButton = mDevice.wait(Until.findObject(By.text("General")), 500);
        generalButton.click();

        if (!autoplayClicked) {
            autoplayButton = mDevice.wait(Until.findObject(By.text("Autoplay")), 1000);
            while (autoplayButton == null)
                autoplayButton = mDevice.wait(Until.findObject(By.text("Autoplay")), 1000);
            autoplayButton.click();
        }

       UiObject2 appViews = mDevice.wait(Until.findObject(By.res("android:id/list")), 500);
        while (appViews == null)
            appViews = mDevice.wait(Until.findObject(By.res("android:id/list")), 500);
        appViews.scroll(Direction.DOWN, 40);

        UiObject2 nerdsButton = mDevice.wait(Until.findObject(By.text("Enable stats for nerds")), 1000);
        while (nerdsButton == null)
            nerdsButton = mDevice.wait(Until.findObject(By.text("Enable stats for nerds")), 1000);
        nerdsButton.click();

        try {
            Thread.sleep(1000);
        } catch (InterruptedException e) {
            e.printStackTrace();
        }

        ControlServer server = new ControlServer(InstrumentationRegistry.getContext(), mDevice);
        server.startListening();

        //testme();
    }

    private void testme() {
        Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse("https://www.youtube.com/watch?v=eRsGyueVLvQ"));
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Context context = InstrumentationRegistry.getContext();
        context.startActivity(i);

        UiObject2 timeObject = mDevice.wait(Until.findObject(By.desc(Pattern.compile("\\d*:\\d* of \\d*:\\d*"))), 3000);

        try (ServerSocket socket = new ServerSocket(25500);
             Socket clientSocket = socket.accept();) {
            BufferedReader fromClient = new BufferedReader(new InputStreamReader(clientSocket.getInputStream()));
            PrintWriter toClient = new PrintWriter(clientSocket.getOutputStream(), true);
            while (true) {
                Thread.sleep(500);
                timeObject = mDevice.wait(Until.findObject(By.desc(Pattern.compile("\\d*:\\d* of \\d*:\\d*"))), 500);
                toClient.println(timeObject.getContentDescription());

            }
        } catch (IOException e) {
            e.printStackTrace();
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
    }


    /**
     * Uses package manager to find the package name of the device launcher. Usually this package
     * is "com.android.launcher" but can be different at times. This is a generic solution which
     * works on all platforms.`
     */
    private String getLauncherPackageName() {
        // Create launcher Intent
        final Intent intent = new Intent(Intent.ACTION_MAIN);
        intent.addCategory(Intent.CATEGORY_HOME);

        // Use PackageManager to get the launcher package name
        PackageManager pm = InstrumentationRegistry.getContext().getPackageManager();
        ResolveInfo resolveInfo = pm.resolveActivity(intent, PackageManager.MATCH_DEFAULT_ONLY);
        return resolveInfo.activityInfo.packageName;
    }
}
