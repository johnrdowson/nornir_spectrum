from nornir.core.inventory import (
    Inventory,
    Group,
    Groups,
    Host,
    Hosts,
    Defaults,
    ParentGroups,
    ConnectionOptions,
)

import re
import os
import urllib3
from typing import Optional, Union, List, Tuple, Dict, Any

import requests
from lxml import etree

urllib3.disable_warnings()

SPECTRUM_PORT_MAP = {"32": 22, "7": 22, "3": 23}


NETMIKO_MODEL_TYPE_MAP = {
    "Rtr_Cisco": "ios",
    "SwCiscoIOS": "ios",
    "CiscoNXOS": "nxos_ssh",
    "SwCat45xx": "ios",
    "HubCat29xx": "ios",
    "CiscoASA": "cisco_asa",
}

NETMIKO_DEVICE_TYPE_MAP = {"CiscoRT": "ios", "JuniperRT": "junos"}


def platform_calc(model_type_name: str, device_type: str) -> str:
    platform = NETMIKO_MODEL_TYPE_MAP.get(
        model_type_name,
        NETMIKO_DEVICE_TYPE_MAP.get(device_type),
    )
    if not platform and device_type:
        if re.search("Cisco", device_type):
            platform = "ios"
        elif re.search("Juniper", device_type):
            platform = "junos"

    return platform


def _strip_ns(root: etree.Element) -> etree.Element:
    """
    Removes all namespaces from an XML Element tree. This will make parsing the
    XML element much simpler.
    """

    for elem in root.getiterator():
        elem.tag = etree.QName(elem).localname

    etree.cleanup_namespaces(root)
    return root


def _process_data(hosts_data: List[Dict[str, str]]) -> Tuple[Hosts, Groups]:
    """
    Converts the parsed data from Spectrum and returns the host and groups data.
    The groups
    """

    # Placeholders for the hosts and groups data which will be popuated
    hosts = Hosts()
    groups = Groups()

    for device in hosts_data:

        # Global Collections for which this host is a member of
        gc_str = device.pop("0x12adb")
        gc_list = list(set(gc_str.split(":"))) if gc_str else []

        # Create a group for each Global Collection if it doesn't already exist
        for gc in gc_list:
            groups.setdefault(gc, Group(gc))

        # Retrieve the management port
        port = SPECTRUM_PORT_MAP.get(device.pop("0x12beb"))

        # If no port then assume this host cannot be accessed via CLI (skip)
        if not port:
            continue

        # Calculate platform type
        platform = platform_calc(device.get("0x10000"), device.get("0x23000e"))

        # Telnet-only Cisco devices need specific options for Netmiko and Napalm to work
        if port == 23 and platform == "ios":
            connection_options.update(
                {
                    "netmiko": ConnectionOptions(
                        extras={"device_type": "cisco_ios_telnet"}
                    ),
                    "napalm": ConnectionOptions(
                        extras={"optional_args": {"transport": "telnet"}}
                    ),
                }
            )
        else:
            connection_options = {}

        # Fall back to generic
        if port == 22 and not platform:
            platform = "generic"
        elif port == 23 and not platform:
            platform = "generic_telnet"

        # NETCONF for all Juniper devices
        if platform == "junos":
            port = 830

        # Use names for data keys otherwise the advanced filtering not possible
        # in Nornir
        data = dict()
        data["model_type"] = device.pop("0x10000", "")
        data["condition"] = int(device.pop("0x1000a", 0))
        data["model_class"] = int(device.pop("0x11ee8", 0))
        data["device_type"] = device.pop("0x23000e", "")
        data["topology_string"] = device.pop("0x129e7", "")
        data.update(device)

        # Finally create the host object
        hostname = data.pop("0x1006e")
        hosts[hostname] = Host(
            name=hostname,
            hostname=data.pop("0x12d7f"),  # Network Address
            port=port,
            platform=platform,
            groups=ParentGroups([groups[gc] for gc in gc_list]),
            connection_options=connection_options,
            data={**data},
        )

    return (hosts, groups)


class SpectrumInventory:
    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify: Union[bool, str] = False,
        proxies: Optional[Dict[str, Union[str, None]]] = None,
    ) -> None:
        self.url = url or os.environ.get("SPECTRUM_URL")
        self.username = username or os.environ.get("SPECTRUM_USERNAME")
        self.password = password or os.environ.get("SPECTRUM_PASSWORD")
        self.verify = verify
        self.proxies = proxies

    def load(self) -> Inventory:
        """Retrieves the inventory of devices from Spectrum"""

        url = f"{self.url}/spectrum/restful/devices"

        attrs = [
            "0x1006e",  # Model Name
            "0x10000",  # Model Type Name
            "0x11ee8",  # Model Class
            "0x23000e",  # Device Type
            "0x12d7f",  # Network Address
            "0x1000a",  # Condition
            "0x12adb",  # Collections Model Name String
            "0x129e7",  # Topology Model Name String
            "0x12beb",  # NCM Potential Comm Modes
        ]

        params = {
            "attr": attrs,
            "throttlesize": "9999",
        }

        resp = requests.get(
            url=url,
            auth=(self.username, self.password),
            headers={"Content-Type": "application/xml"},
            params=params,
            verify=self.verify,
            proxies=self.proxies,
        )

        resp.raise_for_status()

        # Parse XML Data
        try:
            root = etree.fromstring(resp.content)
        except etree.XMLSyntaxError as err:
            raise ValueError(f"Unable to parse XML response\n\n{err}")

        root = _strip_ns(root)
        models = root.findall(".//model")

        data = [{attr.get("id"): attr.text for attr in model} for model in models]

        hosts, groups = _process_data(data)

        return Inventory(hosts=hosts, groups=groups, defaults=Defaults())
