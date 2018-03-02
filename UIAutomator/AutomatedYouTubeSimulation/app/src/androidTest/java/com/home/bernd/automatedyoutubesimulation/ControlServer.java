package com.home.bernd.automatedyoutubesimulation;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.support.test.InstrumentationRegistry;
import android.support.test.uiautomator.By;
import android.support.test.uiautomator.StaleObjectException;
import android.support.test.uiautomator.UiDevice;
import android.support.test.uiautomator.UiObject2;
import android.support.test.uiautomator.Until;

import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.Socket;
import java.util.Calendar;
import java.util.Queue;
import java.util.TimeZone;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.regex.Pattern;

/**
 * Created by Bernd on 01.08.2017.
 */

public class ControlServer {

    private Context context;
    private UiDevice mDevice;
    private Queue<String> commandQueue = new ConcurrentLinkedQueue<>();
    private boolean videoRunning = false;

    public ControlServer(Context context, UiDevice mDevice) {
        this.context = context;
        this.mDevice = mDevice;
    }

    public void startListening() {
        CommandReceiverThread commandReceiverThread = new CommandReceiverThread(commandQueue);
        commandReceiverThread.start();

        //ClipboardManager clipboard = (ClipboardManager) context.getSystemService(Context.CLIPBOARD_SERVICE);


        try (Socket socket = new Socket("localhost", 25501);) {
            BufferedReader fromClient = new BufferedReader(new InputStreamReader(socket.getInputStream()));
            PrintWriter toServer = new PrintWriter(socket.getOutputStream(), true);

            while (!mDevice.hasObject(By.desc("Replay video"))) {

                if (!commandQueue.isEmpty()) {
                    String cmd = commandQueue.poll();
                    processCommand(cmd);
                    commandReceiverThread.setCmdComplete(true);
                }


                if (!videoRunning) continue;
                UiObject2 timeObject = mDevice.wait(Until.findObject(By.desc(Pattern.compile("\\d*:\\d* of \\d*:\\d*"))), 500);
                if (timeObject != null) {
                    Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("GMT"));
                    try {
                        toServer.println("progress:" + cal.getTimeInMillis() + " : " + timeObject.getContentDescription());
                    } catch (StaleObjectException e) {
                        e.printStackTrace();
                    }
                }

                UiObject2 nerdObject = mDevice.wait(Until.findObject(By.desc("Copy debug info")), 500);

                if (nerdObject != null) {
                    nerdObject.click();
                    toServer.println("nerd");
                }

                Thread.sleep(500);
            }
            commandReceiverThread.setVideoStopped(true);
            commandReceiverThread.join();
            toServer.println("done");
        } catch (FileNotFoundException e) {
            e.printStackTrace();
        } catch (IOException e) {
            e.printStackTrace();
        } catch (InterruptedException e) {
            e.printStackTrace();
        }


    }

    private boolean processCommand(String cmd) {
        if (cmd.startsWith("open:")) {
            openVideo(cmd.substring(5));
            return true;
        } else if (cmd.startsWith("setquality:")) {
            setQuality(cmd.substring(11));
            return true;
        } else if (cmd.startsWith("presetquality:")) {
            presetQuality(cmd.substring(14));
            return true;
        }
        return false;
    }

    private void presetQuality(String qualityString) {
        Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse("https://www.youtube.com/watch?v=FiO0iLzTyVg"));
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(i);

        mDevice.wait(Until.findObject(By.res("com.google.android.youtube:id/player_overflow_button")), 5000);
        setQuality(qualityString);

        try {
            Thread.sleep(4000);
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
        openMenu();

        UiObject2 statsForNerds = null;
        while (statsForNerds == null)
            statsForNerds = mDevice.wait(Until.findObject(By.text("Stats for nerds")), 500);
        statsForNerds.click();

    }

    private void openMenu() {
        UiObject2 player = mDevice.wait(Until.findObject(By.res("com.google.android.youtube:id/watch_player_container")), 500);
        player.click();

        mDevice.click((int) (mDevice.getDisplayWidth() * 0.92), (int) (mDevice.getDisplayHeight() * 0.08));
    }

    private void setQuality(String qualityString) {

        openMenu();

        mDevice.wait(Until.hasObject(By.text("Quality")), 5000);
        UiObject2 qualityMenu = mDevice.findObject(By.text("Quality"));

        while (qualityMenu == null) {
            qualityMenu = mDevice.findObject(By.text("Quality"));
        }

        qualityMenu.click();

        try {
            Thread.sleep(2000);
        } catch (InterruptedException e) {
            e.printStackTrace();
        }

        UiObject2 qualityButton = mDevice.wait(Until.findObject(By.text(Pattern.compile(qualityString + ".*"))), 5000);
        while (qualityButton == null) {
            qualityButton = mDevice.wait(Until.findObject(By.text(Pattern.compile(qualityString + ".*"))), 5000);
        }
        qualityButton.click();
    }

    private void openVideo(String videoURL) {
        Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse(videoURL));
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(i);

        try {
            Thread.sleep(2000);
        } catch (InterruptedException e) {
            e.printStackTrace();
        }

        videoRunning = true;


    }


}
