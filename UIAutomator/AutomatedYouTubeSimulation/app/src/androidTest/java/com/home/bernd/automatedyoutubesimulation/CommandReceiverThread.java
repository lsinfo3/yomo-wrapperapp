package com.home.bernd.automatedyoutubesimulation;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.util.Queue;

/**
 * Created by user on 11.08.17.
 */

public class CommandReceiverThread extends Thread {

    private Queue<String> commandQueue;
    private boolean cmdComplete;
    private boolean videoStopped;

    public CommandReceiverThread(Queue commandQueue) {

        this.commandQueue = commandQueue;
    }


    public void run() {

        try (Socket socket = new Socket("localhost", 25500);) {
            socket.setSoTimeout(2000);
            BufferedReader fromServer = new BufferedReader(new InputStreamReader(socket.getInputStream()));
            PrintWriter toServer = new PrintWriter(socket.getOutputStream(), true);
            while (!videoStopped) {

                try {
                    String cmd = fromServer.readLine();
                    if (cmd == null) { continue;}
                    commandQueue.add(cmd);

                    while (!cmdComplete) {
                        try {
                            Thread.sleep(500);
                        } catch (InterruptedException e) {
                            e.printStackTrace();
                        }
                    }

                    toServer.println("success");
                    setCmdComplete(false);

                } catch (SocketTimeoutException e) {

                }


            }

        } catch (UnknownHostException e) {
            e.printStackTrace();
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    public void setCmdComplete(boolean cmdComplete) {
        this.cmdComplete = cmdComplete;
    }

    public void setVideoStopped(boolean videoStopped) {
        this.videoStopped = videoStopped;
    }
}