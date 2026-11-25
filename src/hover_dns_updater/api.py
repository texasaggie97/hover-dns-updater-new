"""Hover authentication and DNS API client."""

import datetime
import logging

import pyotp
import requests

from .constants import API_BASE_URL, AUTH_CACHE_SECONDS, SIGNIN_URL, TIMEOUT
from .exceptions import HoverError


class HoverAPI(object):
    def __init__(self, config):
        self._config = config
        self._current_dns_ips = {}
        self.get_auth()

    def get_auth(self):
        logging.info("Logging in")

        # Getting required cookies "hover_session" and "hoverauth"
        r = requests.get(SIGNIN_URL, timeout=TIMEOUT)
        self._cookies = {"hover_session": r.cookies["hover_session"]}

        params = {
            "password": self._config.PASSWORD,
            "username": self._config.USERNAME,
            "token": None,
        }
        r = requests.post(
            "{0}/auth.json".format(SIGNIN_URL),
            json=params,
            cookies=self._cookies,
            timeout=TIMEOUT,
        )

        otp = self._config.TOPTKEY
        topt = pyotp.TOTP(otp + "=" * (-len(otp) % 8))
        params = {"code": topt.now()}
        r = requests.post(
            "{0}/auth2.json".format(SIGNIN_URL),
            json=params,
            cookies=self._cookies,
            timeout=TIMEOUT,
        )

        if not r.ok or "hoverauth" not in r.cookies:
            raise HoverError(r)
        self._cookies["hoverauth"] = r.cookies["hoverauth"]
        self._auth_timestamp = datetime.datetime.now()
        logging.info("Hover authentication succeeded")

    def check_auth(self):
        td = datetime.datetime.now() - self._auth_timestamp
        # We will cache the login authorization for two hours
        if td.total_seconds() > AUTH_CACHE_SECONDS:
            logging.info(
                "Refreshing Hover session after %.0f seconds (two-hour threshold)",
                td.total_seconds(),
            )
            self.get_auth()

    def get_current_ips(self):
        logging.info("Getting current IP addresses from Hover:")
        current = self.call("get", "dns")
        for domain in current.get("domains"):
            for entry in domain["entries"]:
                if entry["id"] in self._config.DNS_IDS:
                    logging.info("    {0} = {1}".format(entry["id"], entry["content"]))
                    self._current_dns_ips[entry["id"]] = entry["content"]

    def update(self):
        current_external_ip = requests.get(
            "https://api.ipify.org", timeout=TIMEOUT
        ).text
        logging.info("Updating - Current external IP = {0}".format(current_external_ip))
        for dns_id in self._current_dns_ips:
            logging.debug("    {0} = {1}".format(dns_id, self._current_dns_ips[dns_id]))
            if self._current_dns_ips[dns_id] != current_external_ip:
                logging.info(
                    "    Updating DNS entry for {0} to {1}".format(
                        dns_id, current_external_ip
                    )
                )
                self.call("put", "dns/" + dns_id, {"content": current_external_ip})
                # Update cache
                self._current_dns_ips[dns_id] = current_external_ip

    def call(self, method, resource, data=None):
        logging.debug(
            "method={0}, resource={1}, data={2}".format(method, resource, str(data))
        )
        self.check_auth()
        url = "{0}/{1}".format(API_BASE_URL, resource)
        r = requests.request(
            method, url, data=data, cookies=self._cookies, timeout=TIMEOUT
        )
        if not r.ok:
            raise HoverError(r)
        if r.content:
            body = r.json()
            if "succeeded" not in body or body["succeeded"] is not True:
                raise HoverError(body)
            return body
