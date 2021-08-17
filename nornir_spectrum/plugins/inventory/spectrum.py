from nornir.core.inventory import (
    Inventory,
    Group,
    Groups,
    Host,
    Hosts,
    Defaults,
    ParentGroups,
)

import re
import os
from typing import Optional, Union, List, Tuple, Dict, Any

import requests
from lxml import etree

SPECTRUM_PORT_MAP = {"32": 22, "7": 22, "3": 23}


NETMIKO_MODEL_TYPE_MAP = {
    "Rtr_Cisco": "cisco_ios",
    "SwCiscoIOS": "cisco_ios",
    "CiscoNXOS": "cisco_nxos",
    "SwCat45xx": "cisco_ios",
    "HubCat29xx": "cisco_ios",
    "CiscoASA": "cisco_asa",
}

NETMIKO_DEVICE_TYPE_MAP = {"CiscoRT": "cisco_ios", "JuniperRT": "junos"}


def platform_calc(model_type_name: str, device_type: str) -> str:
    platform = NETMIKO_MODEL_TYPE_MAP.get(
        model_type_name,
        NETMIKO_DEVICE_TYPE_MAP.get(device_type),
    )
    if not platform and device_type:
        if re.search("Cisco", device_type):
            platform = "cisco_ios"
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

    # Main loop to interate over each device model
    for device in hosts_data:

        # Extract the unique Global Collections for which this host is a member
        # of
        gc_str = device.pop("collections_model_name_string")
        gc_list = list(set(gc_str.split(":"))) if gc_str else []

        # Add each Global Collection as a group if it doesn't already exist
        for gc in gc_list:
            groups.setdefault(gc, Group(gc))

        port = SPECTRUM_PORT_MAP.get(device.get("ncm_potential_comm_modes"))

        if port:
            platform = platform_calc(
                device.get("model_type_name"), device.get("device_type")
            )
        else:
            continue

        # Telnet only Cisco devices need specific platform for Netmiko to work
        if port == 23 and platform == "cisco_ios":
            platform = "cisco_ios_telnet"

        # NETCONF for all Juniper devices
        if platform == "junos":
            port = 830

        hostname = device.pop("model_name")

        hosts[hostname] = Host(
            name=hostname,
            hostname=device.pop("network_address"),
            port=port,
            platform=platform,
            groups=ParentGroups([groups[gc] for gc in gc_list]),
            data={**device},
        )

    return (hosts, groups)


class SpectrumInventory:
    def __init__(
        self,
        url: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        verify: Union[bool, str] = False,
    ) -> None:
        self.url = url or os.environ.get("SPECTRUM_URL")
        self.user = user or os.environ.get("SPECTRUM_USER")
        self.password = password or os.environ.get("SPECTRUM_PASSWORD")
        self.verify = verify

    def load(self) -> Inventory:
        """Retrieves the inventory of devices from Spectrum"""

        url = f"{self.url}/spectrum/restful"

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
        )

        resp.raise_for_status()

        # Parse XML Data

        _xparser = etree.XMLParser(recover=True, remove_blank_text=True)

        try:
            root = etree.fromstring(resp.content, parser=_xparser)
        except etree.XMLSyntaxError as err:
            raise ValueError(f"Unable to parse XML response\n\n{err}")

        root = _strip_ns(root)

        data = [
            {attr.get("id"): attr.text for attr in model}
            for model in self.root[0]
        ]

        hosts, groups = _process_data(data)

        return Inventory(hosts=hosts, groups=groups, defaults=Defaults())
