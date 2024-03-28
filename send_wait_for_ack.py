"""
Script to send a JS8Call message and wait for an ACK response.

Based on https://planetarystatusreport.com/?p=646

make sure you open port 2442 prior to opening JS8 application
ubuntu command: sudo ufw allow 2442
"""

from socket import socket, AF_INET, SOCK_STREAM
from threading import Thread, Timer

import argparse
import json
import sys
import time

parser = argparse.ArgumentParser(
    prog="JS8Call send and wait for ACK",
    description="Sends a message and waits for an ACK",
)
parser.add_argument(
    "-r", "--receipient", required=True, help="Callsign of the receipient"
)
parser.add_argument("-m", "--message", required=True, help="Message to send")
parser.add_argument(
    "-t",
    "--tries",
    type=int,
    default=3,
    help="Number of times to attempt to send the message",
)
parser.add_argument(
    "-i",
    "--interval",
    type=int,
    default=120,
    help="Interval (in seconds) between attempts",
)
parser.add_argument(
    "-s", "--server", default="127.0.0.1:2473", help="JS8Call API server host and port"
)
parser.add_argument(
    "-w",
    "--maxwait",
    type=int,
    default=600,
    help="Max time (in seconds) to wait for an ack",
)


def from_message(content):
    try:
        return json.loads(content)
    except ValueError:
        return {}


def to_message(typ, value="", params=None):
    if params is None:
        params = {}
    return json.dumps({"type": typ, "value": value, "params": params})


class Client(object):
    server = ("127.0.0.1", 2473)
    receipient = "XXXXXX"
    retries = 1
    retry_interval = 90
    message = "ACK ME BRO"
    max_wait = 600

    # internal variables
    gotAck = False  # did we get an ack
    stop_timer = False  # should the timer thread stop
    timed_out = False  # did we hit the max time out
    callsign = "XXXXXX"  # your callsign; will be grabbed from JS8Call
    attemptsMade = 0

    def __init__(
        self,
        receipient,
        message,
        server="127.0.0.1:2473",
        retries=3,
        interval=120,
        maxwait=600,
    ):
        self.receipient = receipient
        self.message = message
        self.retries = retries
        self.retry_interval = interval
        self.max_wait = maxwait
        s = server.split(":")
        self.server = (s[0], int(s[1]))

    def process(self, message):
        """Process a message received from JS8Call."""
        typ = message.get("type", "")
        value = message.get("value", "")
        params = message.get("params", {})
        if not typ:
            return

        if typ in ("RX.ACTIVITY",):
            # skip
            return

        print("->", typ)

        if value:
            print("-> value", value)

        if params:
            print("-> params: ", params)

            # DEO experiment to get inbox messages
            if not params.get("MESSAGES") is None:
                print(params.get("MESSAGES"))
                print(type(params.get("MESSAGES")))
                print("There are", len(params.get("MESSAGES")), " messasges")

        if typ == "STATION.CALLSIGN":
            print("Setting callsign to", value)
            self.callsign = value

        if typ in ("RX.DIRECTED",):
            self.processRxDirected(params)

    def processRxDirected(self, msg):
        """Process an RX.DIRECTED message."""
        print("-> msg from ", msg.get("FROM"), "to", msg.get("TO"))
        if msg.get("TO") == self.callsign and msg.get("FROM") == self.receipient:
            print("-> Got a message for me:", msg.get("TEXT"))
            if msg.get("TEXT").contains("ACK"):
                # got an ACK
                print("Got ACK!")
                # TODO DEO need to better recognize an ACK
                self.gotAck = True

    def send(self, *args, **kwargs):
        """Send a message to JS8Call."""
        params = kwargs.get("params", {})
        if "_ID" not in params:
            params["_ID"] = "{}".format(int(time.time() * 1000))
            kwargs["params"] = params
        message = to_message(*args, **kwargs)
        print("<- outgoing message:", message)
        self.sock.send(
            (message + "\n").encode()
        )  # remember to send the newline at the end :)

    def attemptToSend(self):
        """Attempts to send a message every retry_interval seconds for retries attempts."""
        time.sleep(10)
        while True:
            if self.stop_timer:
                break

            self.attemptsMade += 1
            print("Sending attempt", self.attemptsMade)
            self.send("TX.SEND_MESSAGE", self.receipient + " " + self.message)
            if self.attemptsMade >= self.retries:
                print("No more attempts to be made")
                return
            time.sleep(self.retry_interval)

    def timeout(self):
        print("Timeout reached, stopping...")
        self.stop_timer = True
        self.timed_out = True

    def connect(self):
        """Connect to JS8Call API server and try to send the message."""
        print("connecting to", ":".join(map(str, self.server)))
        self.sock = socket(AF_INET, SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect(self.server)
        self.connected = True

        try:
            # get callsign
            self.send("STATION.GET_CALLSIGN")

            # start timer for max wait
            print("Setting max wait to", self.max_wait, "seconds")
            timeoutTimer = Timer(self.max_wait, self.timeout)
            timeoutTimer.start()

            # start a thread to send the message on the interval
            print("Starting to send...")
            timer = Thread(target=self.attemptToSend)
            # comment out the following line to disable sending msg
            timer.run()

            while self.connected and not self.timed_out:
                try:

                    # block while waiting for message from js8call
                    content = self.sock.recv(65500)
                    if not content:
                        break

                    try:
                        message = json.loads(content)
                    except ValueError:
                        message = {}

                    if not message:
                        continue

                    self.process(message)

                    if self.gotAck:
                        # if we get an ack, inform the timer to stop trying to send the message
                        self.stop_timer = True
                        break
                except TimeoutError:
                    # got socket time out waiting for a message, this is normal so skip it
                    pass
                except:
                    print("Some other socket error")

        finally:
            print("Closing things out...")
            if timer.is_alive:
                self.stop_timer = True
            self.sock.close()

        return self.gotAck

    def close(self):
        self.connected = False


def main():
    args = parser.parse_args()
    s = Client(
        args.receipient,
        args.message,
        args.server,
        args.tries,
        args.interval,
        args.maxwait,
    )
    result = s.connect()
    sys.exit(not result)


if __name__ == "__main__":
    main()
