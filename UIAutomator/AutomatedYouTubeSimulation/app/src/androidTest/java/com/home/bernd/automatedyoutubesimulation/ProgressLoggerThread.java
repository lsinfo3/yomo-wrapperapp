package com.home.bernd.automatedyoutubesimulation;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.os.Environment;
import android.support.test.uiautomator.By;
import android.support.test.uiautomator.UiDevice;
import android.support.test.uiautomator.UiObject2;
import android.support.test.uiautomator.Until;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.Calendar;
import java.util.TimeZone;
import java.util.regex.Pattern;

/**
 * Created by Bernd on 02.08.2017.
 */

public class ProgressLoggerThread extends Thread {

    UiDevice mDevice;
    Context context;

    public ProgressLoggerThread(UiDevice mDevice, Context context) {
        this.mDevice = mDevice;
        this.context = context;
    }

    public void run() {
        ClipboardManager clipboard = (ClipboardManager) context.getSystemService(Context.CLIPBOARD_SERVICE);



        try (Socket socket = new Socket("localhost", 25501);) {
            BufferedReader fromClient = new BufferedReader(new InputStreamReader(socket.getInputStream()));
            PrintWriter toClient = new PrintWriter(socket.getOutputStream(), true);
            while (true) {
                if (mDevice.hasObject(By.desc("Replay video"))) {
                    toClient.println("done");
                    return;
                }

                UiObject2 timeObject = mDevice.wait(Until.findObject(By.desc(Pattern.compile("\\d*:\\d* of \\d*:\\d*"))), 500);
                if (timeObject == null) continue;

                Calendar cal = Calendar.getInstance(TimeZone.getTimeZone("GMT"));
                toClient.println("progress:" + cal.getTimeInMillis() + " : " + timeObject.getContentDescription());


                UiObject2 nerdObject = mDevice.wait(Until.findObject(By.desc("Copy debug info")), 500);

                if (nerdObject != null) {
                    nerdObject.click();

                    ClipData clip = clipboard.getPrimaryClip();
                    String text = (clip.getItemAt(0).coerceToText(context)).toString();

                    cal = Calendar.getInstance(TimeZone.getTimeZone("GMT"));
                    toClient.println("nerd:" + cal.getTimeInMillis() + " : " + text + "\n");
                }

                Thread.sleep(500);
            }
        } catch (FileNotFoundException e) {
            e.printStackTrace();
        } catch (IOException e) {
            e.printStackTrace();
        } catch (InterruptedException e) {
            e.printStackTrace();
        }

    }
}

