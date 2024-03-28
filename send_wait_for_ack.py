from __future__ import print_function
from socket import socket, AF_INET, SOCK_STREAM
from threading import Thread

import argparse
import json
import sys
import time

# based on https://planetarystatusreport.com/?p=646

# make sure you open port 2442 prior to opening JS8 application
# ubuntu command: sudo ufw allow 2442

# TODO DEO add max time to wait for ack

parser = argparse.ArgumentParser(
    prog="JS8Call send and wait for ACK",
    description="Sends a message and waits for an ACK",
)
parser.add_argument("-r", "--receipient", required=True)
parser.add_argument("-m", "--message", required=True)
parser.add_argument("-t", "--tries", type=int, default=3)
parser.add_argument("-i", "--interval", type=int, default=120)
parser.add_argument("-s", "--server", default="127.0.0.1:2473")


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
    server = ("127.0.0.1", 2473)  # js8call api server
    # callsign to send message to
    receipient = "XXXXXX"
    # number of times to try to send the message (includes the first initial tx)
    retries = 1
    retry_interval = 90  # seconds to wait between tries; this should be several minutes
    message = "ACK ME BRO"  # message to send

    # internal variables
    gotAck = False  # did we get an ack
    stop_timer = False  # should the timer thread stop
    callsign = "XXXXXX"  # your callsign; will be grabbed from JS8Call
    attemptsMade = 0

    def __init__(
        self, receipient, message, server="127.0.0.1:2473", retries=3, interval=120
    ):
        self.receipient = receipient
        self.message = message
        self.retries = retries
        self.retry_interval = interval
        s = server.split(":")
        self.server = (s[0], int(s[1]))
        print("server=", self.server)

    def process(self, message):
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
        print("-> msg from ", msg.get("FROM"), "to", msg.get("TO"))
        if msg.get("TO") == self.callsign and msg.get("FROM") == self.receipient:
            print("-> Got a message for me:", msg.get("TEXT"))
            if msg.get("TEXT").contains("ACK"):
                # got an ACK
                # TODO DEO need to better recognize an ACK
                self.gotAck = True

    def send(self, *args, **kwargs):
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

    def connect(self):
        print("connecting to", ":".join(map(str, self.server)))
        self.sock = socket(AF_INET, SOCK_STREAM)
        self.sock.connect(self.server)
        self.connected = True

        try:
            # get callsign
            self.send("STATION.GET_CALLSIGN")

            # start a time to send the message on the interval
            print("Starting to send...")
            timer = Thread(target=self.attemptToSend)
            # comment out the following line to disable sending msg
            timer.run()

            while self.connected:

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
                    self.stop_timer = True
                    break

        finally:
            if timer.is_alive:
                self.stop_timer = True
            self.sock.close()

        return self.gotAck

    def close(self):
        self.connected = False


def main():
    args = parser.parse_args()
    s = Client(args.receipient, args.message, args.server, args.tries, args.interval)
    result = s.connect()
    sys.exit(not result)


if __name__ == "__main__":
    main()
