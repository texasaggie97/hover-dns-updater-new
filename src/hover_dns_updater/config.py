"""Configuration for the Hover DNS updater."""

import json
import os
import pprint
import sys

from .constants import default_config

pp = pprint.PrettyPrinter(width=120)


class HoverConfig(object):
    def __init__(self, args):
        self._config = default_config
        try:
            with open(args.config_file, "r") as c:
                config = json.load(c)
                for k in config:
                    self._config[k] = config[k]
        except FileNotFoundError:
            with open(args.config_file, "w") as c:
                json.dump(default_config, c)
            sys.exit(1)

        # Override config file with command line parameters
        self.USERNAME = self._config["username"]
        self.PASSWORD = self._config["password"]
        self.DNS_IDS = self._config["dns_ids"]
        self.TOPTKEY = self._config["toptkey"]
        self.LOGFILE = (
            self._config["logfile"] if args.log_file is None else args.log_file
        )
        self.SERVICE = (
            self._config["run-as-service"] if args.service is None else args.service
        )
        self.POLLTIME = (
            self._config["poll-time"] if args.poll_time is None else args.poll_time
        )

        if self.USERNAME == "ENV":
            self.USERNAME = os.environ["USERNAME"]
        if self.PASSWORD == "ENV":
            self.PASSWORD = os.environ["PASSWORD"]
        if self.LOGFILE == "ENV":
            self.LOGFILE = os.environ["LOGFILE"]
        if self.TOPTKEY == "ENV":
            self.TOPTKEY = os.environ["TOPTKEY"]
        if len(self.DNS_IDS) == 1 and self.DNS_IDS[0] == "ENV":
            self.DNS_IDS = []
            i = 1
            # We expect the environment variable to be DNS1, DNS2, ... DNSn
            while True:
                try:
                    id = "DNS{0}".format(i)
                    self.DNS_IDS.append(os.environ[id])
                    i += 1
                except KeyError:
                    break

    def __repr__(self):
        ret_str = self.__class__.__name__ + "():\n"
        ret_str += "    USERNAME = {0}\n".format(self.USERNAME)
        ret_str += "    PASSWORD = {0}\n".format(self.PASSWORD)
        ret_str += "    TOPTKEY = {0}\n".format(self.TOPTKEY)
        ret_str += "    DNS_IDS = {0}\n".format(pp.pformat(self.DNS_IDS))
        ret_str += "    LOGFILE = {0}\n".format(str(self.LOGFILE))
        ret_str += "    SERVICE = {0}\n".format(str(self.SERVICE))
        ret_str += "    POLLTIME = {0}\n".format(str(self.POLLTIME))
        return ret_str
