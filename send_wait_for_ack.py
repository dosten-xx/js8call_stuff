from __future__ import print_function
from socket import socket, AF_INET, SOCK_STREAM
from threading import Thread

import json
import time

# based on https://planetarystatusreport.com/?p=646

# make sure you open port 2442 prior to opening JS8 application
# ubuntu command: sudo ufw allow 2442

def from_message(content):
    try:
        return json.loads(content)
    except ValueError:
        return {}


def to_message(typ, value='', params=None):
    if params is None:
        params = {}
    return json.dumps({'type': typ, 'value': value, 'params': params})


class Client(object):
    attemptsMade = 0
    gotAck = False
    server = ('127.0.0.1', 2473) # js8call api server
    callsign = "KN6KTN" # your callsign
    receipient = "KC8OWL" # callsign to send message to
    retries = 1 # number of times to try to send the message (includes the first initial tx)
    retry_interval = 90 # seconds to wait between tries; this should be several minutes
    message = "ACK ME BRO" # message to send
    stop_timer = False


    def process(self, message):
        typ = message.get('type', '')
        value = message.get('value', '')
        params = message.get('params', {})
        if not typ:
            return

        if typ in ('RX.ACTIVITY',):
            # skip
            return

        print('->', typ)

        if value:
            print('-> value', value)

        if params:
            print('-> params: ', params)

            # DEO experiment to get inbox messages
            if (not params.get('MESSAGES') is None):
                print(params.get('MESSAGES'))
                print(type(params.get('MESSAGES')))
                print("There are", len(params.get('MESSAGES')), " messasges")

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
        params = kwargs.get('params', {})
        if '_ID' not in params:
            params['_ID'] = '{}'.format(int(time.time()*1000))
            kwargs['params'] = params
        message = to_message(*args, **kwargs)
        print('outgoing message:', message)
        self.sock.send((message + '\n').encode()) # remember to send the newline at the end :)


    def attemptToSend(self):
        while True:
            if self.stop_timer:
                break

            self.attemptsMade += 1
            print("Sending attempt", self.attemptsMade)
            self.send("TX.SEND_MESSAGE", self.receipient + ": " + self.message)
            if self.attemptsMade >= self.retries:
                print("No more attempts to be made")
                return
            time.sleep(self.retry_interval)


    def connect(self):
        print('connecting to', ':'.join(map(str, self.server)))
        self.sock = socket(AF_INET, SOCK_STREAM)
        self.sock.connect(self.server)
        self.connected = True
        try:
            # start a time to send the message on the interval
            print("Starting to send...")
            timer = Thread(target=self.attemptToSend)
            timer.run()
            #timer = threading.Timer(self.retry_interval, self.attemptToSend)
            #timer.start()

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


    def close(self):
        self.connected = False


def main():
    s = Client()
    s.connect()

if __name__ == '__main__':
    main()
