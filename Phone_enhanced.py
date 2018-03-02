import colorlog
import argparse
import configparser
import os
import random
import re
import shutil
import signal
import socket
import subprocess
import threading
import time
import logging
import atexit
import sys
import datetime


class Configuration:
    pass


def postprocess_stats(path):
    logger.debug("Postprocessing " + path)
    os.rename(path, path + ".tmp")
    with open(path + ".tmp", 'r') as source_file, open(path, 'w') as target_file:
        for line in source_file:
            if line == "Broadcasting: Intent { act=clipboard.show flg=0x20 }":
                continue

            result = re.search(r'"timestamp":"(\d{4}-\d\d-\d\dT\d+:\d+:\d+.\d+Z)"', line)
            if result is not None:
                timestamp = time.mktime(
                    datetime.datetime.strptime(result.group(1), "%Y-%m-%dT%H:%M:%S.%fZ").timetuple())
                target_file.write(str(timestamp) + "::" + line)

    os.remove(path + ".tmp")


def get_device_state(devicename):
    state = str(
        subprocess.check_output('''adb -s ''' + devicename + ''' shell dumpsys power | grep 'Display Power:' ''',
                                shell=True).decode())
    logger.log(logging.VERBOSE, "Device %s state returns ' %s '", devicename, state)
    return "ON" in state


def get_battery(devicename):
    return int(re.search(r'(\d+)',
                         subprocess.check_output('''adb -s ''' + devicename + ''' shell dumpsys battery | grep level''',
                                                 shell=True).decode()).group(1))


def change_device_state(devicename, state):
    if get_device_state(devicename) != state:
        if state:
            logger.debug("Turning device %s on", devicename)
            subprocess.Popen('''adb -s ''' + devicename + ''' shell "input keyevent 26"''', shell=True,
                             preexec_fn=os.setsid).wait()
            if configuration.nexus:
                subprocess.Popen('''adb -s ''' + devicename + ''' shell "input keyevent 82"''', shell=True,
                                 preexec_fn=os.setsid).wait()
        else:
            logger.debug("Turning device %s off", devicename)
            subprocess.Popen('''adb -s ''' + devicename + ''' shell "input keyevent 26"''', shell=True,
                             preexec_fn=os.setsid).wait()


def reset_usb():
    identifier = ""
    lsusb = subprocess.check_output("lsusb", shell=True).decode()
    result = re.search(r'Bus (\d\d\d) Device (\d\d\d): ID ' + identifier, lsusb)
    bus = result.group(1)
    device = result.group(2)
    subprocess.Popen("./usbreset /dev/bus/usb/" + bus + "/" + device, shell=True).wait()


def log_output(process, blocking):
    def handle_printing(input_pipe, action):
        if input_pipe is None:
            return
        line = input_pipe.readline().decode()
        while line != "":
            if not configuration.suppress_output:
                action(line.rstrip())
            line = input_pipe.readline().decode()

    error_thread = threading.Thread(target=handle_printing, args=(process.stderr, logger.warn))
    output_thread = threading.Thread(target=handle_printing, args=(process.stdout, logger.debug))
    error_thread.start()
    output_thread.start()

    if blocking:
        error_thread.join()
        output_thread.join()


def restart_adb():
    logger.debug("Restarting adb")
    p = subprocess.Popen("adb kill-server && adb start-server && adb usb", shell=True,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    log_output(p, True)


def cleanup():
    logger.info("Cleaning up")
    if measurement is not None:
        measurement.cleanup()


class Measurement:
    __current_device_index = 0

    def __init__(self, iteration, video_id):
        self.receiver = None
        self.video_id = video_id.rstrip()
        self.iteration = iteration
        self.discard = False
        self.scenario_list = os.listdir(configuration.schedule_directory)
        self.scenario_list.sort()
        self.scenario_index = None
        self.logfile = None
        self.scheduler = None
        self.connected = False
        self.processes = []
        self.command_socket = None

    def run(self):
        logger.info("Starting measurement on video %s", self.video_id)

        # TODO: Download Manifest
        for scenario_name in self.scenario_list:
            if not scenario_name.endswith(".txt"):
                continue
            if configuration.grepable_log:
                grep_logger.info('Started: Iteration %i, Scenario %s, Video %s, Device: %s, Battery level: %i',
                                 self.iteration, self.scenario_index, self.video_id, Measurement.get_current_device(),
                                 get_battery(Measurement.get_current_device()))
            self.scenario_index = re.search(r'_(\d+.*).txt', scenario_name).group(1)
            logger.info("Starting scenario %s with video %s", self.scenario_index, self.video_id)
            logger.debug("Current device %s is at %i %% battery power", Measurement.get_current_device(),
                         get_battery(Measurement.get_current_device()))
            self.cycle_device()
            change_device_state(Measurement.get_current_device(), True)
            self.clean_phone()
            if not configuration.no_reboot:
                if configuration.reset_usb:
                    reset_usb()
                restart_adb()

            time.sleep(10)

            logger.log(logging.VERBOSE, "Creating directory %s", self.get_path())
            os.makedirs(self.get_path(), exist_ok=True)

            self.log_times()

            logger.log(logging.VERBOSE, "Opening file %s",
                       os.path.join(self.get_path(), configuration.location + "_phone_event_log_scen_" +
                                    self.scenario_index + "_vid_" + self.video_id + "_rep_" + str(
                           self.iteration) + ".log"))
            self.logfile = open(
                os.path.join(self.get_path(), configuration.location + "_phone_event_log_scen_" +
                             self.scenario_index + "_vid_" + self.video_id + "_rep_" + str(self.iteration) + ".log"),
                'a')

            logger.debug("Clearing tc")
            p = subprocess.Popen("tc qdisc del dev " + configuration.wifi + " root", shell=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            log_output(p, True)

            logger.info("Preparing device %s", Measurement.get_current_device())


            log_output(subprocess.Popen(
                '''adb -s ''' + Measurement.get_current_device() + ''' shell "am force-stop com.google.android.youtube;'''
                + ''' pm clear com.google.android.youtube;"''',
                shell=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE), True)

            if not configuration.no_wrapper:
                init_thread = threading.Thread(target=self.initialize_wrapper)
                init_thread.start()

            self.receiver = Measurement.Receiver(self)
            self.receiver.start()

            self.start_video(scenario_name)

            logger.debug("Terminating processes")
            for process in self.processes:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            self.processes = []

            self.logfile.close()

            pull_cmd = '''adb -s ''' + Measurement.get_current_device() + ''' pull /sdcard/measurement-buffer.txt ''' \
                       + os.path.join(os.getcwd(), self.get_path(),
                                      configuration.location + "_phone_stats_for_nerds" + "_scen_" + self.scenario_index
                                      + "_vid_" + self.video_id + "_rep_" + str(self.iteration) + ".log")
            log_output(subprocess.Popen(pull_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE), True)
            logger.info("Buffer info copied to %s _logs on the PC", configuration.location)
            postprocess_stats(os.path.join(os.getcwd(), self.get_path(),
                                           configuration.location + "_phone_stats_for_nerds" + "_scen_" + self.scenario_index
                                           + "_vid_" + self.video_id + "_rep_" + str(self.iteration) + ".log"))

            pull_cmd = '''adb -s ''' + Measurement.get_current_device() + ''' pull /sdcard/tcpdump.log ''' \
                       + os.path.join(os.getcwd(), self.get_path(), configuration.location + "_phone_tcpdump" + "_scen_"
                                      + self.scenario_index + "_vid_" + self.video_id
                                      + "_rep_" + str(self.iteration) + ".log")
            log_output(subprocess.Popen(pull_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE), True)
            logger.info("Phone TCPDUMP info copied to %s _logs on the PC", configuration.location)

            self.clean_phone()
            if self.receiver.discard:
                logger.info("Moving discarded measurement to %s",
                            os.path.join(os.getcwd(), self.get_path() + "_discard_" + str(time.time())))
                shutil.move(os.path.join(os.getcwd(), self.get_path()),
                            os.path.join(os.getcwd(), self.get_path() + "_discard_" + str(time.time())))

            if configuration.grepable_log:
                grep_logger.info('Finished: Iteration %i, Scenario %s, Video %s, Device: %s, Battery level: %i',
                                 self.iteration, self.scenario_index, self.video_id, Measurement.get_current_device(),
                                 get_battery(Measurement.get_current_device()))
            self.cleanup()

    def initialize_wrapper(self):
        def timeout(p):
            if not self.connected:
                p.kill()
                self.initialize_wrapper()

        install_and_launch_cmd = '''adb -s ''' + Measurement.get_current_device() + ''' reverse tcp:25500 tcp:''' \
                                 + str(configuration.command_socket) + ''' ; ''' \
                                 + '''adb -s ''' + Measurement.get_current_device() + ''' reverse tcp:25501 tcp:''' \
                                 + str(configuration.data_socket) + ''' ; ''' \
                                 + '''adb -s ''' + Measurement.get_current_device() + ''' push app-debug.apk /data/local/tmp/com.home.bernd.automatedyoutubesimulation &&''' \
                                 + '''adb -s ''' + Measurement.get_current_device() + ''' uninstall com.home.bernd.automatedyoutubesimulation.test &&''' \
                                 + '''adb -s ''' + Measurement.get_current_device() + ''' uninstall com.home.bernd.automatedyoutubesimulation &&''' \
                                 + '''adb -s ''' + Measurement.get_current_device() + ''' shell pm install -r "/data/local/tmp/com.home.bernd.automatedyoutubesimulation" &&''' \
                                 + '''adb -s ''' + Measurement.get_current_device() + ''' push app-debug-androidTest.apk /data/local/tmp/com.home.bernd.automatedyoutubesimulation.test &&''' \
                                 + '''adb -s ''' + Measurement.get_current_device() + ''' shell pm install -r "/data/local/tmp/com.home.bernd.automatedyoutubesimulation.test" &&''' \
                                 + '''adb -s ''' + Measurement.get_current_device() + ''' shell am instrument -w -r -e debug false -e class com.home.bernd.automatedyoutubesimulation.MainTest#startTest ''' + \
                                 '''com.home.bernd.automatedyoutubesimulation.test/android.support.test.runner.AndroidJUnitRunner '''

        p = subprocess.Popen(install_and_launch_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             preexec_fn=os.setsid)
        self.processes.append(p)

        timer = threading.Timer(180, timeout, [p])
        timer.start()

        log_output(p, False)

    def clean_phone(self):
        del_cmd = '''adb -s ''' + Measurement.get_current_device() + ''' shell rm /sdcard/measurement-buffer.txt'''
        log_output(subprocess.Popen(del_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE), True)
        del_cmd = '''adb -s ''' + Measurement.get_current_device() + ''' shell rm /sdcard/tcpdump.log'''
        log_output(subprocess.Popen(del_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE), True)

    def cleanup(self):
        try:
            if self.command_socket is not None:
                self.command_socket.close()

            if self.logfile is not None:
                self.logfile.close()
            if self.receiver is not None:
                if self.receiver.client_socket is not None:
                    self.receiver.client_socket.close()

                if self.receiver.file is not None:
                    self.receiver.file.close()
        except TypeError as e:
            logger.error("Problems cleaning up: " + str(e))

        for process in self.processes:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)

    def start_video(self, scenario_name):
        starting_quality = 'Auto'
        starting_bandwidth = '1gbps'
        with open(os.path.join(configuration.schedule_directory, scenario_name)) as schedule_file:
            for line in schedule_file:
                if line.startswith('stq'):
                    starting_quality = line.split(':')[1].rstrip()
                if line.startswith('stbw'):
                    starting_bandwidth = line.split(':')[1].rstrip()

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        logger.debug("Starting command socket on port %i", configuration.command_socket)
        try:
            s.bind(('', configuration.command_socket))
        except OSError as err:
            logger.critical("Error when opening command socket. Reason: %s", err.strerror)
            cleanup()
            sys.exit(err.errno)

        s.listen(1)
        (self.command_socket, address) = s.accept()
        self.connected = True

        logger.log(logging.VERBOSE, "Command connection established")

        time.sleep(5)

        logger.info("Setting starting quality: %s", starting_quality)
        self.command_socket.send(str.encode("presetquality:" + starting_quality + "\n"))
        data = self.command_socket.recv(4096).decode()
        while "success" not in data:
            data = self.command_socket.recv(4096).decode()
        logger.debug("Successfully set starting quality")
        self.start_dump()

        logger.info("Starting video %s", self.video_id)
        self.command_socket.send(str.encode("open:https://www.youtube.com/watch?v=" + self.video_id + "\n"))
        self.log("Starting video " + self.video_id)
        logger.debug("Done starting video %s", self.video_id)

        self.schedule(scenario_name, starting_bandwidth)

        self.connected = False

    def schedule(self, scenario_name, starting_bandwidth):
        self.log("Starting bandwidth: " + starting_bandwidth)
        logger.info("Starting bandwidth: " + starting_bandwidth)
        p = subprocess.Popen("tc qdisc del dev " + configuration.wifi + " root", shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        log_output(p, True)
        p = subprocess.Popen("tc qdisc add dev " + configuration.wifi + " parent root handle 1: htb default 1",
                             shell=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log_output(p, True)
        p = subprocess.Popen(
            "tc class add dev " + configuration.wifi + " parent 1: classid 1:1 htb rate " + starting_bandwidth,
            shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log_output(p, True)
        p = subprocess.Popen("tc qdisc add dev " + configuration.wifi + " parent 1:1 handle 11 netem", shell=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log_output(p, True)
        logger.debug("tc preparation complete")

        loss = "0%"
        delay = "0ms"

        schedule = []

        last_event_time = time.time()
        with open(os.path.join(configuration.schedule_directory, scenario_name)) as schedule_file:
            for line in schedule_file:
                if line[0] == '#':
                    continue
                else:
                    event = line.split(':')
                    if len(event) != 3:
                        continue
                    elif event[0].startswith('rnd'):
                        lower = int(re.search(r'(\d*),(\d*)', event[0]).group(1))
                        higher = int(re.search(r'(\d*),(\d*)', event[0]).group(2))
                        event_time = random.randint(lower, higher)

                        schedule.append([event_time, event[1], event[2]])
                    else:
                        schedule.append(event)

        logger.log(logging.VERBOSE, "Read %i events from %s", len(schedule),
                   os.path.join(configuration.schedule_directory, scenario_name))
        current_event = 0
        while not self.receiver.done:
            while current_event < len(schedule) and time.time() >= last_event_time + int(schedule[current_event][0]):
                event = schedule[current_event]
                last_event_time = time.time()
                current_event += 1

                cmd = ''
                if event[1] == 'qc':
                    self.change_quality(event[2].rstrip())
                    self.log("Quality changed to " + event[2].rstrip())
                    logger.info("Quality changed to %s", event[2].rstrip())
                else:
                    if event[1] == 'bw':
                        cmd = "tc class change dev " + configuration.wifi + " parent 1: classid 1:1 htb rate " + event[
                            2].rstrip()
                        self.log("Rate changed to " + event[2].rstrip())
                        logger.info("Rate changed to %s", event[2].rstrip())
                    elif event[1] == 'dl':
                        delay = event[2].rstrip()
                        cmd = "tc qdisc change dev " + configuration.wifi + " parent 1:1 handle 11 netem delay " + delay + " loss " + loss
                        self.log("Delay changed to " + event[2].rstrip())
                        logger.info("Delay changed to %s", event[2].rstrip())
                    elif event[1] == 'pl':
                        loss = event[2].rstrip()
                        cmd = "tc qdisc change dev " + configuration.wifi + " parent 1:1 handle 11 netem delay " + delay + " loss " + loss
                        self.log("Loss changed to " + event[2])
                        logger.info("Loss changed to %s", event[2].rstrip())

                    logger.debug("Executing command: \"%s\"", cmd)
                    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
                    log_output(p, True)

            time.sleep(1)
        logger.debug("Stopping scheduling")

    @staticmethod
    def cycle_device():
        if get_battery(Measurement.get_current_device()) < configuration.battery_threshold:
            if len(configuration.devices) == 1:
                change_device_state(Measurement.get_current_device(), False)
                logger.info("Putting device %s to sleep, waiting for %i Minutes", Measurement.get_current_device(),
                            configuration.sleep_time)
                time.sleep(configuration.sleep_time * 60)
                logger.info("Done sleeping for device %s", Measurement.get_current_device())
                change_device_state(Measurement.get_current_device(), True)
            else:
                change_device_state(Measurement.get_current_device(), False)
                Measurement.next_device()
                logger.info("Rotating to device %s", Measurement.get_current_device())
                change_device_state(Measurement.get_current_device(), True)

        elif configuration.alternate_phones and len(configuration.devices) > 1:
            change_device_state(Measurement.get_current_device(), False)
            Measurement.next_device()
            logger.info("Rotating to device %s", Measurement.get_current_device())
            change_device_state(Measurement.get_current_device(), True)

    @staticmethod
    def get_current_device():
        return configuration.devices[Measurement.__current_device_index]

    @staticmethod
    def next_device():
        Measurement.__current_device_index = (Measurement.__current_device_index + 1) % len(configuration.devices)

    def get_path(self):
        return os.path.join(configuration.location + "_logs", "Scenario_" + self.scenario_index,
                            "Vid_" + self.video_id, "Iteration_" + str(self.iteration))

    def start_dump(self):
        p = subprocess.Popen("tcpdump -i " + configuration.interface
                             + " -v -tt -n -B 12288 \"udp or tcp\" > "
                             + os.path.join(self.get_path(),
                                            configuration.location + "_PC_tcpdump" + "_scen_"
                                            + self.scenario_index + "_vid_" + self.video_id
                                            + "_rep_" + str(self.iteration) + ".log"),
                             shell=True, preexec_fn=os.setsid, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        self.processes.append(p)
        log_output(p, False)
        logger.debug("TCPDUMP started on the PC")

        p = subprocess.Popen('''adb -s ''' + Measurement.get_current_device() +
                             ''' shell "su -c tcpdump -i wlan0 -v -tt -n -B 12288''' \
                             + ''' 'udp or tcp' > /sdcard/tcpdump.log"''',
                             shell=True, preexec_fn=os.setsid, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)

        self.processes.append(p)
        log_output(p, False)
        logger.debug("TCPDUMP started on the Phone")

        p = subprocess.Popen("tcpdump -tt -i " + configuration.interface + " udp port 53 > "
                             + os.path.join(self.get_path(),
                                            configuration.location + "_PC_dns" + "_scen_"
                                            + self.scenario_index + "_vid_" + self.video_id + "_rep_"
                                            + str(self.iteration) + ".log"),
                             shell=True, preexec_fn=os.setsid, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        self.processes.append(p)
        log_output(p, False)
        logger.debug("DNS logging started on the PC")

    def change_quality(self, level):
        self.command_socket.send(str.encode("setquality:" + level + "\n"))

    class Receiver(threading.Thread):
        def __init__(self, parent):
            threading.Thread.__init__(self)
            self.parent = parent
            self.discard = False
            self.done = False
            self.client_socket = None
            self.file = open(os.path.join(os.getcwd(), self.parent.get_path(),
                                          configuration.location + "_phone_video_progress_scen_"
                                          + self.parent.scenario_index + "_vid_" + self.parent.video_id
                                          + "_rep_" + str(self.parent.iteration) + ".log"),
                             'a')

        def run(self):
            data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            data_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            logger.debug("Starting receiver on port %i", configuration.data_socket)
            try:
                data_socket.bind(('', configuration.data_socket))
            except OSError as err:
                logger.critical("Error when opening receiver socket. Reason: %s", err.strerror)
                cleanup()
                sys.exit(err.errno)

            data_socket.listen(1)

            (client_data_socket, address) = data_socket.accept()
            self.client_socket = client_data_socket

            logger.log(logging.VERBOSE, "Data socket connected")

            data = self.client_socket.recv(4096)
            last_time = time.time()
            self.client_socket.settimeout(5)
            self.client_socket.setblocking(False)

            last_progress = "0:00"
            last_progress_time = time.time()

            while "done" not in data.decode():
                if "nerd" in data.decode():
                    copy_cmd = '''adb -s ''' + Measurement.get_current_device() \
                               + ''' shell "am broadcast -a clipboard.show''' \
                               + ''' --include-stopped-packages >> /sdcard/measurement-buffer.txt"'''
                    subprocess.Popen(copy_cmd, shell=True)
                else:
                    result = re.search(r'(\d+:\d\d) of', data.decode())
                    if result is None:
                        logger.error("Error in communication, discarding measurement")
                        data_socket.close()
                        self.discard = True
                        self.done = True
                        return

                    progress_string = result.group(1)

                    if progress_string != last_progress:
                        last_progress = progress_string
                        last_progress_time = time.time()
                    elif (time.time() - last_progress_time) > 240:
                        logger.error("No progress for 240 seconds, discarding measurement")
                        self.client_socket.close()
                        self.discard = True
                        self.done = True
                        return

                    self.file.write(data.decode())
                    self.file.flush()

                while True:
                    try:
                        data = client_data_socket.recv(4096)
                        last_time = time.time()
                        break
                    except socket.error:
                        if time.time() - last_time > 20:
                            logger.error("No response for 20 seconds, discarding measurement")
                            data_socket.close()
                            self.discard = True
                            self.done = True
                            return

            logger.info("Scenario %s for video %s completed", self.parent.scenario_index, self.parent.video_id)
            self.done = True
            self.file.close()
            data_socket.close()

    def log(self, msg):
        self.logfile.write(str(time.time()) + "::" + msg.rstrip() + "\n")
        self.logfile.flush()

    def log_times(self):
        phonetime = subprocess.check_output(
            '''adb -s ''' + self.get_current_device() + ''' shell echo \\$EPOCHREALTIME''', shell=True).decode()
        with open(os.path.join(self.get_path(), "time_log"), 'w') as timefile:
            timefile.write("PC: " + str(time.time()) + "\n")
            timefile.write("Phone: " + phonetime + "\n")


if __name__ == "__main__":
    logging.VERBOSE = 7
    configuration = Configuration()

    argument_parser = argparse.ArgumentParser(description="Perform a maesurement run.")
    argument_parser.add_argument('--config', '-c', type=str, default='default.config', dest='config_file',
                                 help="Specify the config file. Default: default.config")
    argument_parser.add_argument('-li', '--last-iteration', type=int, default=1, dest='last_iteration',
                                 help="Iteration to start with. Default: 1")
    argument_parser.add_argument('-i', '--iterations', type=int, default=1, dest='iterations',
                                 help="Maximum iteration to perform. Default: 1")
    argument_parser.add_argument('--nexus', action='store_const', const=True, default=False, dest='nexus',
                                 help="Patch for Nexus 6P. Default: false")  # TODO: Talk with Theo
    argument_parser.add_argument('--grepable-log', '-gl', action='store_const', const=True, default=False,
                                 dest='grepable_log',
                                 help="Enables grepable logfile")
    argument_parser.add_argument('--no-wrapper', '-nw', action='store_const', const=True, default=False,
                                 dest='no_wrapper',
                                 help="Disable launching the wrapper for debugging purposes")
    argument_parser.add_argument('--no-reboot', '-nr', action='store_const', const=True, default=False,
                                 dest='no_reboot',
                                 help="Disable device reboot debugging purposes")
    argument_parser.add_argument('--suppress-output', '-su', action='store_const', const=True, default=False,
                                 dest='suppress_output',
                                 help="Suppress output by invoked processes")
    argument_parser.add_argument('--reset-usb', '-ru', action='store_const', const=True, default=False,
                                 dest='reset_usb',
                                 help="Reset USB device in addition to restarting the phone")
    argument_parser.add_argument('--logfile', '-l', type=str, default=None, dest='logfile',
                                 help="Specify a logfile to print log output to")
    verbosity_group = argument_parser.add_mutually_exclusive_group()
    verbosity_group.add_argument('-vv', action='store_const', dest='verbosity', const=logging.VERBOSE,
                                 help="Set logging level to verbose")
    verbosity_group.add_argument('-v', action='store_const', dest='verbosity', const=logging.DEBUG,
                                 default=logging.INFO, help="Set logging level to debug. Default is info")
    verbosity_group.add_argument('-q', action='store_const', dest='verbosity', const=logging.WARNING,
                                 help="Set logging level to warning")
    verbosity_group.add_argument('-qq', action='store_const', dest='verbosity', const=logging.ERROR,
                                 help="Set logging level to error")
    verbosity_group.add_argument('-qqq', action='store_const', dest='verbosity', const=logging.CRITICAL,
                                 help="Set logging level to critical")
    argument_parser.parse_args(namespace=configuration)

    if configuration.verbosity is None:
        configuration.verbosity = logging.INFO

    logging.addLevelName(logging.VERBOSE, "VERBOSE")
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s:%(levelname)s:%(message)s', log_colors={

            'CRITICAL': 'red,bg_white',
            'ERROR': 'red',
            'WARNING': 'yellow',
            'INFO': 'white',
            'DEBUG': 'cyan'
        }))
    logger = colorlog.getLogger('root')
    logger.setLevel(configuration.verbosity)
    logger.addHandler(handler)

    if configuration.logfile is not None:
        file_handler = logging.FileHandler(configuration.logfile)
        file_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(message)s'))
        logger.addHandler(file_handler)

    grep_logger = None
    if configuration.grepable_log:
        grep_logger = logging.getLogger('grep')
        handler = logging.FileHandler(str(time.time()) + "_output.log")
        formatter = logging.Formatter('%(asctime)s %(message)s', datefmt='%s')
        handler.setFormatter(formatter)
        grep_logger.addHandler(handler)

    config = configparser.ConfigParser({"wifi_interface": "wlan0"})
    config.read(configuration.config_file)
    configuration.devices = config["GENERAL"]["devices"].split(", ")
    configuration.location = config["GENERAL"]["measurement_site"]
    configuration.schedule_directory = config["GENERAL"]["schedule_directory"]
    configuration.video_list = config["GENERAL"]["video_list"]
    configuration.alternate_phones = config.getboolean("POWER", "alternate_phones")
    configuration.battery_threshold = config.getint("POWER", "battery_threshold")
    configuration.sleep_time = config.getint("POWER", "sleep_time")
    configuration.interface = config["NETWORK"]["interface"]
    configuration.wifi = config["NETWORK"]["wifi_interface"]
    configuration.data_socket = config.getint("NETWORK", "data_socket")
    configuration.command_socket = config.getint("NETWORK", "command_socket")

    atexit.register(cleanup)

    logger.warn("Loglevel is " + logging.getLevelName(configuration.verbosity))
    start_time = time.time()

    with open(configuration.video_list, 'r') as file:
        videos = file.readlines()

    logger.log(logging.VERBOSE, "Read %i lines of videos", len(videos))

    measurement = None
    current_iteration = configuration.last_iteration

    connected_devices = subprocess.check_output("adb devices", shell=True).decode()
    for phone_id in configuration.devices:
        if phone_id not in connected_devices:
            logger.error("Device " + phone_id + " seems to be offline, removing from device list")
            configuration.devices.remove(phone_id)
        else:
            logger.info(("Device " + phone_id + " connected, commencing measurement"))

    while current_iteration <= configuration.iterations:
        logger.info("Starting iteration %i", current_iteration)
        for video_id in videos:
            while True:
                measurement = Measurement(current_iteration, video_id)
                measurement.run()
                if not measurement.receiver.discard:
                    break
        current_iteration += 1

    logger.info("Measurement complete. Time elapsed: " + str(time.time() - start_time) + " seconds")
